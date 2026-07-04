"""
HIVE OS - PALADIN Layer 4: Behavioral Monitoring & Anomaly Detection
Tracks tool calls, detects deviations, circuit breakers.
Based on Microsoft Agent Governance Toolkit and SRE practices.
"""

import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from collections import defaultdict


class AnomalyType(Enum):
    RATE_LIMIT = "rate_limit"
    TOOL_SEQUENCE = "tool_sequence"
    DATA_ACCESS = "data_access"
    CIRCUIT_BREAKER = "circuit_breaker"
    BEHAVIORAL_DEVIATION = "behavioral_deviation"
    LOOP_DETECTED = "loop_detected"
    COST_BUDGET = "cost_budget"


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class ToolCall:
    """Record of a tool call"""
    tool_name: str
    agent_id: str
    timestamp: float
    success: bool
    duration_ms: float
    args_hash: str = ""
    result_hash: str = ""


@dataclass
class BehavioralBaseline:
    """Baseline behavior for an agent"""
    agent_id: str
    agent_type: str
    typical_tools: Set[str] = field(default_factory=set)
    avg_calls_per_minute: float = 0.0
    max_calls_per_minute: float = 0.0
    typical_sequences: List[List[str]] = field(default_factory=list)
    max_data_access: int = 100
    last_updated: float = 0.0


