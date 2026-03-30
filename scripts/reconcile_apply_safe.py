#!/usr/bin/env python3
"""Safe runner for `scripts/reconcile_projects.py`.

Creates a timestamped backup of the SQLite DB file before running the reconciliation
with `--apply`. By default this creates a backup; use `--no-backup` to skip.

Usage:
  python3 scripts/reconcile_apply_safe.py --db /path/to/annaseo.db

This script is intentionally conservative: it refuses to run if the DB file is
missing.
"""
import argparse, shutil, time, subprocess, os, sys


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--db', required=True, help='Path to SQLite DB file')
    parser.add_argument('--no-backup', action='store_true', help='Skip automatic backup (not recommended)')
    parser.add_argument('--dry-run', action='store_true', help='Run reconcile in dry-run mode (no --apply)')
    args = parser.parse_args()

    db = args.db
    if not os.path.exists(db):
        print('ERROR: DB file not found:', db)
        sys.exit(2)

    if not args.no_backup:
        ts = time.strftime('%Y%m%dT%H%M%S')
        backup = f"{db}.bak.{ts}"
        print('Creating backup:', backup)
        shutil.copy2(db, backup)
        print('Backup created:', backup)

    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), 'reconcile_projects.py')]
    if not args.dry_run:
        cmd.append('--apply')
    cmd.extend(['--db', db])

    print('Running:', ' '.join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print('reconcile_projects.py exited with', rc)
        sys.exit(rc)

    print('Done.')


if __name__ == '__main__':
    main()
