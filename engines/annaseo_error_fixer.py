"""
================================================================================
ANNASEO — Error/Bug Collector & Fixer Engine
================================================================================
Collects engine console errors + browser errors, uses Groq/Ollama to draft
a fix, Claude to verify it, then waits for customer approval before applying.

Flow:
  1. ErrorCollector.collect(run_id)  → reads run_events for error entries
  2. BugAnalyzer.analyze(error_report, db) → Groq drafts fix → Claude verifies
     → saves fix_proposal row (status='pending')
  3. FixApplicator.apply(fix_id, db) → snapshot file → apply fix
  4. FixRollback.rollback(fix_id, db) → restore snapshot
================================================================================
"""
from __future__ import annotations
import os, re, json, hashlib, time, logging, difflib, sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("annaseo.error_fixer")

# Base directory of the project — used to resolve relative file paths
_BASE = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _new_id(prefix: str) -> str:
    return f"{prefix}_{hashlib.md5(f'{time.time()}'.encode()).hexdigest()[:10]}"


def _call_groq(prompt: str, max_tokens: int = 800) -> str:
    """Call Groq Llama via openai-compatible API. Returns text or '' on failure."""
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        log.warning(f"[BugAnalyzer] Groq failed: {e}")
        return ""


def _call_ollama(prompt: str, max_tokens: int = 800) -> str:
    """Fallback: call local Ollama DeepSeek."""
    try:
        import requests
        url = f"{os.getenv('OLLAMA_URL', 'http://172.235.16.165:11434')}/api/generate"
        r = requests.post(url, json={
            "model": os.getenv("OLLAMA_MODEL", "deepseek-r1:7b"),
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.2},
        }, timeout=60)
        return r.json().get("response", "")
    except Exception as e:
        log.warning(f"[BugAnalyzer] Ollama failed: {e}")
        return ""


