"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Terminal,
  Swords,
  Users,
  Wallet,
  BarChart3,
  Settings,
  Activity,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/terminal", label: "Terminal", icon: Terminal },
  { href: "/arena", label: "Arena", icon: Swords },
  { href: "/agents", label: "Agents", icon: Users },
  { href: "/economy", label: "Economy", icon: Wallet },
  { href: "/benchmarks", label: "Benchmarks", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 glass border-r border-white/8 flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 border-b border-white/8">
        <h1 className="text-xl font-bold text-white tracking-wide">
          <span className="text-accent">HIVE</span> OS
        </h1>
        <p className="text-xs text-slate-500 mt-1">Agent Swarm v2.0</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-accent/20 text-accent border border-accent/30"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Status */}
      <div className="p-4 border-t border-white/8">
        <div className="glass-card p-3">
          <div className="flex items-center gap-2 text-xs">
            <Activity size={14} className="text-success" />
            <span className="text-slate-400">Swarm Status</span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
            <span className="text-sm text-white">Online</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
