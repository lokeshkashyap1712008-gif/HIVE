"use client";

import { useEffect, useState } from "react";
import { Wallet, TrendingUp, TrendingDown, DollarSign, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

interface Transaction {
  id: string;
  agent_id: string;
  amount: number;
  reason: string;
  timestamp: number;
}

interface EconomyData {
  budget: number;
  total_earned: number;
  total_spent: number;
  transactions: Transaction[];
}

export default function EconomyPage() {
  const [economy, setEconomy] = useState<EconomyData | null>(null);

  useEffect(() => {
    const fetchEconomy = async () => {
      try {
        const res = await fetch("/api/economy");
        const data = await res.json();
        setEconomy(data);
      } catch {}
    };
    fetchEconomy();
    const interval = setInterval(fetchEconomy, 5000);
    return () => clearInterval(interval);
  }, []);

  const data = economy || { budget: 100, total_earned: 0, total_spent: 0, transactions: [] };

  const pieData = [
    { name: "Available", value: Math.max(0, data.budget), color: "#22c55e" },
    { name: "Spent", value: data.total_spent, color: "#ef4444" },
    { name: "Earned", value: data.total_earned, color: "#6366f1" },
  ].filter((d) => d.value > 0);

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Wallet className="text-accent" />
          Economy
        </h1>
        <p className="text-slate-500 mt-1">
          Track token budgets and agent transactions
        </p>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-4 gap-6">
        <div className="glass-card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500">Budget</span>
            <DollarSign size={18} className="text-success" />
          </div>
          <div className="text-3xl font-bold text-white">
            ${data.budget.toFixed(1)}
          </div>
        </div>
        <div className="glass-card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500">Earned</span>
            <TrendingUp size={18} className="text-accent" />
          </div>
          <div className="text-3xl font-bold text-white">
            ${data.total_earned.toFixed(1)}
          </div>
        </div>
        <div className="glass-card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500">Spent</span>
            <TrendingDown size={18} className="text-danger" />
          </div>
          <div className="text-3xl font-bold text-white">
            ${data.total_spent.toFixed(1)}
          </div>
        </div>
        <div className="glass-card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500">Net</span>
            <DollarSign size={18} className="text-info" />
          </div>
          <div className="text-3xl font-bold text-white">
            ${(data.total_earned - data.total_spent).toFixed(1)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Pie Chart */}
        <div className="glass-card">
          <h2 className="text-lg font-semibold text-white mb-4">Distribution</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  dataKey="value"
                  paddingAngle={4}
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#1a1a2e",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "8px",
                    color: "#f1f5f9",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 mt-2">
            {pieData.map((d) => (
              <div key={d.name} className="flex items-center gap-2 text-xs">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: d.color }}
                />
                <span className="text-slate-400">{d.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Transactions */}
        <div className="col-span-2 glass-card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Recent Transactions
          </h2>
          <div className="overflow-y-auto max-h-96">
            {data.transactions.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-8">
                No transactions yet
              </p>
            ) : (
              <div className="space-y-2">
                {data.transactions.slice(0, 20).map((tx) => (
                  <div
                    key={tx.id}
                    className="p-3 rounded-xl bg-white/3 border border-white/5 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                          tx.amount > 0
                            ? "bg-success/20"
                            : "bg-danger/20"
                        }`}
                      >
                        {tx.amount > 0 ? (
                          <ArrowUpRight
                            size={14}
                            className="text-success"
                          />
                        ) : (
                          <ArrowDownRight
                            size={14}
                            className="text-danger"
                          />
                        )}
                      </div>
                      <div>
                        <div className="text-sm text-white">
                          {tx.reason}
                        </div>
                        <div className="text-xs text-slate-500">
                          {tx.agent_id}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`text-sm font-medium ${
                          tx.amount > 0 ? "text-success" : "text-danger"
                        }`}
                      >
                        {tx.amount > 0 ? "+" : ""}
                        {tx.amount.toFixed(2)}
                      </div>
                      <div className="text-[10px] text-slate-600">
                        {new Date(tx.timestamp * 1000).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
