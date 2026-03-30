"""
Test research schema tables in annaseo_wiring.py
"""
import sqlite3
from pathlib import Path


def test_keyword_research_sessions_table_exists():
    """Test that keyword_research_sessions table is created."""
    db_path = Path("./annaseo.db")
    if db_path.exists():
        db_path.unlink()  # Start fresh

    from annaseo_wiring import setup_research_tables
    setup_research_tables()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_research_sessions'")
    assert cursor.fetchone() is not None
    conn.close()


def test_research_results_table_exists():
    """Test that research_results table is created."""
    from pathlib import Path
    db_path = Path("./annaseo.db")

    from annaseo_wiring import setup_research_tables
    setup_research_tables()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='research_results'")
    assert cursor.fetchone() is not None
    conn.close()


def test_research_indexes_exist():
    """Test that proper indexes are created."""
    from annaseo_wiring import setup_research_tables

    setup_research_tables()

    conn = sqlite3.connect(str(Path("./annaseo.db")))
    cursor = conn.cursor()

    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_research%'")
    indexes = cursor.fetchall()
    assert len(indexes) >= 2
    conn.close()
