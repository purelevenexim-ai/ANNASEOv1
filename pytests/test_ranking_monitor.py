import uuid
from services.ranking_monitor import RankingMonitor
from main import get_db


def test_ranking_monitor_detect_drop():
    rm = RankingMonitor()
    h = [10, 8, 7, 6]
    out = rm.detect_drop(h)
    assert out['drop_detected'] is True
    assert out['drop_magnitude'] >= 0


def test_ranking_monitor_analyze_serp_shift():
    rm = RankingMonitor()
    out = rm.analyze_serp_shift('best spices for chicken')
    assert 'serp_summary' in out
    assert 'gaps' in out
