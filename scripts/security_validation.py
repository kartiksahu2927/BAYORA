#!/usr/bin/env python3
"""Run Bayora's reproducible security validation from a source checkout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bayora.config import Settings  # noqa: E402
from bayora.service import BayoraService  # noqa: E402


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".bayora-validation")
    service = BayoraService(Settings.from_env(data_dir))
    actor = service.actor_for_user("security-admin")
    result = service.run_security_validation(actor)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
