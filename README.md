# ENG. IBRAHIM — Maintenance Management System (CMMS)

Offline, single-PC Windows desktop app. Python + PySide6 + SQLite. Spec: `SPEC.md`.
**Status: Phase 4 complete + Phase 3b** — foundation, accounts, assets & meters, failures &
work orders, preventive maintenance, inspections, spare parts with a stock ledger, dashboard
status board, and a reporting engine with PDF/XLSX export (4 of 6 P0 reports).
Reports (PDF/XLSX), backup/restore, import and users are in. Version 0.10.0 is the
release candidate; the installer scripts live in `scripts/` (see docs/BUILD_AND_RELEASE.md).

## Accounts (1.0)
First run creates the owner/admin account with a password (Argon2id) and shows a one-time
recovery code. The admin creates users and grants one of: view only, editor, or
view + print/export reports. Permissions are enforced in the application services, not
just by hiding buttons. The wizard always sets a password; owner mode (one password-less
account) is only a compatibility path for older databases.

## Run (Windows PowerShell)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock
python main.py
```
Data lives in `%LOCALAPPDATA%\ENG_IBRAHIM\` (database, logs, backups, preferences) — never in the
project/EXE folder. Base currency defaults to **EGP**. Set `ENG_IBRAHIM_DATA_DIR` to use another
folder (e.g. for testing).

## Test
```powershell
pip install -r requirements-dev.lock
$env:QT_QPA_PLATFORM="offscreen"   # optional: no windows pop up
python -m pytest -q
ruff check src tests
python scripts/check_database.py   # read-only DB health check
```

## Layout
`src/eng_ibrahim/{domain,application,infrastructure,presentation,localization}` — see SPEC 20.2.
Decisions and deviations: `docs/DECISIONS.md`. Schema: `docs/DATABASE_SCHEMA.md`.

## Brand assets
Official icon: `assets/icons/ENG_IBRAHIM_Icon.ico` (16–256 px) + `.png`, loaded automatically.
The drawn placeholder remains only as a fallback if the files are removed.
