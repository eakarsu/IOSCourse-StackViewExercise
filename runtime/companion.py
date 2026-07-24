from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

CANONICAL_BASE_URL = "https://openrouter.ai/api/v1"
PASSWORD_ITERATIONS = 310_000
SESSION_TTL_SECONDS = 8 * 60 * 60


class ProviderError(RuntimeError):
    """An upstream failure that is safe to report without leaking details."""


@dataclass(frozen=True)
class RuntimeConfig:
    api_port: int
    ui_origin: str
    database_path: Path
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        required = {
            key: os.environ.get(key, "").strip()
            for key in (
                "API_PORT",
                "UI_ORIGIN",
                "RUNTIME_DB_PATH",
                "OPENROUTER_API_KEY",
                "OPENROUTER_MODEL",
                "OPENROUTER_BASE_URL",
            )
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing environment configuration: {', '.join(missing)}")
        try:
            api_port = int(required["API_PORT"])
        except ValueError as error:
            raise ValueError("API_PORT must be numeric") from error
        if api_port != 31004:
            raise ValueError("API_PORT must be 31004 for this verification shard")
        if required["UI_ORIGIN"] != "http://127.0.0.1:31005":
            raise ValueError("UI_ORIGIN must be http://127.0.0.1:31005")
        if required["OPENROUTER_BASE_URL"] != CANONICAL_BASE_URL:
            raise ValueError("OPENROUTER_BASE_URL must be canonical")
        return cls(
            api_port=api_port,
            ui_origin=required["UI_ORIGIN"],
            database_path=Path(required["RUNTIME_DB_PATH"]).expanduser().resolve(),
            openrouter_api_key=required["OPENROUTER_API_KEY"],
            openrouter_model=required["OPENROUTER_MODEL"],
            openrouter_base_url=required["OPENROUTER_BASE_URL"],
        )


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)


class RuntimeDatabase:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def authenticate(self, email: str, password: str) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, password_salt, password_hash FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
        salt = bytes(row["password_salt"]) if row else b"missing-user-salt"
        expected = bytes(row["password_hash"]) if row else b"\0" * 32
        actual = password_digest(password, salt)
        if row and hmac.compare_digest(actual, expected):
            return int(row["id"])
        return None

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        now = int(time.time())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, now, now + SESSION_TTL_SECONDS),
            )
        return token

    def actor_for_token(self, token: str) -> dict[str, object] | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, int(time.time())),
            ).fetchone()
        if not row:
            return None
        return {"id": int(row["id"]), "email": str(row["email"])}

    def persist_interaction(
        self,
        user_id: int,
        prompt: str,
        response: str,
        model: str,
        receipt: dict[str, object],
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ai_interactions(user_id, prompt, response, model, provider_receipt, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, prompt, response, model, json.dumps(receipt, separators=(",", ":")), int(time.time())),
            )
            return int(cursor.lastrowid)

    def interaction_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM ai_interactions").fetchone()
        return int(row["count"])


