"""
Humanization V2 Bandit — epsilon-greedy multi-armed bandit that learns
which V2Config produces the lowest AI-detection score over time.

Each pipeline run:
  1. `select()` picks an arm (config) before the run
  2. `update(arm_idx, final_score)` is called after step 11 with the
     resulting AI-detection score (higher = more human-like)

State persists to `data/humanization_bandit.json` so learning survives
restarts.  Module-level singleton `_bandit` is used by the pipeline.
"""
import json
import logging
import os
import random
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

from engines.humanize.humanization_v2 import V2Config

log = logging.getLogger("annaseo.humanize.bandit")

_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "humanization_bandit.json")
_STATE_PATH = os.path.normpath(_STATE_PATH)


# ── Preset arms ───────────────────────────────────────────────────────────────

_ARMS: List[V2Config] = [
    V2Config(structure_chaos=0.20, cognitive_noise=0.15, persona_drift=0.20, seed=10),  # 0: light
    V2Config(structure_chaos=0.30, cognitive_noise=0.20, persona_drift=0.25, seed=20),  # 1: balanced (default)
    V2Config(structure_chaos=0.40, cognitive_noise=0.30, persona_drift=0.30, seed=30),  # 2: heavy
    V2Config(structure_chaos=0.25, cognitive_noise=0.10, persona_drift=0.15, seed=40),  # 3: minimal
]

_ARM_NAMES = ["light", "balanced", "heavy", "minimal"]


# ── Bandit class ──────────────────────────────────────────────────────────────

class HumanizationBandit:
    """Epsilon-greedy bandit over V2Config arms.

    Q-values represent expected AI-detection score (0–100, higher = better).
    EMA update: Q[a] = alpha * Q[a] + (1 - alpha) * reward
    """

    _ALPHA = 0.10   # EMA smoothing factor
    _INITIAL_Q = 60.0  # optimistic start (encourages exploration early)

    def __init__(self) -> None:
        self._q: List[float] = [self._INITIAL_Q] * len(_ARMS)
        self._counts: List[int] = [0] * len(_ARMS)
        self._total_updates: int = 0
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if os.path.exists(_STATE_PATH):
                with open(_STATE_PATH, "r") as f:
                    state = json.load(f)
                q = state.get("q_values", [])
                counts = state.get("counts", [])
                if len(q) == len(_ARMS):
                    self._q = [float(v) for v in q]
                if len(counts) == len(_ARMS):
                    self._counts = [int(v) for v in counts]
                self._total_updates = int(state.get("total_updates", 0))
                log.debug("Bandit state loaded: %d updates, Q=%s", self._total_updates, [round(v, 1) for v in self._q])
        except Exception as e:
            log.warning("Bandit: could not load state (%s) — starting fresh", e)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
            state = {
                "q_values": [round(v, 4) for v in self._q],
                "counts": self._counts,
                "arm_names": _ARM_NAMES,
                "total_updates": self._total_updates,
                "arms": [asdict(a) for a in _ARMS],
            }
            tmp = _STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, _STATE_PATH)
        except Exception as e:
            log.warning("Bandit: could not save state: %s", e)

    # ── Core API ───────────────────────────────────────────────────────────────

    def select(self, epsilon: float = 0.15) -> Tuple[V2Config, int]:
        """Choose an arm via epsilon-greedy policy.

        Args:
            epsilon: Exploration probability (0–1).  Default 0.15.

        Returns:
            (V2Config, arm_index) tuple.
        """
        if random.random() < epsilon:
            idx = random.randrange(len(_ARMS))
            log.debug("Bandit: exploring — arm %d (%s)", idx, _ARM_NAMES[idx])
        else:
            idx = max(range(len(self._q)), key=lambda i: self._q[i])
            log.debug("Bandit: exploiting — arm %d (%s, Q=%.1f)", idx, _ARM_NAMES[idx], self._q[idx])
        return _ARMS[idx], idx

    def update(self, arm_idx: int, reward: float) -> None:
        """Update Q-value for the given arm using EMA.

        Args:
            arm_idx: Arm index returned by select().
            reward:  AI-detection score (0–100) — higher means more human-like.
        """
        if not 0 <= arm_idx < len(_ARMS):
            log.warning("Bandit.update: invalid arm_idx %d", arm_idx)
            return
        prev = self._q[arm_idx]
        self._q[arm_idx] = (1 - self._ALPHA) * prev + self._ALPHA * float(reward)
        self._counts[arm_idx] += 1
        self._total_updates += 1
        log.debug(
            "Bandit: arm %d (%s) reward=%.1f  Q: %.1f → %.1f",
            arm_idx, _ARM_NAMES[arm_idx], reward, prev, self._q[arm_idx],
        )
        self._save()

    def stats(self) -> Dict:
        """Return current bandit state as a serialisable dict."""
        return {
            "total_updates": self._total_updates,
            "best_arm": _ARM_NAMES[max(range(len(self._q)), key=lambda i: self._q[i])],
            "arms": [
                {
                    "index": i,
                    "name": _ARM_NAMES[i],
                    "q_value": round(self._q[i], 2),
                    "times_selected": self._counts[i],
                    "config": asdict(_ARMS[i]),
                }
                for i in range(len(_ARMS))
            ],
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_bandit = HumanizationBandit()
