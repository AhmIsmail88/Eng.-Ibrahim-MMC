"""List local users or reset one password (offline, same machine).

Usage:
    python scripts/reset_password.py --list
    python scripts/reset_password.py --user admin --password "NewPass#2026"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select  # noqa: E402

from eng_ibrahim.config import APP_DIR_NAME, get_paths  # noqa: E402
from eng_ibrahim.infrastructure.database.engine import Database  # noqa: E402
from eng_ibrahim.infrastructure.database.orm_models import AppUser  # noqa: E402
from eng_ibrahim.infrastructure.security.passwords import hash_secret  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ENG. IBRAHIM — local accounts")
    parser.add_argument("--list", action="store_true", help="show users")
    parser.add_argument("--user", help="username to reset")
    parser.add_argument("--password", help="new password (min 8 characters)")
    args = parser.parse_args()

    paths = get_paths()
    if not paths.db_file.exists():
        print(f"No database at {paths.db_file}")
        print(f"Start the app once (it creates {APP_DIR_NAME} under %LOCALAPPDATA%), "
              "or set ENG_IBRAHIM_DATA_DIR.")
        return 1
    db = Database(paths.db_file)
    try:
        if args.list or not args.user:
            with db.session() as s:
                rows = s.scalars(select(AppUser).order_by(AppUser.username)).all()
                if not rows:
                    print("No users yet — finish the First Run Wizard in the app.")
                for row in rows:
                    print(f"{row.username:<24} role={row.role:<8} "
                          f"active={'yes' if row.is_active else 'no'} "
                          f"password={'set' if row.password_hash and not row.password_hash.startswith('!') else 'none'}")
            return 0
        if not args.password or len(args.password) < 8:
            print("Password must be at least 8 characters.")
            return 2
        with db.unit_of_work() as s:
            row = s.scalar(select(AppUser).where(
                func.lower(AppUser.username) == args.user.strip().lower()))
            if row is None:
                print(f"User not found: {args.user}")
                return 3
            row.password_hash = hash_secret(args.password)
            row.is_active = 1
        print(f"Password updated for {args.user}.")
        return 0
    finally:
        db.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
