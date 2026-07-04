"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  Zap,
  DollarSign,
  AlertTriangle,
  CheckCircle,
  Clock,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface Metric {
  label: string;
  value: string | number;
  icon: any;
  color: string;
  change?: string;
}

interface AgentNode {
  id: string;
  type: string;
  status: string;
  emotion: string;
  stress: number;
}

const statusColors: Record<string, string> = {
  idle: "bg-slate-500",
  working: "bg-accent",
  sleeping: "bg-info",
  error: "bg-danger",
  coordinating: "bg-warning",
};

const emotionIcons: Record<string, string> = {
  neutral: "😐",
  focused: "🎯",
  excited: "⚡",
  tired: "😴",
  confused: "🤔",
  proud: "✨",
};

export default function DashboardPage() {
  const [agents, setAgents] = useState<AgentNode[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  // Poll for data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const [agentsRes, healthRes, tasksRes] = await Promise.allSettled([
          fetch("/api/agents/states", { signal: controller.signal }),
          fetch("/health", { signal: controller.signal }),
          fetch("/api/tasks", { signal: controller.signal }),
        ]);

        clearTimeout(timeoutId);

        if (agentsRes.status === "fulfilled") {
          const data = await agentsRes.value.json();
          setAgents(data.agents || []);
        }
        if (healthRes.status === "fulfilled") {
          const data = await healthRes.value.json();
          setHealth(data);
        }
        if (tasksRes.status === "fulfilled") {
          const data = await tasksRes.value.json();
          setTasks(data.tasks || []);
        }
        setConnected(true);
      } catch {
        setConnected(false);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  // SSE events
  useEffect(() => {
    const evtSource = new EventSource("/events");
    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [data, ...prev].slice(0, 50));
      } catch {}
    };
    evtSource.onerror = () => {};
    return () => evtSource.close();
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-slate-500 mt-1">Real-time swarm intelligence overview</p>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card animate-pulse">
              <div className="h-4 bg-white/10 rounded w-20 mb-3" />
              <div className="h-8 bg-white/10 rounded w-16" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 glass-card animate-pulse">
            <div className="h-6 bg-white/10 rounded w-40 mb-4" />
            <div className="h-80 bg-white/5 rounded" />
          </div>
          <div className="glass-card animate-pulse">
            <div className="h-6 bg-white/10 rounded w-32 mb-4" />
            <div className="h-80 bg-white/5 rounded" />
          </div>
        </div>
        <div className="glass-card animate-pulse">
          <div className="h-6 bg-white/10 rounded w-32 mb-4" />
          <div className="h-40 bg-white/5 rounded" />
        </div>
      </div>
    );
  }

  const metrics: Metric[] = [
    {
      label: "Active Agents",
      value: health?.active_agents ?? agents.length,
      icon: Cpu,
      color: "text-accent",
      change: "+2",
    },
    {
      label: "Queue Depth",
      value: health?.queue_depth ?? 0,
      icon: Clock,
      color: "text-info",
    },
    {
      label: "Budget",
      value: `$${(health?.budget_available ?? 0).toFixed(1)}`,
      icon: DollarSign,
      color: "text-success",
    },
    {
      label: "Swarm Health",
      value: `${((health?.swarm_health ?? 0) * 100).toFixed(0)}%`,
      icon: Activity,
      color: "text-warning",
    },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-500 mt-1">
            Real-time swarm intelligence overview
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              connected ? "bg-success" : "bg-danger"
            } animate-pulse`}
          />
          <span className="text-sm text-slate-400">
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-4 gap-6">
        {metrics.map((m) => {
          const Icon = m.icon;
          return (
            <div key={m.label} className="glass-card">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500">{m.label}</span>
                <Icon size={18} className={m.color} />
              </div>
              <div className="mt-3">
                <span className="text-3xl font-bold text-white">{m.value}</span>
                {m.change && (
                  <span className="ml-2 text-xs text-success">{m.change}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Agent Graph */}
        <div className="col-span-2 glass-card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Agent Topology
          </h2>
          <div className="relative h-80">
            {/* SVG Agent Graph */}
            <svg className="w-full h-full" viewBox="0 0 600 300">
              {/* Connections */}
              {agents.length > 1 &&
                agents.slice(1).map((agent, i) => {
                  const parentIdx = 0;
                  const x1 = 300;
                  const y1 = 60;
                  const x2 = 80 + (i % 4) * 140;
                  const y2 = 150 + Math.floor(i / 4) * 100;
                  return (
                    <line
                      key={`conn-${i}`}
                      x1={x1}
                      y1={y1 + 20}
                      x2={x2}
                      y2={y2 - 20}
                      stroke={agent.status === "working" ? "#6366f1" : "#333"}
                      strokeWidth={agent.status === "working" ? 2 : 1}
                      strokeDasharray={agent.status === "working" ? "none" : "4,4"}
                    />
                  );
                })}

              {/* Agent Nodes */}
              {agents.map((agent, i) => {
                const isLeader = i === 0;
                const x = isLeader ? 300 : 80 + ((i - 1) % 4) * 140;
                const y = isLeader ? 60 : 150 + Math.floor((i - 1) / 4) * 100;
                const color = statusColors[agent.status] || "bg-slate-500";
                return (
                  <g key={agent.id}>
                    <circle
                      cx={x}
                      cy={y}
                      r={isLeader ? 28 : 22}
                      fill={agent.status === "working" ? "#6366f120" : "#1a1a2e"}
                      stroke={agent.status === "working" ? "#6366f1" : "#444"}
                      strokeWidth={2}
                    />
                    <circle cx={x} cy={y - (isLeader ? 35 : 30)} r={4} fill={color.replace("bg-", "#").replace("slate-500", "#64748b").replace("accent", "#6366f1").replace("info", "#3b82f6").replace("success", "#22c55e").replace("warning", "#f59e0b").replace("danger", "#ef4444")} />
                    <text
                      x={x}
                      y={y + 5}
                      textAnchor="middle"
                      fontSize={isLeader ? 16 : 12}
                      fill="white"
                    >
                      {agent.type?.slice(0, 3).toUpperCase() || "?"}
                    </text>
                    <text
                      x={x}
                      y={y + (isLeader ? 22 : 18)}
                      textAnchor="middle"
                      fontSize={8}
                      fill="#94a3b8"
                    >
                      {emotionIcons[agent.emotion] || ""}
                    </text>
                    {/* Stress bar */}
                    <rect
                      x={x - 15}
                      y={y + (isLeader ? 32 : 26)}
                      width={30}
                      height={3}
                      rx={1.5}
                      fill="#1a1a2e"
                    />
                    <rect
                      x={x - 15}
                      y={y + (isLeader ? 32 : 26)}
                      width={30 * (agent.stress || 0)}
                      height={3}
                      rx={1.5}
                      fill={
                        agent.stress > 0.8
                          ? "#ef4444"
                          : agent.stress > 0.5
                          ? "#f59e0b"
                          : "#22c55e"
                      }
                    />
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Recent Events */}
        <div className="glass-card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Live Events
          </h2>
          <div className="space-y-2 overflow-y-auto max-h-80">
            {events.length === 0 && (
              <p className="text-slate-500 text-sm">No events yet...</p>
            )}
            {events.map((event, i) => (
              <div
                key={i}
                className="p-3 rounded-lg bg-white/3 border border-white/5 text-sm"
              >
                <div className="flex items-center gap-2">
                  <Zap size={12} className="text-accent" />
                  <span className="text-white font-medium">
                    {event.type || "event"}
                  </span>
                  <span className="text-slate-600 text-xs ml-auto">
                    {event.time
                      ? new Date(event.time).toLocaleTimeString()
                      : ""}
                  </span>
                </div>
                {event.message && (
                  <p className="text-slate-400 mt-1 text-xs">{event.message}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Tasks */}
      <div className="glass-card">
        <h2 className="text-lg font-semibold text-white mb-4">Recent Tasks</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Task
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Mode
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Status
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Tokens
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Time
                </th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-500">
                    No tasks yet. Submit one from the Terminal.
                  </td>
                </tr>
              )}
              {tasks.slice(0, 10).map((task) => (
                <tr
                  key={task.id}
                  className="border-b border-white/5 hover:bg-white/3"
                >
                  <td className="py-3 px-4 text-white">
                    {task.description?.slice(0, 60)}
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-1 rounded-full text-xs bg-accent/20 text-accent">
                      {task.mode}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`flex items-center gap-1.5 ${
                        task.status === "completed"
                          ? "text-success"
                          : task.status === "failed"
                          ? "text-danger"
                          : "text-warning"
                      }`}
                    >
                      {task.status === "completed" ? (
                        <CheckCircle size={14} />
                      ) : task.status === "failed" ? (
                        <AlertTriangle size={14} />
                      ) : (
                        <Clock size={14} />
                      )}
                      {task.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-400">
                    {task.tokens_used?.toLocaleString() || 0}
                  </td>
                  <td className="py-3 px-4 text-slate-400">
                    {task.time_taken?.toFixed(1) || 0}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
