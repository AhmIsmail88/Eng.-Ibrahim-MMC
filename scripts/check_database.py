"""Read-only database health check:  python scripts/check_database.py [path-to-db]
Never modifies the database."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eng_ibrahim.config import get_paths  # noqa: E402
from eng_ibrahim.infrastructure.database.migration_runner import head_revision  # noqa: E402


def main() -> int:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else get_paths().db_file
    if not db.exists():
        print(f"NOT FOUND: {db}")
        return 2
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        try:
            rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            rev = rev[0] if rev else None
        except sqlite3.DatabaseError:
            rev = None
    finally:
        conn.close()
    head = head_revision()
    print(f"file: {db}\nintegrity_check: {integrity}\nforeign_key_violations: {len(fk)}")
    print(f"schema revision: {rev} (app head: {head})")
    return 0 if integrity == "ok" and not fk and rev == head else 1


if __name__ == "__main__":
    sys.exit(main())
