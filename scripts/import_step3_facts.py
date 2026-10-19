"""Command-line wrapper for the optional Step 3 source fact importer."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dev import environment
os.environ.update(environment())

from backend.fact_importer import main


if __name__ == '__main__':
    main()
