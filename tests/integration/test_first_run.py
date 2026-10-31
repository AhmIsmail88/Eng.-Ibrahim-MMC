import json

from sqlalchemy import func, select

from eng_ibrahim.application.services.first_run_service import FirstRunInput, FirstRunService
from eng_ibrahim.application.services.settings_service import SettingsService
from eng_ibrahim.infrastructure.database.orm_models import (
    AppUser,
    Asset,
    AssetCategory,
    AuditLog,
    Currency,
    FailureCode,
    LocalRecoveryCode,
    MaintenanceTask,
    Unit,
    WorkOrder,
)
from eng_ibrahim.infrastructure.security.passwords import verify_secret


def _input(paths, **kw):
    base = dict(station_name_ar="محطة الاختبار", station_name_en="Test Station",
                currency_code="EGP", timezone="Africa/Cairo", username="admin",
                display_name="Admin", backup_folder=paths.backups, password=None)
    base.update(kw)
    if "password" not in kw:
        base["password"] = "Admin#2026"
    return FirstRunInput(**base)


def test_first_run_creates_owner_admin_with_password(ctx, paths):
    svc = FirstRunService(ctx.db)
    assert not ctx.settings.is_first_run_completed()
    res = svc.complete(_input(paths))
    assert res.ok and res.value.recovery_code
    assert ctx.settings.is_first_run_completed()
    assert ctx.settings.get("station_name_ar") == "محطة الاختبار"
    assert ctx.settings.get("currency_code") == "EGP"
    assert ctx.settings.get("local_login_enabled") is True
    with ctx.db.session() as s:
        user = s.scalar(select(AppUser))
        assert user.role == "admin" and user.password_hash
        assert s.scalar(select(func.count()).select_from(LocalRecoveryCode)) == 1
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_first_run_requires_a_password(ctx, paths):
    res = FirstRunService(ctx.db).complete(_input(paths, password=""))
    assert not res.ok and res.error_code == "err.password_required"
    assert not ctx.settings.is_first_run_completed()
    with ctx.db.session() as s:
        assert s.scalar(select(func.count()).select_from(AppUser)) == 0


def test_first_run_with_password_stores_only_hashes(ctx, paths):
    res = FirstRunService(ctx.db).complete(_input(paths, password="s3cret-pass"))
    assert res.ok
    code = res.value.recovery_code
    assert code and len(code.split("-")) == 4
    with ctx.db.session() as s:
        user = s.scalar(select(AppUser))
        assert verify_secret(user.password_hash, "s3cret-pass")
        rc = s.scalar(select(LocalRecoveryCode))
        assert rc.code_hash != code and verify_secret(rc.code_hash, code)
        audit = s.scalar(select(AuditLog))
        blob = (audit.after_json or "") + (audit.before_json or "")
        assert "s3cret-pass" not in blob and code not in blob
        assert json.loads(audit.after_json)["password_set"] is True


def test_seed_is_reference_only(ctx, paths):
    FirstRunService(ctx.db).complete(_input(paths))
    with ctx.db.session() as s:
        for model in (AssetCategory, FailureCode, MaintenanceTask, Unit, Currency):
            assert s.scalar(select(func.count()).select_from(model)) > 0
        # Phase 1/2 add operational tables, but the seed must leave them empty.
        assert s.scalar(select(func.count()).select_from(Asset)) == 0
        assert s.scalar(select(func.count()).select_from(WorkOrder)) == 0


def test_validation_errors_do_not_write(ctx, paths):
    svc = FirstRunService(ctx.db)
    for kw, code in [
        (dict(station_name_ar="", station_name_en=""), "err.station_name_required"),
        (dict(username="  "), "err.username_required"),
        (dict(password=""), "err.password_required"),
        (dict(password="short"), "err.password_too_short"),
        (dict(currency_code="XXX"), "err.currency_unknown"),
    ]:
        res = svc.complete(_input(paths, **kw))
        assert not res.ok and res.error_code == code
    assert not ctx.settings.is_first_run_completed()
    with ctx.db.session() as s:
        assert s.scalar(select(func.count()).select_from(AppUser)) == 0
        assert s.scalar(select(func.count()).select_from(Currency)) == 0  # seed rolled back


def test_second_completion_rejected(ctx, paths):
    svc = FirstRunService(ctx.db)
    assert svc.complete(_input(paths)).ok
    again = svc.complete(_input(paths, username="other"))
    assert not again.ok and again.error_code == "err.first_run_already_done"


def test_seed_idempotent(ctx):
    from eng_ibrahim.infrastructure.database.seed_reference_data import seed_reference_data
    with ctx.db.unit_of_work() as s:
        first = seed_reference_data(s)
    with ctx.db.unit_of_work() as s:
        second = seed_reference_data(s)
    assert sum(first.values()) > 0 and sum(second.values()) == 0


def test_settings_roundtrip(ctx):
    st = SettingsService(ctx.db)
    st.set("k", {"a": [1, 2], "ar": "عربي"})
    assert st.get("k") == {"a": [1, 2], "ar": "عربي"}
    st.set("k", 5)
    assert st.get("k") == 5 and st.get("missing", "d") == "d"
