/**
 * HIVE OS - API Client
 * Connects to the HIVE FastAPI backend
 */

const HIVE_API = process.env.NEXT_PUBLIC_HIVE_API || "";

export interface HiveStatus {
  name: string;
  version: string;
  status: string;
  thesis: string;
  llm_mode: string;
  active_agents: number;
}

export interface HealthStatus {
  status: string;
  memory_mb: number;
  active_agents: number;
  queue_depth: number;
  swarm_health: number;
  budget_available: number;
  budget_total: number;
}

export interface AgentState {
  id: string;
  type: string;
  status: string;
  emotion: string;
  confidence: number;
  stress: number;
  workload: number;
  current_task?: string;
}

export interface Task {
  id: string;
  description: string;
  mode: string;
  priority: string;
  status: string;
  result?: any;
  tokens_used: number;
  time_taken: number;
  created_at: number;
  completed_at?: number;
}

export interface Economy {
  budget: number;
  total_earned: number;
  total_spent: number;
  transactions: Transaction[];
}

export interface Transaction {
  id: string;
  agent_id: string;
  amount: number;
  reason: string;
  timestamp: number;
}

export interface BenchmarkResult {
  id: string;
  name: string;
  single_agent_score: number;
  society_score: number;
  improvement_pct: number;
  run_timestamp: string;
}

export interface TaskResult {
  task_id: string;
  description: string;
  status: string;
  result?: any;
  time_taken?: number;
  agents_used?: string[];
}

// API functions
export async function getHiveStatus(): Promise<HiveStatus> {
  const res = await fetch(`${HIVE_API}/`);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function getHealth(): Promise<HealthStatus> {
  const res = await fetch(`${HIVE_API}/health`);
  if (!res.ok) throw new Error("Failed to fetch health");
  return res.json();
}

export async function getAgentStates(): Promise<AgentState[]> {
  const res = await fetch(`${HIVE_API}/api/agents/states`);
  if (!res.ok) throw new Error("Failed to fetch agents");
  const data = await res.json();
  return data.agents || [];
}

export async function getTasks(): Promise<Task[]> {
  const res = await fetch(`${HIVE_API}/api/tasks`);
  if (!res.ok) throw new Error("Failed to fetch tasks");
  const data = await res.json();
  return data.tasks || [];
}

export async function submitTask(
  description: string,
  mode: string = "swarm"
): Promise<TaskResult> {
  const res = await fetch(`${HIVE_API}/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: description, mode }),
  });
  if (!res.ok) throw new Error("Failed to submit task");
  return res.json();
}

export async function getEconomy(): Promise<Economy> {
  const res = await fetch(`${HIVE_API}/api/economy`);
  if (!res.ok) throw new Error("Failed to fetch economy");
  return res.json();
}

export async function getAuditLog(): Promise<any[]> {
  const res = await fetch(`${HIVE_API}/api/audit`);
  if (!res.ok) throw new Error("Failed to fetch audit");
  const data = await res.json();
  return data.entries || [];
}

export async function runArena(task: string): Promise<any> {
  const res = await fetch(`${HIVE_API}/api/arena`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
  if (!res.ok) throw new Error("Failed to run arena");
  return res.json();
}

export async function runBenchmark(id: string): Promise<any> {
  const res = await fetch(`${HIVE_API}/api/benchmark/${id}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to run benchmark");
  return res.json();
}

// SSE Event stream
export function subscribeToEvents(
  onEvent: (event: any) => void
): () => void {
  const eventSource = new EventSource(`${HIVE_API}/events`);

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {}
  };

  eventSource.onerror = () => {
    // Reconnect after 3 seconds
    setTimeout(() => {
      eventSource.close();
      subscribeToEvents(onEvent);
    }, 3000);
  };

  return () => eventSource.close();
}
