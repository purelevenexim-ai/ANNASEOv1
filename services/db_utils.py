from typing import Any, Dict, List, Optional


def row_to_dict(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Convert a sqlite3.Row (or any mapping) into a dict, preserving None."""
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        # Fallback for non-mapping types: keep as-is for outer layer handling
        return row


def rows_to_dicts(rows: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to list of dicts."""
    if not rows:
        return []
    return [dict(r) for r in rows]
