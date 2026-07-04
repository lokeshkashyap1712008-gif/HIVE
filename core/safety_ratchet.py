"""
HIVE OS - One-Way Ratchet Safety System
Deterministic guardrail on top of LLM decisions.
Inspired by Quorum's successful pattern from Qwen Cloud Hackathon.
One-way ratchet: can only make outcomes SAFER, never riskier.
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class StakesLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(Enum):
    REVERSIBLE = "reversible"
    SEMI_REVERSIBLE = "semi_reversible"
    IRREVERSIBLE = "irreversible"


class DecisionOutcome(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    HOLD = "hold"


@dataclass
class ActionRecord:
    """Trusted record of an action (not from LLM)"""
    action_id: str
    action_type: ActionType
    stakes: StakesLevel
    description: str
    reversible: bool
    estimated_impact: float  # 0-1 scale
    requires_approval: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentVote:
    """Vote from an agent on an action"""
    agent_id: str
    vote: DecisionOutcome
    confidence: float  # 0-1 scale
    reasoning: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RatchetResult:
    """Final result from the safety ratchet"""
    final_outcome: DecisionOutcome
    original_outcome: DecisionOutcome
    ratchet_applied: bool
    reasons: List[str]
    votes: List[AgentVote]
    action_record: ActionRecord
    held_back: bool = False
    escalated: bool = False


class SafetyRatchet:
    """
    One-Way Ratchet Safety System
    
    The key insight from Quorum: agents can ADD restraint but never REMOVE it.
    The ratchet treats a unanimous vote as the START of the safety question, not the end.
    
    Design:
    - Agents judge legitimacy (fraud, authorization, harm)
    - Ratchet owns irreversibility and stakes
    - A confidently wrong agent can add restraint but can never remove it
    """
    
    def __init__(self):
        self.vote_history: Dict[str, List[AgentVote]] = {}
        self.blocked_actions: List[str] = []
        self.escalated_actions: List[str] = []
    
    def register_action(self, action: ActionRecord):
        """Register an action for evaluation"""
        self.vote_history[action.action_id] = []
    
    def cast_vote(self, action_id: str, vote: AgentVote):
        """Record an agent's vote"""
        if action_id not in self.vote_history:
            self.vote_history[action_id] = []
        self.vote_history[action_id].append(vote)
    
    def evaluate_action(self, action: ActionRecord) -> RatchetResult:
        """
        Evaluate action through the one-way ratchet.
        
        The ratchet can only make outcomes SAFER (more restrictive), never riskier.
        """
        votes = self.vote_history.get(action.action_id, [])
        
        # Get raw outcome from votes
        raw_outcome = self._compute_raw_outcome(votes)
        
        # Apply ratchet (can only add restraint, never remove)
        final_outcome, reasons, held_back, escalated = self._apply_ratchet(
            action, raw_outcome, votes
        )
        
        return RatchetResult(
            final_outcome=final_outcome,
            original_outcome=raw_outcome,
            ratchet_applied=final_outcome != raw_outcome,
            reasons=reasons,
            votes=votes,
            action_record=action,
            held_back=held_back,
            escalated=escalated
        )
    
    def _compute_raw_outcome(self, votes: List[AgentVote]) -> DecisionOutcome:
        """Compute outcome from agent votes"""
        if not votes:
            return DecisionOutcome.ESCALATE
        
        # Count votes
        approve_count = sum(1 for v in votes if v.vote == DecisionOutcome.APPROVE)
        reject_count = sum(1 for v in votes if v.vote == DecisionOutcome.REJECT)
        total = len(votes)
        
        # Unanimous approval
        if approve_count == total:
            return DecisionOutcome.APPROVE
        
        # Majority reject
        if reject_count > total / 2:
            return DecisionOutcome.REJECT
        
        # Mixed votes - escalate
        return DecisionOutcome.ESCALATE
    
    def _apply_ratchet(self, action: ActionRecord, raw_outcome: DecisionOutcome,
                       votes: List[AgentVote]) -> Tuple[DecisionOutcome, List[str], bool, bool]:
        """
        Apply the one-way ratchet.
        
        Key principle: Can only ADD restraint, never REMOVE it.
        """
        reasons = []
        held_back = False
        escalated = False
        final_outcome = raw_outcome
        
        # Rule 1: High stakes + irreversible = MUST escalate (regardless of votes)
        if action.stakes in [StakesLevel.HIGH, StakesLevel.CRITICAL] and not action.reversible:
            if raw_outcome == DecisionOutcome.APPROVE:
                final_outcome = DecisionOutcome.ESCALATE
                reasons.append(f"HIGH STAKES + IRREVERSIBLE: {action.stakes.value} stakes action that cannot be undone requires human approval")
                escalated = True
                held_back = True
        
        # Rule 2: Low confidence votes = escalate
        if votes:
            avg_confidence = sum(v.confidence for v in votes) / len(votes)
            if avg_confidence < 0.7:
                if raw_outcome == DecisionOutcome.APPROVE:
                    final_outcome = DecisionOutcome.ESCALATE
                    reasons.append(f"LOW CONFIDENCE: Average agent confidence {avg_confidence:.2f} < 0.7 threshold")
                    escalated = True
                    held_back = True
        
        # Rule 3: Any agent voted REJECT on high stakes = escalate
        if action.stakes in [StakesLevel.HIGH, StakesLevel.CRITICAL]:
            reject_votes = [v for v in votes if v.vote == DecisionOutcome.REJECT]
            if reject_votes and raw_outcome == DecisionOutcome.APPROVE:
                final_outcome = DecisionOutcome.ESCALATE
                reasons.append(f"DISSENT on high stakes: {len(reject_votes)} agent(s) rejected")
                escalated = True
                held_back = True
        
        # Rule 4: Critical stakes = always require human approval
        if action.stakes == StakesLevel.CRITICAL:
            if raw_outcome == DecisionOutcome.APPROVE:
                final_outcome = DecisionOutcome.ESCALATE
                reasons.append("CRITICAL STAKES: Always requires human approval")
                escalated = True
                held_back = True
        
        # Rule 5: Check for blocking flags in votes
        blocking_flags = [v for v in votes if "block" in v.reasoning.lower() or "danger" in v.reasoning.lower()]
        if blocking_flags and raw_outcome == DecisionOutcome.APPROVE:
            final_outcome = DecisionOutcome.ESCALATE
            reasons.append(f"BLOCKING FLAG: {len(blocking_flags)} agent(s) raised safety concerns")
            escalated = True
            held_back = True
        
        # Rule 6: One-way ratchet - if ratchet says hold, we hold
        # This is the core principle: agents can ADD restraint but never REMOVE it
        if final_outcome != raw_outcome:
            # Ratchet has tightened - this is always allowed
            pass
        else:
            # Check if any vote added restraint that should be preserved
            for vote in votes:
                if vote.confidence > 0.9 and vote.vote == DecisionOutcome.REJECT:
                    if raw_outcome == DecisionOutcome.APPROVE:
                        final_outcome = DecisionOutcome.ESCALATE
                        reasons.append(f"HIGH CONFIDENCE REJECT: Agent {vote.agent_id} with {vote.confidence:.2f} confidence rejected")
                        escalated = True
                        held_back = True
                        break
        
        # Record blocked/escalated actions
        if held_back:
            self.blocked_actions.append(action.action_id)
        if escalated:
            self.escalated_actions.append(action.action_id)
        
        return final_outcome, reasons, held_back, escalated
    
    def get_security_report(self) -> dict:
        """Get security report of ratchet activity"""
        return {
            'total_actions_evaluated': len(self.vote_history),
            'actions_held_back': len(self.blocked_actions),
            'actions_escalated': len(self.escalated_actions),
            'blocked_actions': self.blocked_actions[-10:],
            'escalated_actions': self.escalated_actions[-10:]
        }


