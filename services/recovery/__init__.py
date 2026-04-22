"""
Section-level Recovery Engine for content pipeline v2.

Detects issues in individual sections, classifies them,
builds targeted fix prompts from recovery_rules, and
regenerates ONLY failing sections (max 2 passes per section).
"""
from .engine import RecoveryEngine

__all__ = ["RecoveryEngine"]
