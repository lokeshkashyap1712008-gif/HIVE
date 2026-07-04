"""
HIVE OS - Checkpoint & Crash Recovery System
Periodic state snapshots, crash recovery, manual checkpoint/restore.
"""

import json
import time
import sqlite3
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class CheckpointData:
    """Complete state snapshot"""
    checkpoint_id: str
    timestamp: float
    agent_states: Dict[str, dict] = field(default_factory=dict)
    task_queue: List[dict] = field(default_factory=list)
    economy_state: dict = field(default_factory=dict)
    active_tasks: List[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class CheckpointManager:
    """Manages system checkpoints for crash recovery"""
    
    def __init__(self, db_path: str = None, max_checkpoints: int = 10):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'checkpoints.db')
        
        self.db_path = db_path
        self.max_checkpoints = max_checkpoints
        self._init_db()
    
    def _init_db(self):
        """Initialize checkpoint database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                agent_states TEXT,
                task_queue TEXT,
                economy_state TEXT,
                active_tasks TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task_id TEXT,
                score REAL NOT NULL,
                metrics TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_name TEXT NOT NULL,
                run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                single_agent_score REAL,
                society_score REAL,
                improvement_pct REAL,
                details TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_checkpoint(self, data: CheckpointData) -> str:
        """Save a checkpoint"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO checkpoints 
            (id, timestamp, agent_states, task_queue, economy_state, active_tasks, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.checkpoint_id,
            data.timestamp,
            json.dumps(data.agent_states),
            json.dumps(data.task_queue),
            json.dumps(data.economy_state),
            json.dumps(data.active_tasks),
            json.dumps(data.metadata)
        ))
        
        conn.commit()
        conn.close()
        
        # Prune old checkpoints
        self._prune_checkpoints()
        
        return data.checkpoint_id
    
    def load_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Load a specific checkpoint"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM checkpoints WHERE id = ?', (checkpoint_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return CheckpointData(
            checkpoint_id=row[0],
            timestamp=row[1],
            agent_states=json.loads(row[2]) if row[2] else {},
            task_queue=json.loads(row[3]) if row[3] else [],
            economy_state=json.loads(row[4]) if row[4] else {},
            active_tasks=json.loads(row[5]) if row[5] else [],
            metadata=json.loads(row[6]) if row[6] else {}
        )
    
    def get_latest_checkpoint(self) -> Optional[CheckpointData]:
        """Get the most recent checkpoint"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM checkpoints ORDER BY timestamp DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self.load_checkpoint(row[0])
        return None
    
    def list_checkpoints(self, limit: int = 20) -> List[dict]:
        """List recent checkpoints"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, timestamp, created_at 
            FROM checkpoints 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {'id': r[0], 'timestamp': r[1], 'created_at': r[2]}
            for r in rows
        ]
    
    def _prune_checkpoints(self):
        """Remove old checkpoints beyond max limit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM checkpoints')
        count = cursor.fetchone()[0]
        
        if count > self.max_checkpoints:
            cursor.execute('''
                DELETE FROM checkpoints 
                WHERE id NOT IN (
                    SELECT id FROM checkpoints 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                )
            ''', (self.max_checkpoints,))
        
        conn.commit()
        conn.close()
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM checkpoints WHERE id = ?', (checkpoint_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def save_agent_score(self, agent_id: str, score: float, 
                         task_id: str = None, metrics: dict = None):
        """Save agent performance score"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO agent_scores (agent_id, task_id, score, metrics)
            VALUES (?, ?, ?, ?)
        ''', (agent_id, task_id, score, json.dumps(metrics) if metrics else None))
        
        conn.commit()
        conn.close()
    
    def get_agent_scores(self, agent_id: str, limit: int = 100) -> List[dict]:
        """Get agent score history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT score, task_id, metrics, recorded_at
            FROM agent_scores
            WHERE agent_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
        ''', (agent_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'score': r[0],
                'task_id': r[1],
                'metrics': json.loads(r[2]) if r[2] else None,
                'recorded_at': r[3]
            }
            for r in rows
        ]
    
    def save_benchmark_result(self, benchmark_name: str, 
                               single_agent_score: float,
                               society_score: float,
                               details: dict = None):
        """Save benchmark result"""
        improvement = ((society_score - single_agent_score) / single_agent_score * 100 
                       if single_agent_score > 0 else 0)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO benchmark_results 
            (benchmark_name, single_agent_score, society_score, improvement_pct, details)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            benchmark_name,
            single_agent_score,
            society_score,
            improvement,
            json.dumps(details) if details else None
        ))
        
        conn.commit()
        conn.close()
    
    def get_benchmark_results(self, benchmark_name: str = None) -> List[dict]:
        """Get benchmark results"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if benchmark_name:
            cursor.execute('''
                SELECT benchmark_name, single_agent_score, society_score, 
                       improvement_pct, details, run_timestamp
                FROM benchmark_results
                WHERE benchmark_name = ?
                ORDER BY run_timestamp DESC
            ''', (benchmark_name,))
        else:
            cursor.execute('''
                SELECT benchmark_name, single_agent_score, society_score, 
                       improvement_pct, details, run_timestamp
                FROM benchmark_results
                ORDER BY run_timestamp DESC
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'benchmark_name': r[0],
                'single_agent_score': r[1],
                'society_score': r[2],
                'improvement_pct': r[3],
                'details': json.loads(r[4]) if r[4] else None,
                'run_timestamp': r[5]
            }
            for r in rows
        ]


# Global instance
checkpoint_manager = CheckpointManager()


def save_checkpoint(checkpoint_id: str, agent_states: dict = None,
                    task_queue: list = None, economy_state: dict = None) -> str:
    """Convenience function to save checkpoint"""
    data = CheckpointData(
        checkpoint_id=checkpoint_id,
        timestamp=time.time(),
        agent_states=agent_states or {},
        task_queue=task_queue or [],
        economy_state=economy_state or {}
    )
    return checkpoint_manager.save_checkpoint(data)


def load_checkpoint(checkpoint_id: str) -> Optional[CheckpointData]:
    """Convenience function to load checkpoint"""
    return checkpoint_manager.load_checkpoint(checkpoint_id)


def get_latest_checkpoint() -> Optional[CheckpointData]:
    """Convenience function to get latest checkpoint"""
    return checkpoint_manager.get_latest_checkpoint()
