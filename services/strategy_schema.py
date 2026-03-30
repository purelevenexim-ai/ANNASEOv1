import json
from pathlib import Path

SCHEMA_PATH = Path("docs/strategy_result_schema.json")


def load_strategy_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
