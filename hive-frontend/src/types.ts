export interface AgentState {
  id: string;
  kind: string;
  status: 'spawning' | 'working' | 'done' | 'failed';
  task: string;
}

export interface DashboardState {
  status: string;
  task: string;
  mode: string;
  elapsed: string;
  budget: { spent: number; total: number };
  agents: AgentState[];
  subtasks: { done: number; total: number };
}

export interface PythonMessage {
  type: string;
  [key: string]: unknown;
}

export interface NodeMessage {
  type: string;
  [key: string]: unknown;
}

export interface PermissionRequest {
  type: 'permission_request';
  tool: string;
  target: string;
  tier: string;
  request_id: string;
}
