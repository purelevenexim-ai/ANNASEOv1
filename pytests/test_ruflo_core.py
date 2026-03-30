import threading
import time
import os, sys

# Ensure repo root is on sys.path for imports when pytest runs from different cwd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engines.ruflo_20phase_engine import P5_IntentClassification, P8_TopicDetection, MemoryManager


def test_p5_classify_returns_tuple():
    p5 = P5_IntentClassification()
    intent, conf = p5._classify("buy red shoes")
    assert isinstance(intent, str)
    assert isinstance(conf, float)


def test_p8_phrase_match():
    p8 = P8_TopicDetection()
    assert p8._is_phrase_match("best coffee maker", "coffee maker review")
    assert not p8._is_phrase_match("apple pie recipe", "running shoes")


def _toggle_heavy(phase, delay=0.1):
    ok, reason = MemoryManager.can_run(phase)
    if ok:
        MemoryManager.acquire(phase)
        time.sleep(delay)
        MemoryManager.release(phase)


def test_memory_manager_threadsafe():
    # Simulate two threads trying to acquire the same heavy phase
    phase = "P8"
    t1 = threading.Thread(target=_toggle_heavy, args=(phase, 0.3))
    t2 = threading.Thread(target=_toggle_heavy, args=(phase, 0.1))
    t1.start(); t2.start()
    t1.join(); t2.join()
    # After both threads, no active heavy phases should remain
    assert not MemoryManager._active_heavy
