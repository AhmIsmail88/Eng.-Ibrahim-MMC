import json
from pathlib import Path

from eng_ibrahim import config
from eng_ibrahim.domain.enums import Language
from eng_ibrahim.localization.service import Localizer

LOC = Path(config.project_root()) / "src/eng_ibrahim/localization"


def test_paths_layout(tmp_path):
    p = config.AppPaths(tmp_path / "X")
    p.ensure()
    assert p.db_file == p.data / "maintenance.sqlite3"
    for d in (p.data, p.attachments, p.backups, p.logs, p.exports, p.cache, p.config):
        assert d.is_dir()


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path / "custom"))
    assert config.default_data_root() == tmp_path / "custom"


def test_localization_files_have_identical_keys():
    ar = json.loads((LOC / "ar.json").read_text(encoding="utf-8"))
    en = json.loads((LOC / "en.json").read_text(encoding="utf-8"))
    assert set(ar) == set(en)
    assert all(v.strip() for v in ar.values()) and all(v.strip() for v in en.values())


def test_localizer_switch_params_and_fallback():
    loc = Localizer(Language.AR)
    assert loc.is_rtl and loc.tr("nav.settings") == "الإعدادات"
    loc.set_language("en")
    assert not loc.is_rtl and loc.tr("nav.settings") == "Settings"
    assert loc.tr("dashboard.welcome", station="X") == "Welcome to X"
    assert loc.tr("no.such.key") == "no.such.key"
