"""Convenience runner for Bayora local server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load .env into os.environ if present
env_file = ROOT / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

from bayora.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.extend(["serve", "--data-dir", ".bayora", "--host", "127.0.0.1", "--port", "8080"])
        raise SystemExit(main())
