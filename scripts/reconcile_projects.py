#!/usr/bin/env python3
"""Reconcile projects between main DB and KI/strategy tables.

Usage:
  python3 scripts/reconcile_projects.py [--apply]

--apply will perform changes; without it the script runs in dry-run mode.
"""
import sqlite3, json, sys, os, argparse

parser = argparse.ArgumentParser(__doc__)
parser.add_argument('--apply', action='store_true', help='Perform changes (default: dry-run)')
parser.add_argument('--db', default=os.getenv('ANNASEO_DB', 'annaseo.db'),
                    help='Path to the SQLite DB file (default: annaseo.db or $ANNASEO_DB)')
args = parser.parse_args()
apply_changes = args.apply
DB = args.db

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('Connected to', DB)

# 1) Find projects that have owner_id but missing user_projects mapping
rows = cur.execute("SELECT project_id, owner_id FROM projects WHERE owner_id IS NOT NULL AND owner_id!='' ").fetchall()
missing_mappings = []
for r in rows:
    pid = r['project_id']
    uid = r['owner_id']
    exists = cur.execute('SELECT 1 FROM user_projects WHERE project_id=? AND user_id=?',(pid,uid)).fetchone()
    if not exists:
        missing_mappings.append((pid, uid))

print('\nProjects with owner_id but missing user_projects mapping:', len(missing_mappings))
for pid, uid in missing_mappings[:50]:
    print('  ', pid, 'owner->', uid)

if apply_changes and missing_mappings:
    for pid, uid in missing_mappings:
        print('Inserting mapping', uid, pid)
        cur.execute('INSERT OR IGNORE INTO user_projects(user_id,project_id,role)VALUES(?,?,?)',(uid,pid,'owner'))
    conn.commit()
    print('Inserted', len(missing_mappings), 'user_projects mappings')

# 2) Find project_ids present in KI or strategy tables but missing from projects table
sources = [
    ('keyword_input_sessions','project_id'),
    ('strategy_sessions','project_id'),
    ('runs','project_id'),
]
found = set()
for table,col in sources:
    try:
        rows = cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL AND {col}!='' ").fetchall()
        for r in rows:
            found.add(r[0])
    except Exception:
        pass

proj_rows = cur.execute("SELECT DISTINCT project_id FROM projects").fetchall()
proj_set = set(r[0] for r in proj_rows)
missing_projects = sorted([p for p in found if p not in proj_set])
print('\nProject IDs referenced in other tables but missing from projects:', len(missing_projects))
for p in missing_projects[:50]: print('  ', p)

if apply_changes and missing_projects:
    import time, hashlib
    for p in missing_projects:
        name = f'imported-{p}'
        owner = ''
        pid = p
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        print('Creating placeholder project', pid)
        cur.execute('INSERT OR IGNORE INTO projects(project_id,name,industry,description,seed_keywords,owner_id,created_at,updated_at)VALUES(?,?,?,?,?,?,?,?)',
                    (pid,name,'general','Imported placeholder',json.dumps([]),owner,now,now))
    conn.commit()
    print('Created', len(missing_projects), 'placeholder projects')

conn.close()
print('\nDone. (use --apply to change DB)')
