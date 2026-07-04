"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Copy, Check } from "lucide-react";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  time: number;
  mode?: string;
}

export default function TerminalPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "system",
      content:
        'HIVE OS Terminal v2.0 — Type a task to delegate to the swarm.\nUse /mode swarm|single|arena to switch modes.\nExample: "Build a REST API for user authentication"',
      time: Date.now(),
    },
  ]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("swarm");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg: Message = {
      role: "user",
      content: input,
      time: Date.now(),
      mode,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Check for mode commands
    if (input.startsWith("/mode ")) {
      const newMode = input.split(" ")[1]?.trim();
      if (["swarm", "single", "arena"].includes(newMode)) {
        setMode(newMode);
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: `Mode switched to: ${newMode}`,
            time: Date.now(),
          },
        ]);
        setLoading(false);
        return;
      }
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: input, mode }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.result
            ? typeof data.result === "string"
              ? data.result
              : JSON.stringify(data.result, null, 2)
            : `Task submitted: ${data.task_id}\nStatus: ${data.status}\nAgents: ${data.agents_used?.join(", ") || "auto"}`,
          time: Date.now(),
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err.message}. Is the HIVE backend running?`,
          time: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white">Terminal</h1>
          <p className="text-slate-500 mt-1">Interact with the HIVE swarm</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Mode:</span>
          <span className="px-3 py-1 rounded-full text-xs bg-accent/20 text-accent font-medium">
            {mode}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 glass-card overflow-y-auto p-4 font-mono text-sm">
        {messages.map((msg, i) => (
          <div key={i} className="mb-4 group">
            <div className="flex items-start gap-3">
              <span
                className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                  msg.role === "user"
                    ? "bg-accent"
                    : msg.role === "system"
                    ? "bg-warning"
                    : "bg-success"
                }`}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-xs font-medium ${
                      msg.role === "user"
                        ? "text-accent"
                        : msg.role === "system"
                        ? "text-warning"
                        : "text-success"
                    }`}
                  >
                    {msg.role === "user"
                      ? "You"
                      : msg.role === "system"
                      ? "System"
                      : "HIVE"}
                  </span>
                  {msg.mode && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-slate-500">
                      {msg.mode}
                    </span>
                  )}
                  <span className="text-[10px] text-slate-600">
                    {new Date(msg.time).toLocaleTimeString()}
                  </span>
                  {msg.role === "assistant" && (
                    <button
                      onClick={() =>
                        copyToClipboard(msg.content, `msg-${i}`)
                      }
                      className="opacity-0 group-hover:opacity-100 transition-opacity ml-auto"
                    >
                      {copied === `msg-${i}` ? (
                        <Check size={12} className="text-success" />
                      ) : (
                        <Copy size={12} className="text-slate-500" />
                      )}
                    </button>
                  )}
                </div>
                <pre className="whitespace-pre-wrap text-slate-300 break-words">
                  {msg.content}
                </pre>
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-accent">
            <Loader2 size={14} className="animate-spin" />
            <span className="text-sm">Processing...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="mt-4 flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter a task for the swarm..."
          className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-accent/50 font-mono text-sm"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-6 py-3 rounded-xl bg-accent hover:bg-accent-hover text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <Send size={16} />
          Send
        </button>
      </form>
    </div>
  );
}
