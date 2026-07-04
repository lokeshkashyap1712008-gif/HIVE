"""
HIVE OS - Demo Mode
Pre-seeded demo data for hackathon presentation.
Allows instant demo with cached responses.
"""

import os
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class DemoTask:
    """Pre-seeded demo task"""
    task_id: str
    description: str
    priority: str
    expected_agents: List[str]
    expected_result: dict
    duration_seconds: float = 5.0


@dataclass
class DemoAgentState:
    """Pre-seeded agent state"""
    agent_id: str
    agent_type: str
    status: str
    emotion: str
    confidence: float
    current_task: str = ""


# Pre-seeded demo tasks
DEMO_TASKS = [
    DemoTask(
        task_id="demo_001",
        description="Analyze this codebase for security vulnerabilities and suggest fixes",
        priority="high",
        expected_agents=["leader", "security_scout", "code_architect", "judge"],
        expected_result={
            "vulnerabilities_found": 12,
            "critical": 2,
            "high": 4,
            "medium": 6,
            "fixes_suggested": 10,
            "confidence": 0.94
        },
        duration_seconds=8.0
    ),
    DemoTask(
        task_id="demo_002",
        description="Review the pull request and provide detailed feedback on code quality",
        priority="medium",
        expected_agents=["leader", "code_architect", "judge"],
        expected_result={
            "issues_found": 8,
            "suggestions": 15,
            "approval_status": "needs_changes",
            "confidence": 0.89
        },
        duration_seconds=6.0
    ),
    DemoTask(
        task_id="demo_003",
        description="Deploy the application to production with zero downtime",
        priority="critical",
        expected_agents=["leader", "cloud_tester", "safety_agent", "judge"],
        expected_result={
            "deployment_status": "success",
            "health_checks_passed": True,
            "rollback_available": True,
            "confidence": 0.91
        },
        duration_seconds=10.0
    ),
    DemoTask(
        task_id="demo_004",
        description="Monitor GPU utilization and optimize resource allocation",
        priority="medium",
        expected_agents=["leader", "gpu_tuner", "data_analyst"],
        expected_result={
            "gpu_utilization_before": 45,
            "gpu_utilization_after": 78,
            "memory_saved_gb": 2.4,
            "performance_improvement": "32%",
            "confidence": 0.96
        },
        duration_seconds=7.0
    ),
    DemoTask(
        task_id="demo_005",
        description="Conduct a red team assessment of the authentication system",
        priority="high",
        expected_agents=["leader", "red_team", "security_scout", "judge"],
        expected_result={
            "attack_vectors_tested": 15,
            "vulnerabilities_found": 5,
            "risk_level": "medium",
            "recommendations": 8,
            "confidence": 0.88
        },
        duration_seconds=9.0
    ),
]

# Pre-seeded agent states
DEMO_AGENT_STATES = [
    DemoAgentState("queen_bee", "leader", "active", "focused", 0.95, "Task orchestration"),
    DemoAgentState("agent_forge", "agent_forge", "idle", "ready", 0.92),
    DemoAgentState("cleanup_crew", "cleanup_crew", "monitoring", "calm", 0.88),
    DemoAgentState("safety_agent", "safety_agent", "active", "vigilant", 0.97),
    DemoAgentState("judge", "judge", "deliberating", "analytical", 0.93),
    DemoAgentState("web_scout", "worker", "active", "curious", 0.85, "Web research"),
    DemoAgentState("security_scout", "worker", "scanning", "alert", 0.91, "Security audit"),
    DemoAgentState("code_architect", "worker", "reviewing", "focused", 0.89, "Code review"),
    DemoAgentState("diagnostician", "worker", "analyzing", "methodical", 0.87),
    DemoAgentState("report_agent", "worker", "idle", "ready", 0.90),
    DemoAgentState("data_analyst", "worker", "processing", "diligent", 0.88, "Data analysis"),
    DemoAgentState("gpu_tuner", "worker", "monitoring", "attentive", 0.94),
    DemoAgentState("red_team", "worker", "reconnaissance", "strategic", 0.86),
    DemoAgentState("communicator", "worker", "idle", "ready", 0.91),
]

# Demo conversation history
DEMO_CONVERSATIONS = [
    {
        "role": "user",
        "content": "Analyze this codebase for security vulnerabilities",
        "timestamp": time.time() - 30
    },
    {
        "role": "assistant",
        "content": "I'll coordinate a comprehensive security analysis. Let me assemble the right team for this task.",
        "timestamp": time.time() - 25
    },
    {
        "role": "system",
        "content": "[Queen Bee] Task assigned: Security Analysis. Spawning agents: security_scout, code_architect, red_team",
        "timestamp": time.time() - 20
    },
    {
        "role": "assistant",
        "content": "[Security Scout] Scanning for vulnerabilities... Found 12 potential issues across 3 categories.",
        "timestamp": time.time() - 15
    },
    {
        "role": "assistant",
        "content": "[Code Architect] Reviewing code patterns... Identified 8 areas for improvement.",
        "timestamp": time.time() - 10
    },
    {
        "role": "assistant",
        "content": "[Judge] Evaluating findings from all agents. Consensus reached: 2 critical, 4 high, 6 medium severity issues.",
        "timestamp": time.time() - 5
    },
    {
        "role": "assistant",
        "content": "## Security Analysis Complete\n\n### Summary\n- **Critical Issues:** 2 (SQL Injection, Hardcoded Secrets)\n- **High Issues:** 4 (XSS, CSRF, Insecure Deserialization, Path Traversal)\n- **Medium Issues:** 6 (Weak Password Policy, Missing Rate Limiting, etc.)\n\n### Recommendations\n1. Implement parameterized queries immediately\n2. Rotate all exposed credentials\n3. Add CSRF tokens to forms\n4. Enable Content Security Policy headers\n\n**Confidence Score:** 94%",
        "timestamp": time.time()
    }
]


