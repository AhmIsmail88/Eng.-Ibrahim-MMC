import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from eng_ibrahim.app import build_context
from eng_ibrahim.config import AppPaths


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    p = AppPaths(tmp_path / "ENG_IBRAHIM")
    p.ensure()
    return p


@pytest.fixture
def ctx(paths):
    context, _ = build_context(paths)
    yield context
    context.db.dispose()
