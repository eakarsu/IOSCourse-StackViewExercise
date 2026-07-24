from __future__ import annotations

import os
from pathlib import Path

from runtime.companion import RuntimeConfig, prepare_database
from runtime.environment import read_environment


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    values = read_environment(root / ".env")
    os.environ.update(values)
    config = RuntimeConfig.from_environment()
    email = values.get("PROVISION_ADMIN_EMAIL", "")
    password = values.get("PROVISION_ADMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit("provisioning credentials are required")
    prepare_database(config.database_path, email, password)
    print("runtime database prepared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
