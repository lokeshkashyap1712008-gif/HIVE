"""
HIVE — Arena (The Demo Moment)
Single Agent vs Society — live comparison with scoring.

This is the DEMO judges remember. The arena pits:
- SINGLE: One LLM agent handling a task alone
- SOCIETY: The full HIVE swarm handling the SAME task

Side-by-side live scoring:
- Time to complete
- Findings discovered
- Errors caught
- Confidence scores
- Cost efficiency

The arena can also run Society A vs Society B — different configurations
of agents competing to solve the same problem.

The key insight: societies WIN. But proving it with live metrics is what closes judges.
"""

import asyncio
import time
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
import json

from core.llm_router import chat, QWEN_TURBO
from core.agent_state import get_or_create_state, task_result_to_state
from core.economy import economy
from core.dashboard_events import get_event_stream, emit_artifact
from agents.leader import run_swarm

logger = logging.getLogger(__name__)


class ArenaMode(str, Enum):
    SINGLE_VS_SOCIETY = "single_vs_society"
    SOCIETY_A_VS_SOCIETY_B = "society_a_vs_society_b"
    TIMETRIAL = "timetrial"


@dataclass
class AgentScore:
    """Score breakdown for one competitor."""
    agent_id: str
    mode: str  # "single" or "society_A" or "society_B"

    # Timing
    start_time: float = 0
    end_time: float = 0
    duration_s: float = 0

    # Quality metrics
    findings: list[str] = field(default_factory=list)
    errors_caught: list[str] = field(default_factory=list)
    confidence_scores: list[float] = field(default_factory=list)

    # Cost
    cost: int = 0

    # Outcome
    status: str = "pending"
    result: str = ""

    @property
    def avg_confidence(self) -> float:
        return sum(self.confidence_scores) / max(len(self.confidence_scores), 1)

    def final_score(self) -> float:
        """
        Calculate final arena score (0-100).

        Formula weights:
        - Quality (40%): findings quality, error detection
        - Speed (20%): faster = better
        - Confidence (20%): higher confidence in results
        - Cost-efficiency (20%): lower cost per finding
        """
        # Quality score (0-100)
        quality = min(100, len(self.findings) * 15 + len(self.errors_caught) * 20)
        quality = max(10, quality)  # At least 10 even if nothing found

        # Speed score (0-100): faster = better. 60s = baseline 50
        if self.duration_s > 0:
            speed = max(0, 100 - (self.duration_s / 60) * 50)
        else:
            speed = 50

        # Confidence score (0-100)
        conf = self.avg_confidence * 100

        # Cost efficiency: lower cost per finding = higher score
        if self.findings:
            cost_per_finding = self.cost / len(self.findings)
            cost_eff = max(0, 100 - cost_per_finding * 2)
        else:
            cost_eff = 50  # Neutral if no findings

        total = (quality * 0.40) + (speed * 0.20) + (conf * 0.20) + (cost_eff * 0.20)
        return round(total, 1)


@dataclass
class ArenaMatch:
    """A complete arena match."""
    match_id: str
    task: str
    mode: ArenaMode

    single_score: Optional[AgentScore] = None
    society_a_score: Optional[AgentScore] = None
    society_b_score: Optional[AgentScore] = None

    started_at: float = 0
    completed_at: float = 0
    winner: str = ""  # "single", "society_a", "society_b", "tie"
    winner_margin: float = 0  # score difference percentage

    status: str = "pending"  # "running", "completed"

    def determine_winner(self):
        """Determine winner after both sides complete."""
        scores = []
        if self.single_score and self.single_score.status == "completed":
            scores.append(("single", self.single_score.final_score()))
        if self.society_a_score and self.society_a_score.status == "completed":
            scores.append(("society_a", self.society_a_score.final_score()))
        if self.society_b_score and self.society_b_score.status == "completed":
            scores.append(("society_b", self.society_b_score.final_score()))

        if len(scores) < 2:
            return

        scores.sort(key=lambda x: x[1], reverse=True)
        self.winner = scores[0][0]
        self.winner_margin = scores[0][1] - scores[1][1]
        self.completed_at = time.time()
        self.status = "completed"

    def summary(self) -> dict:
        """Get arena summary for dashboard."""
        return {
            "match_id": self.match_id,
            "task": self.task[:100],
            "mode": self.mode.value,
            "status": self.status,
            "winner": self.winner,
            "winner_margin": self.winner_margin,
            "single_score": self.single_score.final_score() if self.single_score else None,
            "society_a_score": self.society_a_score.final_score() if self.society_a_score else None,
            "society_b_score": self.society_b_score.final_score() if self.society_b_score else None,
            "duration_s": self.completed_at - self.started_at if self.completed_at else 0,
        }


