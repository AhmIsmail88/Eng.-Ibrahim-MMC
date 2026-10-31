from eng_ibrahim.infrastructure.security.passwords import (
    generate_recovery_code,
    hash_secret,
    verify_secret,
)
from eng_ibrahim.infrastructure.storage.preferences import PreferencesStore


def test_argon2id_hash_and_verify():
    h = hash_secret("correct horse")
    assert h.startswith("$argon2id$") and "correct horse" not in h
    assert verify_secret(h, "correct horse")
    assert not verify_secret(h, "wrong")
    assert not verify_secret("garbage", "x")
    assert hash_secret("a") != hash_secret("a")  # random salt


def test_recovery_code_format():
    code = generate_recovery_code()
    parts = code.split("-")
    assert len(parts) == 4 and all(len(p) == 5 for p in parts)
    assert generate_recovery_code() != code


def test_preferences_roundtrip_and_corruption(tmp_path):
    f = tmp_path / "cfg" / "user_preferences.json"
    s = PreferencesStore(f)
    assert s.get("language") == "ar" and s.get("theme") == "light"
    s.set("language", "en")
    s.set("theme", "dark")
    s2 = PreferencesStore(f)
    assert (s2.get("language"), s2.get("theme")) == ("en", "dark")
    f.write_text("{not json", encoding="utf-8")
    assert PreferencesStore(f).get("language") == "ar"  # falls back, does not crash
