"""Entry point only. All logic lives in src/eng_ibrahim."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from eng_ibrahim.app import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