class Arena:
    """
    The arena manager. Runs matches between single agents and societies.
    """

    def __init__(self):
        self.matches: dict[str, ArenaMatch] = {}
        self._running: dict[str, asyncio.Task] = {}
        self.history: list[ArenaMatch] = []
        self.leaderboard: dict[str, dict] = {}  # agent_id -> win/loss/draw

    async def run_single_agent(
        self,
        task: str,
        score: AgentScore,
    ) -> AgentScore:
        """
        Run a task through a SINGLE LLM agent (no swarm).
        This is the baseline — represents a "normal" AI assistant.
        """
        score.start_time = time.time()
        get_event_stream().publish("arena", {
            "phase": "single_started",
            "task_preview": task[:80],
        }, "arena")

        # Run single agent via LLM
        budget_before = economy.budget.available

        result = await chat(
            [
                {"role": "system", "content": "You are a helpful AI assistant. "
                 "Think carefully. Provide thorough, accurate responses. "
                 "When you find something important, note it explicitly."},
                {"role": "user", "content": task},
            ],
            model=QWEN_TURBO,
            temperature=0.4,
            max_tokens=1024,
        )

        score.end_time = time.time()
        score.duration_s = score.end_time - score.start_time
        score.result = result["content"]
        score.cost = budget_before - economy.budget.available
        score.status = "completed"
        score.confidence_scores.append(result.get("confidence", 0.7))

        # Extract "findings" from the response (simple heuristic)
        lines = result["content"].split("\n")
        for line in lines:
            if any(kw in line.lower() for kw in ["found", "discovered", "identified", "note:", "important:", "warning:", "error:"]):
                score.findings.append(line.strip()[:200])

        get_event_stream().publish("arena", {
            "phase": "single_completed",
            "match_id": score.agent_id,
            "duration_s": score.duration_s,
            "findings_count": len(score.findings),
            "final_score": score.final_score(),
        }, "arena")

        return score

    async def run_society(
        self,
        task: str,
        score: AgentScore,
        mode: str = "society",
    ) -> AgentScore:
        """
        Run a task through the HIVE society (full swarm).
        This is what we're proving is BETTER than single agent.
        """
        score.start_time = time.time()
        budget_before = economy.budget.available

        get_event_stream().publish("arena", {
            "phase": "society_started",
            "task_preview": task[:80],
        }, "arena")

        # Run through HIVE swarm
        result = await run_swarm(task, mode="swarm")

        score.end_time = time.time()
        score.duration_s = score.end_time - score.start_time
        score.cost = budget_before - economy.budget.available
        score.status = "completed"

        # Extract data from swarm result
        synthesis = result.get("synthesis", "")
        score.result = synthesis
        score.confidence_scores.append(result.get("debate_confidence", 0.8))

        # Swarm findings: agents' findings + debate findings
        for agent_result in result.get("agent_results", []):
            if agent_result.get("status") == "ok":
                conf = agent_result.get("confidence", 0.7)
                score.confidence_scores.append(conf)

        # Debate findings
        debate_findings = result.get("debate_findings", {})
        if debate_findings:
            for finding in debate_findings.values():
                if isinstance(finding, str) and len(finding) > 20:
                    score.findings.append(finding[:200])

        # Extract findings from synthesis
        for line in synthesis.split("\n"):
            if any(kw in line.lower() for kw in ["found", "discovered", "identified", "note:", "important:", "warning:"]):
                score.findings.append(line.strip()[:200])

        get_event_stream().publish("arena", {
            "phase": "society_completed",
            "task_preview": task[:80],
            "duration_s": score.duration_s,
            "findings_count": len(score.findings),
            "agents_used": result.get("agents_used", []),
            "concerns_raised": result.get("concerns_raised", []),
            "debate_verdict": result.get("debate_verdict"),
            "final_score": score.final_score(),
        }, "arena")

        return score

    async def run_match(self, task: str, mode: ArenaMode = ArenaMode.SINGLE_VS_SOCIETY) -> ArenaMatch:
        """
        THE MAIN ARENA ENTRY POINT.

        Runs a single vs society match. Both sides get the SAME task.
        Side-by-side live scoring.

        Returns the ArenaMatch with full scoring.
        """
        match_id = str(uuid.uuid4())[:8]
        match = ArenaMatch(
            match_id=match_id,
            task=task,
            mode=mode,
            started_at=time.time(),
        )

        self.matches[match_id] = match

        get_event_stream().publish("arena", {
            "match_id": match_id,
            "phase": "match_started",
            "task_preview": task[:80],
        }, "arena")

        if mode == ArenaMode.SINGLE_VS_SOCIETY:
            # Run both sides concurrently
            match.single_score = AgentScore(agent_id="single_agent", mode="single")
            match.society_a_score = AgentScore(agent_id="hive_society", mode="society")

            single_task = asyncio.create_task(
                self.run_single_agent(task, match.single_score)
            )
            society_task = asyncio.create_task(
                self.run_society(task, match.society_a_score)
            )

            # Wait for both
            await asyncio.gather(single_task, society_task)

            # Determine winner
            match.determine_winner()

        elif mode == ArenaMode.SOCIETY_A_VS_SOCIETY_B:
            # Two different swarm configurations
            match.society_a_score = AgentScore(agent_id="society_A", mode="society_a")
            match.society_b_score = AgentScore(agent_id="society_B", mode="society_b")

            task_a = asyncio.create_task(
                self.run_society(task, match.society_a_score, mode="society_a")
            )
            task_b = asyncio.create_task(
                self.run_society(task, match.society_b_score, mode="society_b")
            )

            await asyncio.gather(task_a, task_b)
            match.determine_winner()

        # Record in history
        self.history.append(match)
        if len(self.history) > 50:
            self.history.pop(0)

        # Update leaderboard
        self._update_leaderboard(match)

        # Emit result event
        get_event_stream().publish("arena", {
            "match_id": match_id,
            "phase": "match_completed",
            **match.summary(),
        }, "arena")

        if match.winner == "society" or match.winner == "society_a":
            # Emit a success alert for the demo
            get_event_stream().publish("alert", {
                "type": "success",
                "message": f"SOCIETY WINS! Margin: {match.winner_margin:.1f} points",
            }, "arena")

        return match

    def _update_leaderboard(self, match: ArenaMatch):
        """Update leaderboard from match result."""
        if match.winner == "tie":
            return

        winner_id = f"arena_{match.winner}"
        loser_id = f"arena_{'single' if match.winner not in ('single', 'tie') else 'society'}"

        if winner_id not in self.leaderboard:
            self.leaderboard[winner_id] = {"wins": 0, "losses": 0, "draws": 0}
        if loser_id not in self.leaderboard:
            self.leaderboard[loser_id] = {"wins": 0, "losses": 0, "draws": 0}

        self.leaderboard[winner_id]["wins"] += 1
        self.leaderboard[loser_id]["losses"] += 1

    def get_leaderboard(self) -> list[dict]:
        """Get arena leaderboard."""
        return [
            {
                "agent_id": aid,
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate": round(data["wins"] / max(data["wins"] + data["losses"], 1), 2),
            }
            for aid, data in sorted(
                self.leaderboard.items(),
                key=lambda x: x[1]["wins"],
                reverse=True,
            )
        ]

    def get_match(self, match_id: str) -> Optional[ArenaMatch]:
        return self.matches.get(match_id)

    def recent_matches(self, count: int = 10) -> list[dict]:
        return [m.summary() for m in self.history[-count:]]


