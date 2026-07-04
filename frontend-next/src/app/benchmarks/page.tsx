"use client";

import { useEffect, useState } from "react";
import { BarChart3, Play, Trophy, TrendingUp, Loader2 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface BenchmarkResult {
  id: string;
  name: string;
  single_agent_score: number;
  society_score: number;
  improvement_pct: number;
  run_timestamp: string;
}

export default function BenchmarksPage() {
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult[]>([]);
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    // Demo data since backend may not have benchmarks
    setBenchmarks([
      {
        id: "bench-1",
        name: "Code Generation",
        single_agent_score: 72,
        society_score: 89,
        improvement_pct: 23.6,
        run_timestamp: new Date().toISOString(),
      },
      {
        id: "bench-2",
        name: "Bug Detection",
        single_agent_score: 65,
        society_score: 91,
        improvement_pct: 40.0,
        run_timestamp: new Date().toISOString(),
      },
      {
        id: "bench-3",
        name: "Code Review",
        single_agent_score: 70,
        society_score: 88,
        improvement_pct: 25.7,
        run_timestamp: new Date().toISOString(),
      },
      {
        id: "bench-4",
        name: "Architecture Design",
        single_agent_score: 60,
        society_score: 85,
        improvement_pct: 41.7,
        run_timestamp: new Date().toISOString(),
      },
      {
        id: "bench-5",
        name: "Test Coverage",
        single_agent_score: 58,
        society_score: 82,
        improvement_pct: 41.4,
        run_timestamp: new Date().toISOString(),
      },
    ]);
  }, []);

  const runBenchmark = async (id: string) => {
    setRunning(id);
    // Simulate running
    await new Promise((r) => setTimeout(r, 2000));
    setRunning(null);
  };

  const chartData = benchmarks.map((b) => ({
    name: b.name.slice(0, 15),
    "Single Agent": b.single_agent_score,
    "HIVE Swarm": b.society_score,
  }));

  const avgImprovement =
    benchmarks.length > 0
      ? benchmarks.reduce((sum, b) => sum + b.improvement_pct, 0) /
        benchmarks.length
      : 0;

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <BarChart3 className="text-accent" />
          Benchmarks
        </h1>
        <p className="text-slate-500 mt-1">
          Compare single-agent vs swarm performance across tasks
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-6">
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-2">
            <Trophy size={18} className="text-warning" />
            <span className="text-sm text-slate-500">Avg Improvement</span>
          </div>
          <div className="text-3xl font-bold text-success">
            +{avgImprovement.toFixed(1)}%
          </div>
        </div>
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={18} className="text-accent" />
            <span className="text-sm text-slate-500">Benchmarks Run</span>
          </div>
          <div className="text-3xl font-bold text-white">
            {benchmarks.length}
          </div>
        </div>
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-2">
            <Trophy size={18} className="text-success" />
            <span className="text-sm text-slate-500">Swarm Wins</span>
          </div>
          <div className="text-3xl font-bold text-success">
            {benchmarks.filter((b) => b.society_score > b.single_agent_score).length}/
            {benchmarks.length}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="glass-card">
        <h2 className="text-lg font-semibold text-white mb-4">
          Performance Comparison
        </h2>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barGap={4}>
              <XAxis
                dataKey="name"
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                axisLine={{ stroke: "#333" }}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                axisLine={{ stroke: "#333" }}
                domain={[0, 100]}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1a2e",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "8px",
                  color: "#f1f5f9",
                }}
              />
              <Legend />
              <Bar dataKey="Single Agent" fill="#64748b" radius={[4, 4, 0, 0]} />
              <Bar dataKey="HIVE Swarm" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Benchmark List */}
      <div className="glass-card">
        <h2 className="text-lg font-semibold text-white mb-4">
          Benchmark Results
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Benchmark
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Single Agent
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  HIVE Swarm
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Improvement
                </th>
                <th className="text-left py-3 px-4 text-slate-500 font-medium">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((b) => (
                <tr
                  key={b.id}
                  className="border-b border-white/5 hover:bg-white/3"
                >
                  <td className="py-3 px-4 text-white font-medium">
                    {b.name}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-slate-500"
                          style={{ width: `${b.single_agent_score}%` }}
                        />
                      </div>
                      <span className="text-slate-400">
                        {b.single_agent_score}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${b.society_score}%` }}
                        />
                      </div>
                      <span className="text-white">{b.society_score}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-success font-medium">
                      +{b.improvement_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <button
                      onClick={() => runBenchmark(b.id)}
                      disabled={running === b.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/20 text-accent text-xs hover:bg-accent/30 transition-colors disabled:opacity-50"
                    >
                      {running === b.id ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Play size={12} />
                      )}
                      {running === b.id ? "Running..." : "Run"}
                    </button>
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
