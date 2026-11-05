#!/usr/bin/env python3
"""Repository-root entrypoint for the industry fund-flow rotation tool."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "skills" / "deep-analysis" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rotate import main  # noqa: E402

if __name__ == "__main__":
    main()
