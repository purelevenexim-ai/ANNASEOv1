from dataclasses import dataclass
import json
from typing import Dict, List
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INV_PATH = ROOT / "tools" / "phase_prompt_inventory.json"


def load_inventory() -> dict:
    if not INV_PATH.exists():
        return {}
    return json.loads(INV_PATH.read_text())


@dataclass
class SeedStub:
    id: str
    keyword: str
    region: str = "global"


def make_sample_seed(keyword: str = "cinnamon") -> SeedStub:
    return SeedStub(id=f"seed_{keyword.replace(' ','_')}", keyword=keyword)


def make_sample_topic_map() -> Dict[str, List[str]]:
    """Return a representative topic_map used as input to P9 in tests.

    Format: {topic_name: [keyword1, keyword2, ...], ...}
    """
    return {
        "Cinnamon Health": ["cinnamon blood sugar", "cinnamon cholesterol"],
        "Cinnamon Recipe": ["cinnamon rolls", "cinnamon sugar"],
        "Cinnamon Uses": ["cinnamon tea", "cinnamon oil"],
        "Cinnamon Cooking": ["cinnamon pancakes", "cinnamon french toast"],
        "Cinnamon Buying": ["buy cinnamon", "cinnamon price"],
        "Cinnamon Varieties": ["ceylon cinnamon", "cassia cinnamon"],
    }


def get_phase_info(phase: str) -> dict:
    inv = load_inventory()
    return inv.get(phase, {})


__all__ = ["load_inventory", "SeedStub", "make_sample_seed", "make_sample_topic_map", "get_phase_info"]
