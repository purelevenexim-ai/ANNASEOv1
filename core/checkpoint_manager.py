"""
Pipeline Checkpoint System: Save & resume from any pipeline step

Key Features:
- Save checkpoint after every expensive step + quality loop passes
- Resume from crash/timeout by loading last checkpoint
- Minimal storage - only essential state (no giant HTML strings in logs)
- Automatic cleanup after successful completion
"""
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import json
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


@dataclass
class PipelineCheckpoint:
    """Serializable pipeline checkpoint"""
    article_id: str
    step_number: int  # 1-12
    step_name: str
    iteration: int = 0  # For steps 10-12 loop
    pass_number: int = 0  # For quality loop passes
    timestamp: str = ""
    
    # Core state - only what's needed to resume
    keyword: str = ""
    project_id: str = ""
    intent: str = ""
    word_count: int = 0
    seo_score: float = 0.0
    
    # Serialized state blob (ContentState + progress)
    state_json: str = ""  # JSON string of full state
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PipelineCheckpoint":
        return cls(**data)


class CheckpointManager:
    """Manages pipeline checkpoints for crash recovery"""
    
    def __init__(self, db=None, checkpoint_dir: str = "/tmp/checkpoints"):
        self.db = db
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
        self._create_tables()
    
    def _create_tables(self):
        """Create checkpoint tables in database"""
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    iteration INTEGER DEFAULT 0,
                    pass INTEGER DEFAULT 0,
                    keyword TEXT,
                    project_id TEXT,
                    seo_score REAL DEFAULT 0,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(article_id, step, iteration, pass)
                )
            """)
            # Index for fast lookup
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_article 
                ON pipeline_checkpoints(article_id, created_at DESC)
            """)
            self.db.commit()
            log.debug("Checkpoint tables created/verified")
        except Exception as e:
            log.warning(f"Could not create checkpoint tables: {e}")
    
    def save(
        self, 
        article_id: str, 
        step_num: int, 
        step_name: str,
        state: Any,  # PipelineState object
        iteration: int = 0, 
        pass_num: int = 0
    ) -> bool:
        """
        Save checkpoint for a pipeline step
        
        Returns True if saved successfully, False otherwise
        """
        try:
            # Serialize state
            state_dict = state.to_dict() if hasattr(state, 'to_dict') else {}
            state_json = json.dumps(state_dict)
            
            checkpoint = PipelineCheckpoint(
                article_id=article_id,
                step_number=step_num,
                step_name=step_name,
                iteration=iteration,
                pass_number=pass_num,
                timestamp=datetime.now(timezone.utc).isoformat(),
                keyword=state.keyword if hasattr(state, 'keyword') else "",
                project_id="",  # Can extract from state if needed
                seo_score=float(state.seo_score) if hasattr(state, 'seo_score') else 0.0,
                state_json=state_json,
            )
            
            # Save to file (fast recovery)
            file_path = self._get_checkpoint_path(article_id, step_num, iteration, pass_num)
            with open(file_path, 'w') as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            
            # Save to DB (persistent)
            if self.db:
                self.db.execute(
                    """INSERT OR REPLACE INTO pipeline_checkpoints
                       (article_id, step, iteration, pass, keyword, project_id, 
                        seo_score, state_json, created_at) 
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (checkpoint.article_id, step_num, iteration, pass_num,
                     checkpoint.keyword, checkpoint.project_id, checkpoint.seo_score,
                     state_json, checkpoint.timestamp)
                )
                self.db.commit()
            
            log.info(f"Checkpoint saved: {article_id} step {step_num} iter={iteration} pass={pass_num}")
            return True
            
        except Exception as e:
            log.error(f"Failed to save checkpoint: {e}")
            return False
    
    def load_latest(self, article_id: str) -> Optional[PipelineCheckpoint]:
        """Load the latest checkpoint for an article"""
        try:
            # Try file first (fastest)
            checkpoints = []
            for filename in os.listdir(self.checkpoint_dir):
                if filename.startswith(f"{article_id}_step"):
                    path = os.path.join(self.checkpoint_dir, filename)
                    try:
                        with open(path, 'r') as f:
                            data = json.load(f)
                            checkpoints.append((data.get('timestamp', ''), data))
                    except:
                        continue
            
            if checkpoints:
                # Get most recent
                checkpoints.sort(reverse=True)
                checkpoint = PipelineCheckpoint.from_dict(checkpoints[0][1])
                log.info(f"Loaded checkpoint from file: {article_id} step {checkpoint.step_number}")
                return checkpoint
            
            # Fallback to DB
            if self.db:
                row = self.db.execute(
                    """SELECT step, iteration, pass, keyword, project_id, 
                              seo_score, state_json, created_at
                       FROM pipeline_checkpoints 
                       WHERE article_id=? 
                       ORDER BY created_at DESC LIMIT 1""",
                    (article_id,)
                ).fetchone()
                
                if row:
                    checkpoint = PipelineCheckpoint(
                        article_id=article_id,
                        step_number=row[0],
                        step_name=f"Step {row[0]}",
                        iteration=row[1],
                        pass_number=row[2],
                        keyword=row[3],
                        project_id=row[4],
                        seo_score=row[5],
                        state_json=row[6],
                        timestamp=row[7],
                    )
                    log.info(f"Loaded checkpoint from DB: {article_id} step {checkpoint.step_number}")
                    return checkpoint
            
            return None
            
        except Exception as e:
            log.error(f"Failed to load checkpoint: {e}")
            return None
    
    def cleanup(self, article_id: str):
        """Delete all checkpoints for a completed article"""
        try:
            # Delete files
            for filename in os.listdir(self.checkpoint_dir):
                if filename.startswith(f"{article_id}_"):
                    path = os.path.join(self.checkpoint_dir, filename)
                    os.remove(path)
            
            # Delete from DB
            if self.db:
                self.db.execute(
                    "DELETE FROM pipeline_checkpoints WHERE article_id=?",
                    (article_id,)
                )
                self.db.commit()
            
            log.info(f"Checkpoints cleaned up for {article_id}")
        except Exception as e:
            log.warning(f"Checkpoint cleanup failed: {e}")
    
    def _get_checkpoint_path(self, article_id: str, step: int, iteration: int, pass_num: int) -> str:
        """Get filesystem path for checkpoint file"""
        filename = f"{article_id}_step{step:02d}_i{iteration}_p{pass_num}.json"
        return os.path.join(self.checkpoint_dir, filename)


# Singleton instance
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager(db=None) -> CheckpointManager:
    """Get or create singleton CheckpointManager"""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager(db)
    return _checkpoint_manager


def init_checkpoint_manager(db) -> CheckpointManager:
    """Initialize checkpoint manager with database"""
    global _checkpoint_manager
    _checkpoint_manager = CheckpointManager(db)
    return _checkpoint_manager
