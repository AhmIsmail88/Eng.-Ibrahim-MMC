# Changelog

## 0.11.0 — Packaging assets (Phase 7)
- `installer/installer.iss` (Inno Setup 6): per-user install, shortcuts, official icon,
  no `[UninstallDelete]` for user data.
- `scripts/build_windows.ps1` (tests first, then pyside6-deploy, copies assets/migrations/SPEC)
  and `scripts/package_installer.ps1` (locates ISCC and compiles).
- `docs/BUILD_AND_RELEASE.md` with the clean-machine checklist and the non-negotiables
  (data stays in %LOCALAPPDATA%, unsigned EXE warns SmartScreen, onefile is optional).
- Version aligned to 0.10.0 across app, pyproject and installer (1.0.0 only after the checklist).

## 0.10.0 — Backup & restore engine (SPEC 23)
- `BackupService.create()`: SQLite online-backup snapshot (WAL-safe), `integrity_check`
  before writing, attachments included, `manifest.json` with per-file SHA-256, ZIP written
  as `.tmp` then renamed, and a `backup_history` row only after success.
- `verify()` re-hashes the database and every attachment and refuses a corrupted archive.
- `restore()`: verify → pre-restore safety backup → dispose connections → atomic replace of
  DB + attachments. A corrupt archive can never touch current data.
- 4 new tests, including a real restore that brings the asset list back.
## 0.9.0 — Attachments (SPEC 22)
- Migration 0007: `attachments` metadata (owner, relative path, size, sha256, actor).
- `AttachmentService`: copies into `<DATA_ROOT>/attachments/<owner>/<owner_id>/<uuid>.<ext>`,
  20 MB limit, allow-list of extensions, path-traversal safe (stored name is a UUID),
  SHA-256 per file, atomic temp→final move, and rollback of the file if the DB insert fails.
- `integrity_scan()` reports rows whose file is missing and orphan files with no row.
- Asset profile gained an “Attachments” tab (add / open). 151 automated tests.

## 0.8.0 — Official logo + Phase 5b reports (REP-003, REP-006)
- Official icon installed: `assets/icons/ENG_IBRAHIM_Icon.ico` (16–256 px) and `.png`.
  The placeholder path is no longer used (SPEC 3.1 / IMP-005 closed).
- REP-003 PM schedule and REP-006 individual work order (tasks, parts used, cost,
  signature lines) added to the report engine and the Reports screen (work-order picker).
- 146 automated tests (unit / integration / UI smoke).

## 0.7.0 — Phase 5a: reporting engine + 4 reports (ADR-035)
- `ReportService` with REP-001 (equipment register), REP-005 (work orders register),
  REP-009 (stock balance), REP-013 (maintenance cost), sharing one query per report between
  preview and exports.
- XLSX writer (xlsxwriter): RTL sheet, frozen header, autofilter, real numbers, and
  formula-injection protection for text cells.
- PDF writer through Qt `QTextDocument`/`QPdfWriter`: RTL HTML table, Arabic font fallback,
  repeated header, totals line.
- New Reports screen: report picker, period filters, live preview, export to PDF/XLSX.
- 144 automated tests (unit / integration / UI smoke).

## 0.6.0 — Phase 3b: inspection templates & execution (ADR-034)
- `InspectionService`: templates with ordered items (pass/fail, yes/no, done/NA, numeric,
  text, photo), start an inspection against an asset (optionally linked to a work order),
  answer items, and complete only when every required item is answered.
- Each answer snapshots its item definition, so editing a template later cannot rewrite
  a completed inspection.
- New Inspections screen: template list + create dialog, run list, fill dialog and complete.
- 139 automated tests (unit / integration / UI smoke).

## 0.5.0 — Phase 4: spare parts, stock ledger, WAC costing (ADR-033)
- Schema 0006: `warehouses`, `parts`, `part_compatibility`, `stock_movements`,
  `stock_balances`, `stock_reservations` + the read-only `work_order_part_usage` view.
- `InventoryService`: receive with moving weighted average, issue to a work order,
  linked returns (never above the original issue), adjustments, reservations, low-stock listing.
- Negative stock is impossible: the check runs inside the same transaction that writes the
  movement and the cached balance.
- `WorkOrderService.cost` now adds the net parts value, so a work order total is
  parts + labour + external (completeness flags only for real gaps).
- `asset_part_usage()` gives the field the owner asked for: part, quantity, value, date,
  the technician who fitted it, the work order, the supplier and the purchase reference.
- New Spare parts screen (catalog, receipt, issue, adjust, movement history) and a
  “Parts used” tab on the asset profile.
- 132 automated tests (unit / integration / UI smoke).