def _call_claude_verify(original: str, fixed: str, error_msg: str) -> tuple[str, str]:
    """
    Ask Claude (≤800 tokens) to verify the proposed fix.
    Returns (verdict, reason) where verdict is 'approved' | 'rejected' | 'pending'.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        # Keep prompt small — only the delta, not the full file
        prompt = (
            f"Error: {error_msg[:300]}\n\n"
            f"ORIGINAL CODE:\n{original[:600]}\n\n"
            f"PROPOSED FIX:\n{fixed[:600]}\n\n"
            "Does this fix resolve the error without introducing new bugs? "
            "Reply with exactly: YES or NO, then one sentence explaining why."
        )
        msg = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = msg.content[0].text.strip() if msg.content else ""
        verdict = "approved" if reply.upper().startswith("YES") else "rejected"
        reason = reply[4:].strip() if len(reply) > 4 else reply
        return verdict, reason
    except Exception as e:
        log.warning(f"[BugAnalyzer] Claude verify failed: {e}")
        return "pending", f"Claude unavailable: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# ERROR COLLECTOR
# ─────────────────────────────────────────────────────────────────────────────

class ErrorCollector:
    """Read error events from a run and upsert them into error_reports table."""

    def collect_from_run(self, run_id: str, db: sqlite3.Connection) -> list[dict]:
        """Pull all error-type events from a completed run and store as error_reports."""
        rows = db.execute(
            "SELECT payload, created_at FROM run_events "
            "WHERE run_id=? AND event_type='error' ORDER BY id",
            (run_id,)
        ).fetchall()

        created = []
        for row in rows:
            payload = json.loads(row["payload"] or "{}")
            msg = payload.get("error", payload.get("message", str(payload)))[:500]
            tb  = payload.get("traceback", "")[:1000]
            eid = _new_id("err")
            db.execute(
                "INSERT OR IGNORE INTO error_reports "
                "(error_id,source,message,traceback,context,run_id,project_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (eid, "engine", msg, tb, json.dumps(payload), run_id, "")
            )
            db.commit()
            created.append({"error_id": eid, "message": msg})
        return created

    def store_browser_error(
        self, message: str, traceback: str, context: dict,
        project_id: str, db: sqlite3.Connection
    ) -> str:
        eid = _new_id("err")
        db.execute(
            "INSERT INTO error_reports "
            "(error_id,source,message,traceback,context,project_id) "
            "VALUES (?,?,?,?,?,?)",
            (eid, "browser", message[:500], traceback[:500],
             json.dumps(context or {}), project_id)
        )
        db.commit()
        return eid


# ─────────────────────────────────────────────────────────────────────────────
# BUG ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

class BugAnalyzer:
    """
    Given an error_report row, draft a fix with Groq/Ollama, verify with Claude,
    then save a fix_proposal row.
    """

    def analyze(self, error_id: str, db: sqlite3.Connection) -> Optional[str]:
        """Returns fix_id if a proposal was created, else None."""
        row = db.execute(
            "SELECT * FROM error_reports WHERE error_id=?", (error_id,)
        ).fetchone()
        if not row:
            log.warning(f"[BugAnalyzer] error_id {error_id} not found")
            return None

        report = dict(row)
        msg = report.get("message", "")
        tb  = report.get("traceback", "")

        # Mark as analyzing
        db.execute(
            "UPDATE error_reports SET status='analyzing' WHERE error_id=?",
            (error_id,)
        )
        db.commit()

        # Extract target file + function from traceback
        target_file, target_fn, original_snippet = self._extract_target(tb, msg)

        # Step 1: Groq drafts the fix
        fix_prompt = (
            f"Python error: {msg}\n"
            f"Traceback: {tb[:400]}\n"
            + (f"Relevant code:\n{original_snippet[:400]}\n" if original_snippet else "")
            + "Write ONLY the corrected Python code snippet to fix this error. "
              "No explanations, no markdown fences — just the fixed code."
        )
        proposed = _call_groq(fix_prompt) or _call_ollama(fix_prompt)
        if not proposed:
            db.execute(
                "UPDATE error_reports SET status='new' WHERE error_id=?", (error_id,)
            )
            db.commit()
            log.warning(f"[BugAnalyzer] No AI response for {error_id}")
            return None

        proposed_snippet = proposed.strip()

        # Build unified diff
        orig_lines = original_snippet.splitlines(keepends=True) if original_snippet else []
        prop_lines = proposed_snippet.splitlines(keepends=True)
        diff_text = "".join(difflib.unified_diff(
            orig_lines, prop_lines,
            fromfile="original", tofile="proposed", lineterm="\n"
        ))

        # Step 2: Claude verifies (small token window)
        claude_verdict, claude_reason = _call_claude_verify(
            original_snippet or "(not extracted)", proposed_snippet, msg
        )

        # Step 3: Read full file for snapshot (if file found)
        snapshot_text = ""
        if target_file:
            full_path = _BASE / target_file
            if full_path.exists():
                snapshot_text = full_path.read_text(encoding="utf-8")

        # Save fix_proposal
        fix_id = _new_id("fix")
        db.execute(
            "INSERT INTO fix_proposals "
            "(fix_id,error_id,target_file,target_function,"
            "original_snippet,proposed_snippet,diff_text,snapshot_text,"
            "ai_draft_model,claude_verdict,claude_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                fix_id, error_id, target_file or "", target_fn or "",
                original_snippet or "", proposed_snippet, diff_text,
                snapshot_text, "groq",
                claude_verdict, claude_reason,
            )
        )
        db.execute(
            "UPDATE error_reports SET status='fix_ready' WHERE error_id=?",
            (error_id,)
        )
        db.commit()
        log.info(f"[BugAnalyzer] fix_proposal {fix_id} created (Claude: {claude_verdict})")
        return fix_id

    # ------------------------------------------------------------------
    def _extract_target(
        self, traceback: str, message: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse a Python traceback to find the last file + function name.
        Then read just that function from the source file.
        Returns (relative_file_path, function_name, source_snippet).
        """
        file_match = re.findall(r'File "([^"]+)", line \d+, in (\S+)', traceback)
        if not file_match:
            return None, None, None

        # Last frame is the crash point
        raw_path, fn_name = file_match[-1]

        # Make relative to project base
        try:
            rel = str(Path(raw_path).relative_to(_BASE))
        except ValueError:
            rel = raw_path  # already relative or external

        # Read function source (~30 lines around the error)
        snippet = self._read_function(raw_path, fn_name)
        return rel, fn_name, snippet

    def _read_function(self, filepath: str, fn_name: str) -> str:
        """Extract a function's source lines from a file."""
        try:
            lines = Path(filepath).read_text(encoding="utf-8").splitlines()
            start = None
            for i, line in enumerate(lines):
                if re.match(rf"\s*def {re.escape(fn_name)}\s*\(", line):
                    start = i
                    break
            if start is None:
                return ""
            # Read up to 40 lines
            snippet_lines = lines[start:start + 40]
            return "\n".join(snippet_lines)
        except Exception:
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# FIX APPLICATOR
# ─────────────────────────────────────────────────────────────────────────────

