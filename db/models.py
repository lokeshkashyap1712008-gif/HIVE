"""
HIVE — SQLite Database Schema
Tables: agents, tasks, audit_log (via audit_logger.py)
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class AgentRecord(Base):
    __tablename__ = "agents"

    id = Column(String(64), primary_key=True)
    agent_type = Column(String(64), nullable=False)
    task_id = Column(String(64))
    status = Column(String(32), default="running")
    spawned_at = Column(Float)
    last_ping = Column(Float)
    failures = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(String(64), primary_key=True)
    description = Column(Text)
    mode = Column(String(16), default="swarm")
    priority = Column(String(16), default="medium")
    status = Column(String(32), default="pending")
    result = Column(JSON)
    tokens_used = Column(Integer, default=0)
    time_taken = Column(Float)
    created_at = Column(Float)
    completed_at = Column(Float)
    recorded_at = Column(DateTime, server_default=func.now())


# DB init helper
def init_db(engine):
    """Create all tables."""
    Base.metadata.create_all(engine)