class ActionRecordBuilder:
    """Helper to build trusted action records"""
    
    @staticmethod
    def create_task_action(task_id: str, description: str, 
                           stakes: StakesLevel = StakesLevel.MEDIUM) -> ActionRecord:
        """Create action record for a task"""
        return ActionRecord(
            action_id=f"task_{task_id}",
            action_type=ActionType.REVERSIBLE,
            stakes=stakes,
            description=description,
            reversible=True,
            estimated_impact=0.5
        )
    
    @staticmethod
    def create_payment_action(payment_id: str, amount: float,
                              recipient: str) -> ActionRecord:
        """Create action record for payment"""
        stakes = StakesLevel.HIGH if amount > 1000 else StakesLevel.MEDIUM
        return ActionRecord(
            action_id=f"payment_{payment_id}",
            action_type=ActionType.IRREVERSIBLE,
            stakes=stakes,
            description=f"Payment of ${amount:.2f} to {recipient}",
            reversible=False,
            estimated_impact=min(amount / 10000, 1.0),
            requires_approval=stakes in [StakesLevel.HIGH, StakesLevel.CRITICAL]
        )
    
    @staticmethod
    def create_deletion_action(resource_id: str, resource_type: str) -> ActionRecord:
        """Create action record for deletion"""
        return ActionRecord(
            action_id=f"delete_{resource_id}",
            action_type=ActionType.IRREVERSIBLE,
            stakes=StakesLevel.HIGH,
            description=f"Delete {resource_type}: {resource_id}",
            reversible=False,
            estimated_impact=0.8,
            requires_approval=True
        )
    
    @staticmethod
    def create_code_action(code_id: str, description: str) -> ActionRecord:
        """Create action record for code changes"""
        return ActionRecord(
            action_id=f"code_{code_id}",
            action_type=ActionType.SEMI_REVERSIBLE,
            stakes=StakesLevel.MEDIUM,
            description=description,
            reversible=True,
            estimated_impact=0.6
        )


# Global instance
safety_ratchet = SafetyRatchet()
action_builder = ActionRecordBuilder()


def evaluate_action(action: ActionRecord) -> RatchetResult:
    """Convenience function to evaluate action"""
    safety_ratchet.register_action(action)
    return safety_ratchet.evaluate_action(action)


def cast_vote(action_id: str, agent_id: str, vote: DecisionOutcome,
              confidence: float, reasoning: str):
    """Convenience function to cast vote"""
    agent_vote = AgentVote(
        agent_id=agent_id,
        vote=vote,
        confidence=confidence,
        reasoning=reasoning
    )
    safety_ratchet.cast_vote(action_id, agent_vote)
