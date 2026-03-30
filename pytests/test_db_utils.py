import sqlite3

from services.db_utils import row_to_dict, rows_to_dicts


def test_row_to_dict_handles_none():
    assert row_to_dict(None) is None


def test_row_to_dict_sqlite_row():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
    cur.execute("INSERT INTO foo (id, name) VALUES (?, ?)", (1, "test"))
    row = cur.execute("SELECT id, name FROM foo WHERE id=1").fetchone()
    d = row_to_dict(row)
    assert d == {"id": 1, "name": "test"}


def test_rows_to_dicts_sqlite_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("CREATE TABLE foo (id INTEGER)")
    cur.executemany("INSERT INTO foo (id) VALUES (?)", [(1,), (2,), (3,)])
    rows = cur.execute("SELECT id FROM foo ORDER BY id").fetchall()
    result = rows_to_dicts(rows)
    assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
