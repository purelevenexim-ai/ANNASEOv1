"""
ANNASEOv1 Audit Framework
=========================
5-layer quality assurance for the deterministic + AI hybrid pipeline.

Groups:
  1. Functional     — system runs correctly
  2. Data Integrity — data is correct across pipeline stages
  3. AI Reasoning   — AI output is logically correct, no hallucination
  4. Regression     — nothing broke after updates
  5. Human Value    — output is actionable and useful

Entry point:
  from audit.runner import run_full_audit
  report = run_full_audit(session_id="...", project_id="...")
"""
from audit.runner import run_full_audit  # noqa: F401