@dataclass
class CircuitBreaker:
    """Circuit breaker for agent or tool"""
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    
    def record_success(self):
        """Record successful call"""
        self.success_count += 1
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
    
    def record_failure(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> Tuple[bool, str]:
        """Check if execution is allowed"""
        if self.state == CircuitState.CLOSED:
            return True, "Circuit closed"
        
        if self.state == CircuitState.OPEN:
            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                return True, "Circuit half-open"
            return False, f"Circuit open, retry in {self.recovery_timeout - time_since_failure:.0f}s"
        
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count < self.half_open_max_calls:
                return True, "Circuit half-open"
            return False, "Circuit half-open, max calls reached"
        
        return False, "Unknown state"


@dataclass
class CostBudget:
    """Cost budget tracking for agent"""
    agent_id: str
    max_tokens: int = 100000
    max_cost_usd: float = 10.0
    current_tokens: int = 0
    current_cost_usd: float = 0.0
    period_start: float = 0.0
    period_duration: int = 3600  # 1 hour
    
    def can_spend(self, tokens: int, cost_usd: float) -> Tuple[bool, str]:
        """Check if spending is within budget"""
        self._check_period()
        
        if self.current_tokens + tokens > self.max_tokens:
            return False, f"Token budget exceeded: {self.current_tokens + tokens}/{self.max_tokens}"
        
        if self.current_cost_usd + cost_usd > self.max_cost_usd:
            return False, f"Cost budget exceeded: ${self.current_cost_usd + cost_usd:.4f}/${self.max_cost_usd:.2f}"
        
        return True, "Within budget"
    
    def record_spend(self, tokens: int, cost_usd: float):
        """Record token/cost spend"""
        self._check_period()
        self.current_tokens += tokens
        self.current_cost_usd += cost_usd
    
    def _check_period(self):
        """Reset if period expired"""
        current_time = time.time()
        if current_time - self.period_start > self.period_duration:
            self.period_start = current_time
            self.current_tokens = 0
            self.current_cost_usd = 0.0


class BehavioralMonitor:
    """Main behavioral monitoring system"""
    
    def __init__(self):
        self.tool_calls: Dict[str, List[ToolCall]] = defaultdict(list)
        self.baselines: Dict[str, BehavioralBaseline] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.cost_budgets: Dict[str, CostBudget] = {}
        self.anomaly_log: List[dict] = []
        self.rate_limiters: Dict[str, List[float]] = defaultdict(list)
    
    def register_agent(self, agent_id: str, agent_type: str, 
                       baseline: dict = None):
        """Register agent for monitoring"""
        self.baselines[agent_id] = BehavioralBaseline(
            agent_id=agent_id,
            agent_type=agent_type,
            typical_tools=set(baseline.get('typical_tools', [])) if baseline else set(),
            avg_calls_per_minute=baseline.get('avg_calls_per_minute', 10) if baseline else 10,
            max_calls_per_minute=baseline.get('max_calls_per_minute', 30) if baseline else 30,
            last_updated=time.time()
        )
        
        # Initialize circuit breaker
        self.circuit_breakers[f"agent_{agent_id}"] = CircuitBreaker(
            name=f"agent_{agent_id}",
            failure_threshold=5,
            recovery_timeout=60
        )
        
        # Initialize cost budget
        self.cost_budgets[agent_id] = CostBudget(
            agent_id=agent_id,
            max_tokens=baseline.get('max_tokens', 100000) if baseline else 100000,
            max_cost_usd=baseline.get('max_cost_usd', 10.0) if baseline else 10.0
        )
    
    def record_tool_call(self, tool_call: ToolCall):
        """Record a tool call"""
        self.tool_calls[tool_call.agent_id].append(tool_call)
        
        # Update rate limiter
        self.rate_limiters[tool_call.agent_id].append(tool_call.timestamp)
        
        # Cleanup old records (keep last 10 minutes)
        cutoff = time.time() - 600
        self.tool_calls[tool_call.agent_id] = [
            tc for tc in self.tool_calls[tool_call.agent_id]
            if tc.timestamp > cutoff
        ]
        self.rate_limiters[tool_call.agent_id] = [
            t for t in self.rate_limiters[tool_call.agent_id]
            if t > cutoff
        ]
    
    def check_anomaly(self, agent_id: str, tool_name: str = None) -> List[dict]:
        """Check for behavioral anomalies"""
        anomalies = []
        
        # Check rate limit
        rate_anomaly = self._check_rate_limit(agent_id)
        if rate_anomaly:
            anomalies.append(rate_anomaly)
        
        # Check tool sequence
        if tool_name:
            sequence_anomaly = self._check_tool_sequence(agent_id, tool_name)
            if sequence_anomaly:
                anomalies.append(sequence_anomaly)
        
        # Check circuit breaker
        circuit_anomaly = self._check_circuit_breaker(agent_id)
        if circuit_anomaly:
            anomalies.append(circuit_anomaly)
        
        # Check cost budget
        cost_anomaly = self._check_cost_budget(agent_id)
        if cost_anomaly:
            anomalies.append(cost_anomaly)
        
        # Check for loops
        loop_anomaly = self._check_loop(agent_id)
        if loop_anomaly:
            anomalies.append(loop_anomaly)
        
        return anomalies
    
    def _check_rate_limit(self, agent_id: str) -> Optional[dict]:
        """Check if agent exceeds rate limit"""
        baseline = self.baselines.get(agent_id)
        if not baseline:
            return None
        
        recent_calls = [
            t for t in self.rate_limiters[agent_id]
            if time.time() - t < 60
        ]
        
        if len(recent_calls) > baseline.max_calls_per_minute:
            anomaly = {
                'type': AnomalyType.RATE_LIMIT,
                'agent_id': agent_id,
                'timestamp': time.time(),
                'details': {
                    'current_rate': len(recent_calls),
                    'max_rate': baseline.max_calls_per_minute
                }
            }
            self.anomaly_log.append(anomaly)
            return anomaly
        
        return None
    
    def _check_tool_sequence(self, agent_id: str, tool_name: str) -> Optional[dict]:
        """Check for suspicious tool sequences"""
        recent_calls = self.tool_calls.get(agent_id, [])[-10:]
        
        if len(recent_calls) < 3:
            return None
        
        # Check for repeated same tool (potential loop)
        last_three = [tc.tool_name for tc in recent_calls[-3:]]
        if len(set(last_three)) == 1:
            anomaly = {
                'type': AnomalyType.TOOL_SEQUENCE,
                'agent_id': agent_id,
                'timestamp': time.time(),
                'details': {
                    'pattern': 'repeated_tool',
                    'tool': tool_name,
                    'count': 3
                }
            }
            self.anomaly_log.append(anomaly)
            return anomaly
        
        return None
    
    def _check_circuit_breaker(self, agent_id: str) -> Optional[dict]:
        """Check circuit breaker status"""
        breaker = self.circuit_breakers.get(f"agent_{agent_id}")
        if not breaker:
            return None
        
        can_execute, reason = breaker.can_execute()
        if not can_execute:
            anomaly = {
                'type': AnomalyType.CIRCUIT_BREAKER,
                'agent_id': agent_id,
                'timestamp': time.time(),
                'details': {
                    'state': breaker.state.value,
                    'failure_count': breaker.failure_count,
                    'reason': reason
                }
            }
            self.anomaly_log.append(anomaly)
            return anomaly
        
        return None
    
    def _check_cost_budget(self, agent_id: str) -> Optional[dict]:
        """Check cost budget"""
        budget = self.cost_budgets.get(agent_id)
        if not budget:
            return None
        
        # Check if approaching limits
        token_pct = budget.current_tokens / budget.max_tokens
        cost_pct = budget.current_cost_usd / budget.max_cost_usd
        
        if token_pct > 0.8 or cost_pct > 0.8:
            anomaly = {
                'type': AnomalyType.COST_BUDGET,
                'agent_id': agent_id,
                'timestamp': time.time(),
                'details': {
                    'token_usage_pct': token_pct * 100,
                    'cost_usage_pct': cost_pct * 100,
                    'tokens': budget.current_tokens,
                    'cost_usd': budget.current_cost_usd
                }
            }
            self.anomaly_log.append(anomaly)
            return anomaly
        
        return None
    
    def _check_loop(self, agent_id: str) -> Optional[dict]:
        """Check for agent loops"""
        recent_calls = self.tool_calls.get(agent_id, [])[-20:]
        
        if len(recent_calls) < 10:
            return None
        
        # Check for A->B->A->B pattern
        tools = [tc.tool_name for tc in recent_calls]
        for i in range(len(tools) - 3):
            if tools[i] == tools[i+2] and tools[i+1] == tools[i+3] and tools[i] != tools[i+1]:
                anomaly = {
                    'type': AnomalyType.LOOP_DETECTED,
                    'agent_id': agent_id,
                    'timestamp': time.time(),
                    'details': {
                        'pattern': f"{tools[i]}->{tools[i+1]}",
                        'occurrences': 2
                    }
                }
                self.anomaly_log.append(anomaly)
                return anomaly
        
        return None
    
    def record_tool_result(self, agent_id: str, success: bool, 
                           tokens: int = 0, cost_usd: float = 0.0):
        """Record tool call result and update circuit breaker"""
        breaker = self.circuit_breakers.get(f"agent_{agent_id}")
        if breaker:
            if success:
                breaker.record_success()
            else:
                breaker.record_failure()
        
        budget = self.cost_budgets.get(agent_id)
        if budget:
            budget.record_spend(tokens, cost_usd)
    
    def can_agent_execute(self, agent_id: str) -> Tuple[bool, str]:
        """Check if agent is allowed to execute"""
        breaker = self.circuit_breakers.get(f"agent_{agent_id}")
        if breaker:
            return breaker.can_execute()
        return True, "No circuit breaker"
    
    def get_agent_stats(self, agent_id: str) -> dict:
        """Get statistics for agent"""
        recent_calls = [
            tc for tc in self.tool_calls.get(agent_id, [])
            if time.time() - tc.timestamp < 300
        ]
        
        return {
            'agent_id': agent_id,
            'total_calls_5min': len(recent_calls),
            'successful_calls': sum(1 for tc in recent_calls if tc.success),
            'failed_calls': sum(1 for tc in recent_calls if not tc.success),
            'avg_duration_ms': (
                sum(tc.duration_ms for tc in recent_calls) / len(recent_calls)
                if recent_calls else 0
            ),
            'circuit_breaker_state': (
                self.circuit_breakers[f"agent_{agent_id}"].state.value
                if f"agent_{agent_id}" in self.circuit_breakers else 'none'
            ),
            'cost_budget': {
                'tokens': self.cost_budgets[agent_id].current_tokens if agent_id in self.cost_budgets else 0,
                'cost_usd': self.cost_budgets[agent_id].current_cost_usd if agent_id in self.cost_budgets else 0
            }
        }
    
    def get_all_anomalies(self, limit: int = 100) -> List[dict]:
        """Get all anomalies"""
        return self.anomaly_log[-limit:]
    
    def export_monitoring_state(self) -> dict:
        """Export complete monitoring state"""
        return {
            'registered_agents': list(self.baselines.keys()),
            'circuit_breakers': {
                name: {
                    'state': cb.state.value,
                    'failure_count': cb.failure_count,
                    'success_count': cb.success_count
                }
                for name, cb in self.circuit_breakers.items()
            },
            'total_anomalies': len(self.anomaly_log),
            'recent_anomalies': self.anomaly_log[-20:]
        }


# Global instance
behavior_monitor = BehavioralMonitor()


def register_agent(agent_id: str, agent_type: str, baseline: dict = None):
    """Convenience function to register agent"""
    behavior_monitor.register_agent(agent_id, agent_type, baseline)


def record_tool_call(tool_call: ToolCall):
    """Convenience function to record tool call"""
    behavior_monitor.record_tool_call(tool_call)


def check_anomaly(agent_id: str, tool_name: str = None) -> List[dict]:
    """Convenience function to check anomalies"""
    return behavior_monitor.check_anomaly(agent_id, tool_name)


def can_execute(agent_id: str) -> Tuple[bool, str]:
    """Convenience function to check if execution allowed"""
    return behavior_monitor.can_agent_execute(agent_id)
