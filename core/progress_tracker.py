"""
Progress Broadcasting: Real-time updates during long pipeline operations

Key Features:
- Broadcast progress every 30s during long operations
- Calculate expected duration based on model speed
- Store in DB for frontend polling (GET /progress/{article_id})
- Automatic cleanup after completion
"""
import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


class ProgressTracker:
    """Track and broadcast progress during long AI operations"""
    
    def __init__(self, article_id: str, db=None):
        self.article_id = article_id
        self.db = db
        self.last_broadcast = 0
        self.operation_start = 0
        self.expected_duration = 0
        self.operation_name = ""
        self._create_tables()
    
    def _create_tables(self):
        """Create progress table in database"""
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_progress (
                    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    message TEXT NOT NULL,
                    elapsed_sec INTEGER DEFAULT 0,
                    remaining_sec INTEGER DEFAULT 0,
                    percent INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            # Index for fast lookup of latest progress
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_progress_article 
                ON pipeline_progress(article_id, created_at DESC)
            """)
            self.db.commit()
        except Exception as e:
            log.warning(f"Could not create progress table: {e}")
    
    def start_operation(self, operation: str, expected_seconds: int):
        """
        Start tracking a long operation
        
        Args:
            operation: Name of operation (e.g., "Quality Loop Pass 1", "Draft S6")
            expected_seconds: Estimated duration in seconds
        """
        self.operation_name = operation
        self.operation_start = _time.time()
        self.expected_duration = expected_seconds
        self.last_broadcast = 0  # Force immediate broadcast
        
        # Initial broadcast
        self._broadcast(
            f"Started: {operation}",
            0,
            expected_seconds,
            0
        )
        log.info(f"[Progress] {operation} started (est. {expected_seconds}s)")
    
    def update(self, message: str = "", force: bool = False):
        """
        Send progress update (throttled to every 30s unless forced)
        
        Args:
            message: Optional custom message
            force: If True, bypass 30s throttle
        """
        now = _time.time()
        
        # Throttle to 30s intervals unless forced
        if not force and (now - self.last_broadcast < 30):
            return
        
        elapsed = int(now - self.operation_start)
        remaining = max(0, self.expected_duration - elapsed)
        
        # Calculate percentage
        if self.expected_duration > 0:
            pct = min(100, int((elapsed / self.expected_duration) * 100))
        else:
            pct = 0
        
        msg = message or f"{self.operation_name}: {elapsed}s elapsed..."
        
        self._broadcast(msg, elapsed, remaining, pct)
    
    def finish(self, message: str = "Complete", final_message: bool = True):
        """
        Mark operation complete
        
        Args:
            message: Completion message
            final_message: If True, mark as 100% complete
        """
        elapsed = int(_time.time() - self.operation_start)
        
        if final_message:
            self._broadcast(message, elapsed, 0, 100)
        else:
            # Just send message without marking 100%
            remaining = max(0, self.expected_duration - elapsed)
            pct = min(99, int((elapsed / self.expected_duration) * 100)) if self.expected_duration > 0 else 0
            self._broadcast(message, elapsed, remaining, pct)
        
        log.info(f"[Progress] {self.operation_name} finished in {elapsed}s")
    
    def _broadcast(self, message: str, elapsed: int, remaining: int, pct: int):
        """Write progress update to database"""
        if not self.db:
            return
        
        try:
            self.db.execute(
                """INSERT INTO pipeline_progress
                   (article_id, operation, message, elapsed_sec, remaining_sec, percent, created_at) 
                   VALUES(?,?,?,?,?,?,?)""",
                (self.article_id, self.operation_name, message, elapsed, remaining, pct,
                 datetime.now(timezone.utc).isoformat())
            )
            self.db.commit()
            self.last_broadcast = _time.time()
            
            log.debug(f"[Progress] {self.article_id}: {message} | {elapsed}s / {remaining}s ({pct}%)")
        except Exception as e:
            log.warning(f"Progress broadcast failed: {e}")
    
    @staticmethod
    def cleanup(article_id: str, db):
        """Delete all progress records for completed article"""
        if not db:
            return
        try:
            db.execute(
                "DELETE FROM pipeline_progress WHERE article_id=?",
                (article_id,)
            )
            db.commit()
            log.debug(f"Progress records cleaned up for {article_id}")
        except Exception as e:
            log.warning(f"Progress cleanup failed: {e}")
    
    @staticmethod
    def get_latest(article_id: str, db) -> Optional[dict]:
        """Get latest progress for an article (for API endpoint)"""
        if not db:
            return None
        try:
            row = db.execute(
                """SELECT operation, message, elapsed_sec, remaining_sec, percent, created_at
                   FROM pipeline_progress 
                   WHERE article_id=? 
                   ORDER BY created_at DESC LIMIT 1""",
                (article_id,)
            ).fetchone()
            
            if row:
                return {
                    "operation": row[0],
                    "message": row[1],
                    "elapsed_sec": row[2],
                    "remaining_sec": row[3],
                    "percent": row[4],
                    "timestamp": row[5],
                }
            return None
        except Exception as e:
            log.warning(f"Failed to get latest progress: {e}")
            return None


def create_progress_tracker(article_id: str, db=None) -> ProgressTracker:
    """Factory function to create progress tracker"""
    return ProgressTracker(article_id, db)
