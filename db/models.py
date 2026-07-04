"""
HIVE OS - Database Models
SQLAlchemy models for agents, tasks, checkpoints, scores, and benchmarks.
"""

from datetime import datetime
from typing import Optional
import json

try:
    from sqlalchemy import create_engine, Column, String, Float, Integer, Text, DateTime, JSON, Boolean
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    
    Base = declarative_base()
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    # Fallback: simple dict-based models
    class Base:
        pass


if SQLALCHEMY_AVAILABLE:
    class AgentRecord(Base):
        """Agent lifecycle tracking"""
        __tablename__ = 'agents'
        
        id = Column(String, primary_key=True)
        agent_type = Column(String, nullable=False)
        task_id = Column(String)
        status = Column(String, default="running")
        spawned_at = Column(Float)
        last_ping = Column(Float)
        failures = Column(Integer, default=0)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            return {
                'id': self.id,
                'agent_type': self.agent_type,
                'task_id': self.task_id,
                'status': self.status,
                'spawned_at': self.spawned_at,
                'last_ping': self.last_ping,
                'failures': self.failures,
                'created_at': self.created_at.isoformat() if self.created_at else None
            }

    class TaskRecord(Base):
        """Task lifecycle tracking"""
        __tablename__ = 'tasks'
        
        id = Column(String, primary_key=True)
        description = Column(Text, nullable=False)
        mode = Column(String, default="swarm")
        priority = Column(String, default="medium")
        status = Column(String, default="pending")
        result = Column(JSON)
        tokens_used = Column(Integer, default=0)
        time_taken = Column(Float, default=0.0)
        created_at = Column(Float)
        completed_at = Column(Float)
        recorded_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            return {
                'id': self.id,
                'description': self.description,
                'mode': self.mode,
                'priority': self.priority,
                'status': self.status,
                'result': self.result,
                'tokens_used': self.tokens_used,
                'time_taken': self.time_taken,
                'created_at': self.created_at,
                'completed_at': self.completed_at
            }

    class Checkpoint(Base):
        """System state checkpoints for crash recovery"""
        __tablename__ = 'checkpoints'
        
        id = Column(String, primary_key=True)
        timestamp = Column(Float, nullable=False)
        agent_states = Column(JSON)
        task_queue = Column(JSON)
        economy_state = Column(JSON)
        active_tasks = Column(JSON)
        metadata = Column(JSON)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            return {
                'id': self.id,
                'timestamp': self.timestamp,
                'agent_states': self.agent_states,
                'task_queue': self.task_queue,
                'economy_state': self.economy_state,
                'active_tasks': self.active_tasks,
                'metadata': self.metadata,
                'created_at': self.created_at.isoformat() if self.created_at else None
            }

    class AgentScore(Base):
        """Agent performance scores (judge-verified)"""
        __tablename__ = 'agent_scores'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, nullable=False, index=True)
        task_id = Column(String)
        score = Column(Float, nullable=False)
        metrics = Column(JSON)
        recorded_at = Column(DateTime, default=datetime.utcnow)
        
        def to_dict(self):
            return {
                'id': self.id,
                'agent_id': self.agent_id,
                'task_id': self.task_id,
                'score': self.score,
                'metrics': self.metrics,
                'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None
            }

    class BenchmarkResult(Base):
        """Benchmark comparison results"""
        __tablename__ = 'benchmark_results'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        benchmark_name = Column(String, nullable=False, index=True)
        run_timestamp = Column(DateTime, default=datetime.utcnow)
        single_agent_score = Column(Float)
        society_score = Column(Float)
        improvement_pct = Column(Float)
        details = Column(JSON)
        
        def to_dict(self):
            return {
                'id': self.id,
                'benchmark_name': self.benchmark_name,
                'run_timestamp': self.run_timestamp.isoformat() if self.run_timestamp else None,
                'single_agent_score': self.single_agent_score,
                'society_score': self.society_score,
                'improvement_pct': self.improvement_pct,
                'details': self.details
            }

    class AuditLog(Base):
        """Append-only audit log for all decisions"""
        __tablename__ = 'audit_log'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(Float, nullable=False)
        datetime_str = Column(String)
        decision_type = Column(String, nullable=False)
        reason = Column(Text)
        agents_affected = Column(JSON)
        metadata = Column(JSON)
        
        def to_dict(self):
            return {
                'id': self.id,
                'timestamp': self.timestamp,
                'datetime': self.datetime_str,
                'decision_type': self.decision_type,
                'reason': self.reason,
                'agents_affected': self.agents_affected,
                'metadata': self.metadata
            }


class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, db_url: str = None):
        if db_url is None:
            import os
            db_path = os.path.join(os.path.dirname(__file__), 'hive.db')
            db_url = f"sqlite:///{db_path}"
        
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def save_agent(self, agent: AgentRecord):
        """Save agent record"""
        session = self.get_session()
        try:
            session.merge(agent)
            session.commit()
        finally:
            session.close()
    
    def save_task(self, task: TaskRecord):
        """Save task record"""
        session = self.get_session()
        try:
            session.merge(task)
            session.commit()
        finally:
            session.close()
    
    def save_checkpoint(self, checkpoint: Checkpoint):
        """Save checkpoint"""
        session = self.get_session()
        try:
            session.add(checkpoint)
            session.commit()
        finally:
            session.close()
    
    def get_latest_checkpoint(self) -> Optional[Checkpoint]:
        """Get latest checkpoint"""
        session = self.get_session()
        try:
            return session.query(Checkpoint).order_by(Checkpoint.timestamp.desc()).first()
        finally:
            session.close()
    
    def save_agent_score(self, score: AgentScore):
        """Save agent score"""
        session = self.get_session()
        try:
            session.add(score)
            session.commit()
        finally:
            session.close()
    
    def get_agent_scores(self, agent_id: str, limit: int = 100):
        """Get agent score history"""
        session = self.get_session()
        try:
            return session.query(AgentScore).filter(
                AgentScore.agent_id == agent_id
            ).order_by(AgentScore.recorded_at.desc()).limit(limit).all()
        finally:
            session.close()
    
    def save_benchmark_result(self, result: BenchmarkResult):
        """Save benchmark result"""
        session = self.get_session()
        try:
            session.add(result)
            session.commit()
        finally:
            session.close()
    
    def get_benchmark_results(self, benchmark_name: str = None, limit: int = 50):
        """Get benchmark results"""
        session = self.get_session()
        try:
            query = session.query(BenchmarkResult)
            if benchmark_name:
                query = query.filter(BenchmarkResult.benchmark_name == benchmark_name)
            return query.order_by(BenchmarkResult.run_timestamp.desc()).limit(limit).all()
        finally:
            session.close()


# Global instance (lazy initialization)
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get or create database manager"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.create_tables()
    return _db_manager
