# Build & release (SPEC 26)

## Prerequisites
- Windows 10/11 x64, Python 3.12/3.13 x64, Inno Setup 6 (only for the installer).
- `pip install -r requirements.lock` (PySide6, SQLAlchemy, Alembic, argon2, xlsxwriter, openpyxl, qrcode, Pillow).

## Build
```powershell
.\scripts\build_windows.ps1                 # standalone (recommended)
.\scripts\build_windows.ps1 -Mode onefile   # only if it passes the full checklist
.\scripts\package_installer.ps1             # produces dist\installer\ENG_IBRAHIM_Installer_1.0.0_x64.exe
```
`build_windows.ps1` runs the test suite first and aborts on failure; it copies `assets/`,
`migrations/` and `SPEC.md` next to the executable because they are runtime data files.

## Non-negotiables
- The database, attachments, backups and logs live in `%LOCALAPPDATA%\ENG_IBRAHIM`, never in
  the install folder. Upgrading the EXE must never touch them (SPEC 19.2, 26.6).
- Uninstall keeps user data by default; there is no `[UninstallDelete]` for the data root.
- The app is unsigned unless a code-signing certificate is supplied: SmartScreen may warn.
  Never advise disabling Windows protections.
- Onefile is optional: it unpacks to a temp folder at runtime, so the DB must still point to
  `%LOCALAPPDATA%` and the checklist below must pass.

## Clean-machine checklist (SPEC 26.7)
1. Windows 10/11 x64 with **no Python** installed, standard (non-admin) user.
2. Install → First Run Wizard → Dashboard loads.
3. Add asset, PM plan, part; receive stock; issue to a work order; complete & close it.
4. Export one report to PDF and XLSX; verify Arabic text and numbers.
5. Backup → close → reinstall/upgrade → data still present.
6. Restore the backup on a second Windows user; verify assets, attachments and stock.
7. Check RTL/LTR, dark/light, 1366×768 and 150% scaling, no missing Qt platform plugin.

## Known gaps (1.0)
- No code signing certificate by default.
- Installer is Arabic/English (picked from the Windows display language).
- Signing: set `ENG_IBRAHIM_SIGN_CERT` (.pfx) and `ENG_IBRAHIM_SIGN_PASSWORD`; both build
  scripts then sign the EXE and the installer via `scripts/sign.ps1` (needs the Windows SDK).