def prepare_database(path: Path, email: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(16)
    digest = password_digest(password, salt)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash BLOB PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                model TEXT NOT NULL,
                provider_receipt TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
            CREATE TRIGGER IF NOT EXISTS ai_interactions_no_update
            BEFORE UPDATE ON ai_interactions
            BEGIN
                SELECT RAISE(ABORT, 'ai_interactions is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS ai_interactions_no_delete
            BEFORE DELETE ON ai_interactions
            BEGIN
                SELECT RAISE(ABORT, 'ai_interactions is append-only');
            END;
            """
        )
        connection.execute(
            """
            INSERT INTO users(email, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password_salt = excluded.password_salt,
                password_hash = excluded.password_hash
            """,
            (email.strip().lower(), salt, digest, int(time.time())),
        )
    os.chmod(path, 0o600)


def call_openrouter(config: RuntimeConfig, prompt: str) -> tuple[str, dict[str, object]]:
    payload = {
        "model": config.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an iOS UIStackView accessibility and layout reviewer. "
                    "Give concise, actionable advice grounded only in the supplied de-identified layout description."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 550,
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{config.openrouter_base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": config.ui_origin,
            "X-Title": "Stack View Runtime Companion",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as upstream:
            body = upstream.read(1_500_000)
        decoded = json.loads(body.decode("utf-8"))
        content = decoded["choices"][0]["message"]["content"]
        request_id = decoded["id"]
        if not isinstance(content, str) or not content.strip() or not isinstance(request_id, str) or not request_id:
            raise ProviderError("provider returned an incomplete response")
        receipt: dict[str, object] = {
            "requestId": request_id,
            "provider": "openrouter",
            "upstreamModel": decoded.get("model", config.openrouter_model),
            "created": decoded.get("created"),
        }
        return content.strip(), receipt
    except ProviderError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError, KeyError, IndexError, TypeError) as error:
        raise ProviderError("provider request failed") from error


ProviderCall = Callable[[RuntimeConfig, str], tuple[str, dict[str, object]]]


def build_api_server(
    config: RuntimeConfig,
    provider_call: ProviderCall = call_openrouter,
) -> ThreadingHTTPServer:
    database = RuntimeDatabase(config.database_path)

    class APIHandler(BaseHTTPRequestHandler):
        server_version = "StackRuntime/1"

        def path_only(self) -> str:
            return urlsplit(self.path).path

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            self.log_message('"%s %s" %s %s', self.command, self.path_only(), code, size)

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("runtime-api: " + (fmt % args) + "\n")

        def send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            origin = self.headers.get("Origin")
            if origin == config.ui_origin:
                self.send_header("Access-Control-Allow-Origin", config.ui_origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def read_json(self) -> dict[str, object] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if length <= 0 or length > 32_768:
                return None
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeError):
                return None
            return value if isinstance(value, dict) else None

        def actor(self) -> dict[str, object] | None:
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                return None
            token = authorization[7:].strip()
            return database.actor_for_token(token) if token else None

        def do_OPTIONS(self) -> None:
            if self.path_only().startswith("/api/"):
                self.send_response(204)
                if self.headers.get("Origin") == config.ui_origin:
                    self.send_header("Access-Control-Allow-Origin", config.ui_origin)
                    self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Vary", "Origin")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_json(404, {"error": "not_found"})

        def do_GET(self) -> None:
            path = self.path_only()
            if path == "/api/health":
                self.send_json(200, {"status": "ok", "service": "stack-runtime-companion"})
                return
            if path == "/api/auth/demo-credentials":
                enabled = os.environ.get("ENABLE_DEMO_CREDENTIAL_AUTOFILL", "true").lower() == "true"
                email = os.environ.get("DEMO_EMAIL") or os.environ.get("PROVISION_ADMIN_EMAIL")
                password = os.environ.get("DEMO_PASSWORD") or os.environ.get("PROVISION_ADMIN_PASSWORD")
                if os.environ.get("NODE_ENV") == "production" or not enabled or not email or not password:
                    self.send_json(404, {"error": "not_found"})
                    return
                self.send_json(200, {"email": email, "password": password})
                return
            if path == "/api/auth/me":
                actor = self.actor()
                if not actor:
                    self.send_json(401, {"error": "authentication_required"})
                    return
                self.send_json(200, {"user": actor})
                return
            self.send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            path = self.path_only()
            try:
                if path == "/api/auth/login":
                    body = self.read_json()
                    email = body.get("email") if body else None
                    password = body.get("password") if body else None
                    if not isinstance(email, str) or not isinstance(password, str):
                        self.send_json(400, {"error": "invalid_request"})
                        return
                    user_id = database.authenticate(email, password)
                    if user_id is None:
                        self.send_json(401, {"error": "invalid_credentials"})
                        return
                    token = database.create_session(user_id)
                    actor = database.actor_for_token(token)
                    self.send_json(200, {"token": token, "user": actor or {}})
                    return
                if path == "/api/ai/stack-layout-advisory":
                    actor = self.actor()
                    if not actor:
                        self.send_json(401, {"error": "authentication_required"})
                        return
                    body = self.read_json()
                    prompt = body.get("layoutDescription") if body else None
                    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4_000:
                        self.send_json(400, {"error": "invalid_layout_description"})
                        return
                    try:
                        advisory, receipt = provider_call(config, prompt.strip())
                    except ProviderError:
                        self.send_json(502, {"error": "provider_unavailable"})
                        return
                    interaction_id = database.persist_interaction(
                        int(actor["id"]), prompt.strip(), advisory, config.openrouter_model, receipt
                    )
                    self.send_json(
                        200,
                        {
                            "advisory": advisory,
                            "interactionId": interaction_id,
                            "providerReceipt": receipt,
                        },
                    )
                    return
                self.send_json(404, {"error": "not_found"})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                self.log_message("request failed safely: %s", type(error).__name__)
                self.send_json(500, {"error": "internal_error"})

    return ThreadingHTTPServer(("127.0.0.1", config.api_port), APIHandler)


def main() -> int:
    try:
        config = RuntimeConfig.from_environment()
    except ValueError as error:
        print(f"runtime configuration error: {error}", file=sys.stderr)
        return 2
    if not config.database_path.is_file():
        print("runtime database is missing; run python3 -m runtime.prepare first", file=sys.stderr)
        return 2
    server = build_api_server(config)
    print(f"runtime API listening on http://127.0.0.1:{config.api_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