## 0.4.0 — Phase 3a: preventive maintenance (ADR-032)
- Schema 0005: `pm_plans`, `pm_plan_tasks`, `pm_occurrences`, plus the inspection tables
  (`inspection_templates`, `inspection_template_items`, `inspections`, `inspection_answers`)
  that Phase 3b will use.
- `domain/policies/pm_schedule.py`: pure calendar/meter rules — CLAMP_TO_LAST_DAY, FIRST_DUE,
  warning windows, and catch-up arithmetic, with their own tests.
- `PMService`: create plans (date/meter/first-due), unique occurrence per due anchor
  (`plan_id + due_key`), generate a PM work order exactly once, skip with reason,
  pause/resume, and advance the next due when the PM work order is completed.
- `WorkOrderService` now calls the PM completion hook inside the same transaction, so
  “PM closed” and “next due moved” cannot drift apart.
- New Preventive maintenance screen: plan list with live due state, plan tasks, occurrence
  history, Generate / Skip / Pause actions.
- 122 automated tests (unit / integration / UI smoke).

## 0.3.0 — Phase 2: failures, work orders, downtime, dashboard board (ADR-031)
- Schema 0004: `failure_reports`, `work_orders`, `work_order_tasks`, `work_order_assignments`,
  `work_order_time_logs`, `work_order_status_events`, `work_order_external_expenses`,
  `downtime_events`.
- `domain/policies/wo_state_machine.py`: the 14 SPEC 10.3.1 transitions as data, with guards,
  required fields and minimum role; services and tests both consume it.
- `WorkOrderService`: create, create-from-failure, transitions, assignment, tasks, time logs
  (overlap check + rate snapshot), external expenses, cost stub, detail with history.
- `FailureService`: register/triage/resolve/cancel; conversion marks the report `Converted`
  and refuses a second work order.
- `DowntimeService`: one open event per asset, no negative durations.
- `DashboardService` + dashboard screen: 4 KPI counts and the asset status board
  (running / faulty / under maintenance / retired, fault and repair dates, open WO, conflict flag).
- New screens: Work orders (actions per state machine, tasks, time logs, history) and
  Failure reports (register, triage, convert, resolve, cancel).
- 107 automated tests (unit / integration / UI smoke).

## 0.2.0 — Phase 1: assets, meters, Arabic search (ADR-030)
- Schema 0003: `assets`, `asset_specifications`, `asset_location_history`,
  `asset_status_history`, `vehicles`, `meter_definitions`, `meter_readings`,
  `technicians`, `suppliers`, `operating_calendars` (+ shifts, exceptions).
- `AssetService`: create/update/archive/restore, status change, location move with history,
  parent-cycle prevention, case-insensitive unique code, Arabic-normalized search.
- `MeterService`: default meter from `assets.meter_type`, cumulative readings cannot go
  backwards, documented corrections keep the original row.
- `MasterDataService`: lookups + create for locations/categories/technicians/suppliers/calendars.
- New Assets screen: filters, search, profile tabs (overview / technical / meters / history),
  create/edit dialog, add reading, add technical item.
- Seed now creates one root location `MAIN` (reference data, no demo assets).
- 87 automated tests (unit / integration / UI smoke).

## 0.1.1 — Users, permissions, EGP (ADR-025..029)
- Local accounts with Argon2id passwords; login screen when more than one active user
  (single password-less owner still runs in owner mode).
- Four roles enforced in the services: `admin`, `editor`, `reports`, `viewer`
  (view / edit / view + print). New Users & permissions page for admins.
- Last active admin cannot be demoted or disabled; a user cannot disable their own account.
- First Run now requires a password and creates a one-time recovery code.
- Base currency defaults to **EGP**; the wizard still lists every seeded ISO currency.
- Migration 0002 rebuilds a legacy `app_users` (roles collapsed, password-less accounts
  marked for reset); fresh databases get the new shape from 0001.
- 55 automated tests (unit / integration / UI smoke).

## 0.1.0 — Phase 0 (Bootstrap / Foundation)
- Project skeleton (layers: domain / application / infrastructure / presentation).
- PySide6 shell: header, collapsible sidebar (11 sections), status bar, Light/Dark theme,
  Arabic RTL / English LTR with live switching, window geometry persistence.
- First Run Wizard (6 steps) -> settings, owner user (optional Argon2id password + recovery code),
  reference seed (no fake operational data), audit entry; one transaction.
- SQLite engine + Alembic migration 0001, safe startup (quick_check, pre-migration backup,
  never overwrite a damaged DB), single-instance lock, rotating logs, crash handler.
- 34 automated tests (unit / integration / UI smoke).
