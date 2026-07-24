from __future__ import annotations

import hmac
import sys
from pathlib import Path

from runtime.environment import read_environment

CANONICAL_BASE_URL = "https://openrouter.ai/api/v1"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_ai_environment.py PROJECT_ENV CANONICAL_ENV", file=sys.stderr)
        return 2
    project = read_environment(Path(sys.argv[1]))
    canonical = read_environment(Path(sys.argv[2]))
    for key in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        if not project.get(key) or not canonical.get(key):
            print(f"missing required {key}", file=sys.stderr)
            return 1
        if not hmac.compare_digest(project[key], canonical[key]):
            print(f"{key} does not match canonical configuration", file=sys.stderr)
            return 1
    if project.get("OPENROUTER_BASE_URL") != CANONICAL_BASE_URL:
        print("OPENROUTER_BASE_URL is not canonical", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