class DemoMode:
    """Demo mode manager for hackathon presentations"""
    
    def __init__(self):
        self.enabled = os.environ.get("HIVE_DEMO_MODE", "false").lower() == "true"
        self.current_task_index = 0
        self.conversation_index = 0
    
    def is_enabled(self) -> bool:
        """Check if demo mode is enabled"""
        return self.enabled
    
    def enable(self):
        """Enable demo mode"""
        self.enabled = True
        os.environ["HIVE_DEMO_MODE"] = "true"
    
    def disable(self):
        """Disable demo mode"""
        self.enabled = False
        os.environ["HIVE_DEMO_MODE"] = "false"
    
    def get_demo_tasks(self) -> List[dict]:
        """Get all demo tasks"""
        return [
            {
                'task_id': t.task_id,
                'description': t.description,
                'priority': t.priority,
                'expected_agents': t.expected_agents
            }
            for t in DEMO_TASKS
        ]
    
    def get_next_demo_task(self) -> Optional[dict]:
        """Get next demo task in sequence"""
        if self.current_task_index >= len(DEMO_TASKS):
            return None
        
        task = DEMO_TASKS[self.current_task_index]
        self.current_task_index += 1
        
        return {
            'task_id': task.task_id,
            'description': task.description,
            'priority': task.priority,
            'expected_agents': task.expected_agents,
            'expected_result': task.expected_result,
            'duration_seconds': task.duration_seconds
        }
    
    def get_demo_agent_states(self) -> List[dict]:
        """Get demo agent states"""
        return [
            {
                'agent_id': a.agent_id,
                'agent_type': a.agent_type,
                'status': a.status,
                'emotion': a.emotion,
                'confidence': a.confidence,
                'current_task': a.current_task
            }
            for a in DEMO_AGENT_STATES
        ]
    
    def get_demo_conversation(self, count: int = 5) -> List[dict]:
        """Get demo conversation messages"""
        start = max(0, self.conversation_index - count)
        end = min(len(DEMO_CONVERSATIONS), self.conversation_index + count)
        self.conversation_index = min(self.conversation_index + 1, len(DEMO_CONVERSATIONS))
        
        return DEMO_CONVERSATIONS[start:end]
    
    def get_demo_metrics(self) -> dict:
        """Get demo swarm metrics"""
        return {
            'total_agents': 14,
            'active_agents': 8,
            'tasks_completed': 47,
            'tasks_in_progress': 3,
            'budget_remaining': 847,
            'budget_total': 1000,
            'uptime_hours': 24.5,
            'tokens_used': 125000,
            'avg_response_time_ms': 2340,
            'success_rate': 0.96
        }
    
    def get_demo_economy(self) -> dict:
        """Get demo economy state"""
        return {
            'budget': 847,
            'total_earned': 200,
            'total_spent': 353,
            'transactions': [
                {'agent': 'security_scout', 'amount': -25, 'reason': 'Security scan'},
                {'agent': 'code_architect', 'amount': -30, 'reason': 'Code review'},
                {'agent': 'web_scout', 'amount': -15, 'reason': 'Web research'},
                {'agent': 'judge', 'amount': -20, 'reason': 'Conflict resolution'},
                {'agent': 'leader', 'amount': -10, 'reason': 'Task orchestration'},
            ]
        }
    
    def get_demo_benchmarks(self) -> List[dict]:
        """Get demo benchmark results"""
        return [
            {
                'name': 'Single vs Society - Findings',
                'single_agent': 12,
                'society': 127,
                'improvement': '958%'
            },
            {
                'name': 'Response Quality',
                'single_agent': 72,
                'society': 94,
                'improvement': '30.6%'
            },
            {
                'name': 'Task Completion Time',
                'single_agent': 45,
                'society': 28,
                'improvement': '37.8% faster'
            },
            {
                'name': 'Cost Efficiency',
                'single_agent': 100,
                'society': 85,
                'improvement': '15% savings'
            }
        ]
    
    def reset(self):
        """Reset demo state"""
        self.current_task_index = 0
        self.conversation_index = 0


# Global instance
demo_mode = DemoMode()


def is_demo_mode() -> bool:
    """Check if demo mode is enabled"""
    return demo_mode.is_enabled()


def get_demo_data() -> dict:
    """Get all demo data for frontend"""
    return {
        'tasks': demo_mode.get_demo_tasks(),
        'agents': demo_mode.get_demo_agent_states(),
        'conversation': demo_mode.get_demo_conversation(),
        'metrics': demo_mode.get_demo_metrics(),
        'economy': demo_mode.get_demo_economy(),
        'benchmarks': demo_mode.get_demo_benchmarks()
    }
