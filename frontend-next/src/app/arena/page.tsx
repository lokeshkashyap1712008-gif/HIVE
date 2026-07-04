"use client";

import { useState } from "react";
import { Swords, Loader2, Trophy, Zap, Clock } from "lucide-react";

interface ArenaResult {
  single: { result: any; time: number; tokens: number };
  swarm: { result: any; time: number; tokens: number };
}

export default function ArenaPage() {
  const [task, setTask] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ArenaResult | null>(null);

  const runArena = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!task.trim() || loading) return;
    setLoading(true);
    try {
      const res = await fetch("/api/arena", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const winner = result
    ? result.single.time < result.swarm.time
      ? "single"
      : "swarm"
    : null;

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Swords className="text-accent" />
          Arena
        </h1>
        <p className="text-slate-500 mt-1">
          Compare single-agent vs swarm performance on the same task
        </p>
      </div>

      {/* Task Input */}
      <div className="glass-card">
        <form onSubmit={runArena} className="flex gap-4">
          <input
            type="text"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Enter a task to benchmark..."
            className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 font-mono text-sm"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !task.trim()}
            className="px-8 py-3 rounded-xl bg-accent hover:bg-accent-hover text-white font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Swords size={16} />
            )}
            {loading ? "Running..." : "Run Arena"}
          </button>
        </form>
      </div>

      {/* Results */}
      {result && (
        <div className="grid grid-cols-2 gap-6">
          {/* Single Agent */}
          <div
            className={`glass-card relative ${
              winner === "single" ? "ring-2 ring-success" : ""
            }`}
          >
            {winner === "single" && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-success/20 text-success text-xs font-medium flex items-center gap-1">
                <Trophy size={12} /> Winner
              </div>
            )}
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-info/20 flex items-center justify-center">
                <Zap size={16} className="text-info" />
              </span>
              Single Agent
            </h3>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-white/3">
                  <div className="text-xs text-slate-500">Time</div>
                  <div className="text-xl font-bold text-white">
                    {result.single.time?.toFixed(1)}s
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-white/3">
                  <div className="text-xs text-slate-500">Tokens</div>
                  <div className="text-xl font-bold text-white">
                    {result.single.tokens?.toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-white/3">
                <div className="text-xs text-slate-500 mb-2">Result</div>
                <pre className="text-sm text-slate-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                  {typeof result.single.result === "string"
                    ? result.single.result
                    : JSON.stringify(result.single.result, null, 2)}
                </pre>
              </div>
            </div>
          </div>

          {/* Swarm */}
          <div
            className={`glass-card relative ${
              winner === "swarm" ? "ring-2 ring-success" : ""
            }`}
          >
            {winner === "swarm" && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-success/20 text-success text-xs font-medium flex items-center gap-1">
                <Trophy size={12} /> Winner
              </div>
            )}
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
                <Swords size={16} className="text-accent" />
              </span>
              HIVE Swarm
            </h3>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-white/3">
                  <div className="text-xs text-slate-500">Time</div>
                  <div className="text-xl font-bold text-white">
                    {result.swarm.time?.toFixed(1)}s
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-white/3">
                  <div className="text-xs text-slate-500">Tokens</div>
                  <div className="text-xl font-bold text-white">
                    {result.swarm.tokens?.toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-white/3">
                <div className="text-xs text-slate-500 mb-2">Result</div>
                <pre className="text-sm text-slate-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                  {typeof result.swarm.result === "string"
                    ? result.swarm.result
                    : JSON.stringify(result.swarm.result, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preset tasks */}
      {!result && (
        <div className="glass-card">
          <h3 className="text-lg font-semibold text-white mb-4">
            Try These Tasks
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              "Write a Python function to find all prime numbers up to n",
              "Design a REST API for a task management app",
              "Debug this code: def f(x): return x + '1' where x is int",
              "Write unit tests for a StringCalculator class",
              "Explain the CAP theorem with real-world examples",
              "Create a SQL schema for an e-commerce platform",
            ].map((preset) => (
              <button
                key={preset}
                onClick={() => setTask(preset)}
                className="p-3 rounded-xl bg-white/3 border border-white/5 text-left text-sm text-slate-400 hover:text-white hover:border-accent/30 transition-all"
              >
                {preset}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
