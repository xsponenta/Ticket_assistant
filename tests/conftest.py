import sys
from pathlib import Path

# The scripts in src/data import each other as plain modules (they are run as `python src/data/x.py`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "data"))

# Project root, so tests can `from src import llm` (as when running `python -m pytest` from the root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