# ─── Pre-built demo tasks for hackathon ──────────────────────────────────

DEMO_TASKS = {
    "security_scan": "Scan this URL and find all security vulnerabilities: https://example.com — "
                     "check for OWASP Top 10 issues, report severity and remediation.",

    "code_review": "Review this code for bugs, performance issues, and security problems: "
                   "function auth(user, pass) { return true; } — be thorough and critical.",

    "data_analysis": "Analyze this dataset: [1,2,3,4,5,100,6,7,8,9,10]. "
                      "Find outliers, calculate statistics, and explain what story the data tells.",

    "multi_step": "Research the latest AI developments, write a 200-word summary, "
                  "identify 3 key trends, and rate your confidence in each finding.",

    "debate_test": "Should autonomous AI agents be allowed to make financial transactions "
                   "above $1000 without human approval? Debate this from multiple angles.",
}


# Singleton
arena = Arena()


async def run_arena_demo():
    """
    THE HACKATHON DEMO SCRIPT.

    This runs a curated demo that shows the arena's power.
    Judges get to see single vs society in real time.
    """
    from core.dashboard_events import emit_artifact

    print("\n" + "=" * 60)
    print("HIVE ARENA — Single Agent vs Society Demo")
    print("=" * 60)

    demo_task = DEMO_TASKS["security_scan"]
    print(f"\nTask: {demo_task[:100]}...\n")

    # Run the match
    match = await arena.run_match(demo_task, ArenaMode.SINGLE_VS_SOCIETY)

    # Print results
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")

    if match.single_score:
        print(f"\nSINGLE AGENT:")
        print(f"  Score: {match.single_score.final_score()}/100")
        print(f"  Time: {match.single_score.duration_s:.1f}s")
        print(f"  Cost: {match.single_score.cost} credits")
        print(f"  Findings: {len(match.single_score.findings)}")
        print(f"  Confidence: {match.single_score.avg_confidence:.0%}")

    if match.society_a_score:
        print(f"\nHIVE SOCIETY:")
        print(f"  Score: {match.society_a_score.final_score()}/100")
        print(f"  Time: {match.society_a_score.duration_s:.1f}s")
        print(f"  Cost: {match.society_a_score.cost} credits")
        print(f"  Findings: {len(match.society_a_score.findings)}")
        print(f"  Confidence: {match.society_a_score.avg_confidence:.0%}")

    print(f"\nWINNER: {match.winner.upper()}")
    print(f"MARGIN: {match.winner_margin:.1f} points")

    # Calculate parallel gain
    if match.single_score and match.society_a_score:
        single_score = match.single_score.final_score()
        society_score = match.society_a_score.final_score()
        if society_score > single_score:
            improvement = ((society_score - single_score) / single_score) * 100
            print(f"SOCIETY IMPROVEMENT: +{improvement:.0f}% vs single agent")

    return match


def get_arena_status() -> dict:
    """Get arena status for dashboard."""
    return {
        "total_matches": len(arena.history),
        "recent_matches": arena.recent_matches(5),
        "leaderboard": arena.get_leaderboard(),
    }