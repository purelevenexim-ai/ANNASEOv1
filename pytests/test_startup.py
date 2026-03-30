import sys, os
# Ensure repository root is on sys.path for imports during pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import health, system_status


def test_health_function_direct():
    data = health()
    assert isinstance(data, dict)
    assert "database" in data


def test_system_status_function_direct():
    data = system_status()
    assert isinstance(data, dict)
    assert "timestamp" in data
    assert "claude" in data
