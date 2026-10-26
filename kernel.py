import hashlib
import json
import sqlite3
import time
from typing import Any, Callable, Dict, Optional

class KernelDeadlockException(Exception):
    """Raised when an agent enters an infinite loop or repetitive state."""
    pass

class KernelBudgetException(Exception):
    """Raised when an agent exceeds step or token limits."""
    pass

class AetherKernel:
    def __init__(self, db_path: str = "kernel_state.db", max_steps: int = 10, max_tokens: int = 1000, loop_threshold: int = 2):
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.loop_threshold = loop_threshold
        self.step_count = 0
        self.total_tokens_used = 0
        self.call_history = {}
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    state_key TEXT,
                    state_value TEXT,
                    timestamp REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    tool_name TEXT,
                    args TEXT,
                    tokens_used INTEGER,
                    status TEXT,
                    timestamp REAL
                )
            """)
            conn.commit()

    def _hash_action(self, tool_name: str, args: Dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_token_usage(self, agent_id: str, tokens: int):
        self.total_tokens_used += tokens
        if self.total_tokens_used > self.max_tokens:
            raise KernelBudgetException(
                f"[KERNEL SHUTDOWN] Token budget breached! Consumed {self.total_tokens_used} tokens (Limit: {self.max_tokens})."
            )

    def checkpoint(self, agent_id: str, key: str, value: Any):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO snapshots (agent_id, state_key, state_value, timestamp) VALUES (?, ?, ?, ?)",
                (agent_id, key, json.dumps(value), time.time()),
            )
            conn.commit()

    def rollback(self, agent_id: str, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT state_value FROM snapshots WHERE agent_id = ? AND state_key = ? ORDER BY id DESC LIMIT 1",
                (agent_id, key),
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None

    def execute_tool(self, agent_id: str, tool_name: str, tool_fn: Callable, **kwargs) -> Any:
        self.step_count += 1

        if self.step_count > self.max_steps:
            raise KernelBudgetException(f"[KERNEL ALERT] Agent '{agent_id}' exceeded max step limit ({self.max_steps}).")

        action_hash = self._hash_action(tool_name, kwargs)
        self.call_history[action_hash] = self.call_history.get(action_hash, 0) + 1

        if self.call_history[action_hash] > self.loop_threshold:
            self._log_execution(agent_id, tool_name, kwargs, 0, "DEADLOCK_HALTED")
            raise KernelDeadlockException(
                f"[KERNEL INTERRUPT] Deadlock detected! Tool '{tool_name}' repeated {self.loop_threshold + 1} times identically."
            )

        print(f"-> [Kernel Approved] Step {self.step_count} | Tokens: {self.total_tokens_used}/{self.max_tokens} | Tool: '{tool_name}'")
        result = tool_fn(**kwargs)
        self._log_execution(agent_id, tool_name, kwargs, 0, "SUCCESS")
        return result

    def _log_execution(self, agent_id: str, tool_name: str, args: dict, tokens: int, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO execution_logs (agent_id, tool_name, args, tokens_used, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, tool_name, json.dumps(args), tokens, status, time.time())
            )
            conn.commit()
