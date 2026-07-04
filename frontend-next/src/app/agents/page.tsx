"use client";

import { useEffect, useState } from "react";
import {
  Users,
  Brain,
  Code,
  Search,
  Shield,
  Heart,
  Cpu,
  Activity,
} from "lucide-react";

interface Agent {
  id: string;
  type: string;
  status: string;
  emotion: string;
  confidence: number;
  stress: number;
  workload: number;
  current_task?: string;
}

const agentMeta: Record<string, { icon: any; color: string; desc: string }> = {
  leader: {
    icon: Brain,
    color: "#f59e0b",
    desc: "Orchestrates task decomposition and agent coordination",
  },
  code_writer: {
    icon: Code,
    color: "#6366f1",
    desc: "Generates and writes code across multiple languages",
  },
  code_reviewer: {
    icon: Search,
    color: "#8b5cf6",
    desc: "Reviews code for bugs, style, and security issues",
  },
  security_scout: {
    icon: Shield,
    color: "#ef4444",
    desc: "Scans for vulnerabilities using OWASP Top 10",
  },
  tester: {
    icon: Activity,
    color: "#22c55e",
    desc: "Writes and runs unit/integration tests",
  },
  memory_keeper: {
    icon: Heart,
    color: "#ec4899",
    desc: "Maintains long-term memory and context",
  },
  executor: {
    icon: Cpu,
    color: "#3b82f6",
    desc: "Executes commands in sandboxed environments",
  },
};

const statusColors: Record<string, string> = {
  idle: "bg-slate-500",
  working: "bg-accent",
  sleeping: "bg-info",
  error: "bg-danger",
  coordinating: "bg-warning",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const res = await fetch("/api/agents/states", { signal: controller.signal });
        clearTimeout(timeoutId);

        const data = await res.json();
        setAgents(data.agents || []);
      } catch {
        // silently catch errors
      } finally {
        setLoading(false);
      }
    };
    fetchAgents();
    const interval = setInterval(fetchAgents, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Users className="text-accent" />
            Agent Registry
          </h1>
          <p className="text-slate-500 mt-1">Monitor and manage your swarm agents</p>
        </div>
        <div className="grid grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="glass-card animate-pulse">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-xl bg-white/10" />
                <div>
                  <div className="h-4 bg-white/10 rounded w-24 mb-2" />
                  <div className="h-3 bg-white/10 rounded w-16" />
                </div>
              </div>
              <div className="h-3 bg-white/10 rounded w-full mb-3" />
              <div className="space-y-3">
                <div className="h-3 bg-white/10 rounded w-full" />
                <div className="h-3 bg-white/10 rounded w-full" />
                <div className="h-3 bg-white/10 rounded w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Add default agents if none exist
  const displayAgents =
    agents.length > 0
      ? agents
      : [
          { id: "leader-1", type: "leader", status: "idle", emotion: "neutral", confidence: 0.9, stress: 0.2, workload: 0 },
          { id: "code_writer-1", type: "code_writer", status: "idle", emotion: "focused", confidence: 0.85, stress: 0.1, workload: 0 },
          { id: "code_reviewer-1", type: "code_reviewer", status: "idle", emotion: "neutral", confidence: 0.88, stress: 0.15, workload: 0 },
          { id: "security_scout-1", type: "security_scout", status: "idle", emotion: "neutral", confidence: 0.82, stress: 0.1, workload: 0 },
          { id: "tester-1", type: "tester", status: "idle", emotion: "neutral", confidence: 0.8, stress: 0.1, workload: 0 },
          { id: "executor-1", type: "executor", status: "idle", emotion: "neutral", confidence: 0.75, stress: 0.05, workload: 0 },
        ];

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Users className="text-accent" />
          Agent Registry
        </h1>
        <p className="text-slate-500 mt-1">
          Monitor and manage your swarm agents
        </p>
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-3 gap-6">
        {displayAgents.map((agent) => {
          const meta = agentMeta[agent.type] || {
            icon: Cpu,
            color: "#64748b",
            desc: "Unknown agent type",
          };
          const Icon = meta.icon;
          return (
            <div key={agent.id} className="glass-card group">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: `${meta.color}20` }}
                  >
                    <Icon size={24} style={{ color: meta.color }} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white capitalize">
                      {agent.type?.replace("_", " ")}
                    </h3>
                    <p className="text-xs text-slate-500">{agent.id}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      statusColors[agent.status] || "bg-slate-500"
                    }`}
                  />
                  <span className="text-xs text-slate-400 capitalize">
                    {agent.status}
                  </span>
                </div>
              </div>

              <p className="text-sm text-slate-400 mb-4">{meta.desc}</p>

              <div className="space-y-3">
                {/* Confidence */}
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-500">Confidence</span>
                    <span className="text-white">
                      {(agent.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-success transition-all"
                      style={{ width: `${agent.confidence * 100}%` }}
                    />
                  </div>
                </div>

                {/* Stress */}
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-500">Stress</span>
                    <span className="text-white">
                      {(agent.stress * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${agent.stress * 100}%`,
                        backgroundColor:
                          agent.stress > 0.8
                            ? "#ef4444"
                            : agent.stress > 0.5
                            ? "#f59e0b"
                            : "#22c55e",
                      }}
                    />
                  </div>
                </div>

                {/* Workload */}
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-500">Workload</span>
                    <span className="text-white">
                      {(agent.workload * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{ width: `${agent.workload * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Emotion */}
              <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                <span className="text-xs text-slate-500">Emotion</span>
                <span className="text-sm capitalize">{agent.emotion}</span>
              </div>

              {agent.current_task && (
                <div className="mt-2 p-2 rounded-lg bg-white/3">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                    Current Task
                  </span>
                  <p className="text-xs text-slate-300 mt-1 truncate">
                    {agent.current_task}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