class FixApplicator:
    """Apply an approved fix_proposal to the target file."""

    def apply(self, fix_id: str, db: sqlite3.Connection) -> bool:
        row = db.execute(
            "SELECT * FROM fix_proposals WHERE fix_id=?", (fix_id,)
        ).fetchone()
        if not row:
            return False

        fix = dict(row)
        if fix["status"] not in ("pending",):
            log.warning(f"[FixApplicator] fix {fix_id} already in status '{fix['status']}'")
            return False

        target_file = fix.get("target_file", "")
        original_snippet = fix.get("original_snippet", "")
        proposed_snippet = fix.get("proposed_snippet", "")

        if not target_file or not original_snippet or not proposed_snippet:
            log.warning(f"[FixApplicator] incomplete fix data for {fix_id}")
            return False

        full_path = _BASE / target_file
        if not full_path.exists():
            log.warning(f"[FixApplicator] file not found: {full_path}")
            return False

        current_text = full_path.read_text(encoding="utf-8")

        # Save snapshot if not already saved
        if not fix.get("snapshot_text"):
            db.execute(
                "UPDATE fix_proposals SET snapshot_text=? WHERE fix_id=?",
                (current_text, fix_id)
            )
            db.commit()

        if original_snippet not in current_text:
            log.warning(f"[FixApplicator] original snippet not found in {target_file}")
            db.execute(
                "UPDATE fix_proposals SET status='rejected' WHERE fix_id=?", (fix_id,)
            )
            db.commit()
            return False

        new_text = current_text.replace(original_snippet, proposed_snippet, 1)
        full_path.write_text(new_text, encoding="utf-8")

        db.execute(
            "UPDATE fix_proposals SET status='applied' WHERE fix_id=?", (fix_id,)
        )
        db.execute(
            "UPDATE error_reports SET status='applied' WHERE error_id=?",
            (fix["error_id"],)
        )
        db.commit()
        log.info(f"[FixApplicator] Applied fix {fix_id} to {target_file}")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# FIX ROLLBACK
# ─────────────────────────────────────────────────────────────────────────────

class FixRollback:
    """Restore a file to its pre-fix snapshot."""

    def rollback(self, fix_id: str, db: sqlite3.Connection) -> bool:
        row = db.execute(
            "SELECT * FROM fix_proposals WHERE fix_id=?", (fix_id,)
        ).fetchone()
        if not row:
            return False

        fix = dict(row)
        snapshot = fix.get("snapshot_text", "")
        target_file = fix.get("target_file", "")

        if not snapshot or not target_file:
            log.warning(f"[FixRollback] No snapshot available for {fix_id}")
            return False

        full_path = _BASE / target_file
        full_path.write_text(snapshot, encoding="utf-8")

        db.execute(
            "UPDATE fix_proposals SET status='rolled_back' WHERE fix_id=?", (fix_id,)
        )
        db.execute(
            "UPDATE error_reports SET status='rolled_back' WHERE error_id=?",
            (fix["error_id"],)
        )
        db.commit()
        log.info(f"[FixRollback] Rolled back {fix_id} — restored {target_file}")
        return True
