from __future__ import annotations

import contextlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from runtime.companion import (
    ProviderError,
    RuntimeConfig,
    RuntimeDatabase,
    build_api_server,
    prepare_database,
)

EMAIL = "runtime-admin@example.com"
PASSWORD = "RuntimeAcceptance123!"


class CompanionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database_path = Path(self.temporary.name) / "companion.sqlite3"
        prepare_database(self.database_path, EMAIL, PASSWORD)
        self.config = RuntimeConfig(
            api_port=0,
            ui_origin="http://127.0.0.1:31005",
            database_path=self.database_path,
            openrouter_api_key="test-key",
            openrouter_model="test-model",
            openrouter_base_url="https://openrouter.ai/api/v1",
        )

    def start_server(self, provider):
        server = build_api_server(self.config, provider)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, method: str, path: str, body=None, token: str | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        headers = {"Content-Type": "application/json", "Origin": self.config.ui_origin}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = json.dumps(body) if body is not None else None
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        decoded = json.loads(response.read().decode("utf-8"))
        status = response.status
        response_headers = dict(response.getheaders())
        connection.close()
        return status, decoded, response_headers

    def login(self, server) -> str:
        status, body, _ = self.request(
            server,
            "POST",
            "/api/auth/login",
            {"email": EMAIL, "password": PASSWORD},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["email"], EMAIL)
        return body["token"]

    def test_database_backed_login_and_identity(self) -> None:
        server = self.start_server(lambda config, prompt: ("unused", {"requestId": "unused"}))
        token = self.login(server)
        status, body, headers = self.request(server, "GET", "/api/auth/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["email"], EMAIL)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.config.ui_origin)
        bad_status, _, _ = self.request(
            server,
            "POST",
            "/api/auth/login",
            {"email": EMAIL, "password": "wrong"},
        )
        self.assertEqual(bad_status, 401)

    def test_anonymous_rejection_and_successful_provider_receipt_persistence(self) -> None:
        receipt = {"requestId": "or-test-123", "provider": "openrouter", "upstreamModel": "test-model"}
        server = self.start_server(lambda config, prompt: ("Use proportional spacing and compression priorities.", receipt))
        anonymous_status, _, _ = self.request(
            server,
            "POST",
            "/api/ai/stack-layout-advisory",
            {"layoutDescription": "A vertical stack clips two buttons."},
        )
        self.assertEqual(anonymous_status, 401)
        token = self.login(server)
        status, body, _ = self.request(
            server,
            "POST",
            "/api/ai/stack-layout-advisory",
            {"layoutDescription": "A vertical stack clips two buttons."},
            token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["providerReceipt"]["requestId"], "or-test-123")
        self.assertGreater(body["interactionId"], 0)
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT prompt, response, provider_receipt FROM ai_interactions WHERE id = ?",
                (body["interactionId"],),
            ).fetchone()
        self.assertEqual(row[0], "A vertical stack clips two buttons.")
        self.assertIn("compression priorities", row[1])
        self.assertEqual(json.loads(row[2])["requestId"], "or-test-123")

    def test_provider_failure_has_no_pending_row_traceback_or_query_string_log(self) -> None:
        def fail_provider(config, prompt):
            raise ProviderError("simulated private upstream detail")

        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            server = self.start_server(fail_provider)
            token = self.login(server)
            before = RuntimeDatabase(self.database_path).interaction_count()
            status, body, _ = self.request(
                server,
                "POST",
                "/api/ai/stack-layout-advisory?secret=must-not-appear",
                {"layoutDescription": "A horizontal stack overflows."},
                token,
            )
            after = RuntimeDatabase(self.database_path).interaction_count()
        self.assertEqual(status, 502)
        self.assertEqual(body, {"error": "provider_unavailable"})
        self.assertEqual(before, after)
        self.assertNotIn("Traceback", log.getvalue())
        self.assertNotIn("must-not-appear", log.getvalue())
        self.assertNotIn("private upstream detail", log.getvalue())

    def test_interaction_ledger_is_append_only(self) -> None:
        database = RuntimeDatabase(self.database_path)
        user_id = database.authenticate(EMAIL, PASSWORD)
        self.assertIsNotNone(user_id)
        interaction_id = database.persist_interaction(
            int(user_id),
            "prompt",
            "response",
            "test-model",
            {"requestId": "receipt"},
        )
        with sqlite3.connect(self.database_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE ai_interactions SET response = 'changed' WHERE id = ?", (interaction_id,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM ai_interactions WHERE id = ?", (interaction_id,))

    def test_ui_contains_real_login_and_advisory_forms(self) -> None:
        ui_root = Path(__file__).resolve().parent.parent / "ui"
        html = (ui_root / "index.html").read_text(encoding="utf-8")
        script = (ui_root / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="login-form"', html)
        self.assertIn('type="email"', html)
        self.assertIn('type="password"', html)
        self.assertIn('id="advisory-form"', html)
        self.assertIn("/api/auth/login", script)
        self.assertIn("/api/auth/me", script)
        self.assertIn("/api/ai/stack-layout-advisory", script)


if __name__ == "__main__":
    unittest.main()
