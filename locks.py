import sqlite3
import time
from typing import Optional

class LockError(Exception):
    pass

class AgentLockManager:
    """Provides atomic mutex locks for agent resources using SQLite."""
    def __init__(self, db_path: str = "kernel_state.db"):
        self.db_path = db_path
        self._init_locks_table()

    def _init_locks_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_locks (
                    resource_id TEXT PRIMARY KEY,
                    locked_by_agent TEXT,
                    acquired_at REAL,
                    timeout_seconds REAL
                )
            """)
            conn.commit()

    def acquire(self, resource_id: str, agent_id: str, timeout: float = 5.0) -> bool:
        """Attempts to acquire an exclusive lock on a resource."""
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Clear expired locks automatically
            cursor.execute("DELETE FROM resource_locks WHERE resource_id = ? AND (? - acquired_at) > timeout_seconds", (resource_id, now))
            
            try:
                cursor.execute(
                    "INSERT INTO resource_locks (resource_id, locked_by_agent, acquired_at, timeout_seconds) VALUES (?, ?, ?, ?)",
                    (resource_id, agent_id, now, timeout)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Resource is already locked
                return False

    def release(self, resource_id: str, agent_id: str):
        """Releases the lock if held by this agent."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM resource_locks WHERE resource_id = ? AND locked_by_agent = ?", (resource_id, agent_id))
            conn.commit()
