import { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import { getBridge } from './bridge.js';
import { DashboardState, PermissionRequest } from './types.js';
import { HiveHeader } from './components/HiveHeader.js';
import { StatusLine } from './components/StatusLine.js';
import { BeeSwarm } from './components/BeeSwarm.js';
import { MessageLog } from './components/MessageLog.js';
import { PermissionDialog } from './components/PermissionDialog.js';
import {
  HiveAnimation,
  BeeEntity,
  createBee,
  createIdleBee,
  updateBees,
  IDLE_POSITIONS,
  HIVE_ENTRANCE,
} from './lib/animations.js';

let _msgId = 0;
function nextMsgId() { return `msg-${++_msgId}`; }

function makeIdleBees(): BeeEntity[] {
  return IDLE_POSITIONS.map((pos, i) => createIdleBee(`idle-${i}`, pos, 'header'));
}

export function App() {
  const { exit } = useApp();
  const bridge = getBridge();

  const [connected, setConnected] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [beeFrame, setBeeFrame] = useState(0);
  const [scrollOffset, setScrollOffset] = useState(0);

  const [beeAnim, setBeeAnim] = useState<HiveAnimation>({
    honeyFrame: 0,
    bees: makeIdleBees(),
  });

  const [dashboard, setDashboard] = useState<DashboardState>({
    status: 'idle',
    task: '',
    mode: 'auto',
    elapsed: '0.0s',
    budget: { spent: 0, total: 1000 },
    agents: [],
    subtasks: { done: 0, total: 0 },
  });

  const [toolCalls, setToolCalls] = useState<Array<{ tool: string; args: Record<string, unknown> }>>([]);
  const [pendingPermission, setPendingPermission] = useState<PermissionRequest | null>(null);
  const [messages, setMessages] = useState<Array<{ id: string; role: string; content: string }>>([]);
  const [processing, setProcessing] = useState(false);
  const [streamText, setStreamText] = useState('');

  const processingRef = useRef(processing);
  processingRef.current = processing;
  const inputRef = useRef(input);
  inputRef.current = input;
  const historyRef = useRef(history);
  historyRef.current = history;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const taskStartTime = useRef<number>(0);
  const elapsedInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  // Slow idle animation — only when NOT processing to avoid terminal wipe
  useEffect(() => {
    if (processing) return;
    const id = setInterval(() => {
      setBeeFrame(f => (f + 1) % 4);
      setBeeAnim(prev => updateBees(prev));
    }, 500);
    return () => clearInterval(id);
  }, [processing]);

  useEffect(() => {
    const readyTimeout = setTimeout(() => {
      if (!connected) {
        setConnectError('Python backend did not respond. Is DASHSCOPE_API_KEY set?');
      }
    }, 10000);

    const cleanupMsg = bridge.onMessage((msg) => {
      switch (msg.type) {
        case 'ready':
          clearTimeout(readyTimeout);
          setConnected(true);
          setConnectError(null);
          break;
        case 'stream':
          setStreamText(prev => prev + (msg.content as string));
          break;
        case 'tool_call':
          setToolCalls(prev => [...prev, {
            tool: msg.tool as string,
            args: (msg.args as Record<string, unknown>) || {},
          }]);
          break;
        case 'permission_request':
          setPendingPermission(msg as unknown as PermissionRequest);
          break;
        case 'status':
          setDashboard(prev => ({ ...prev, status: msg.status as string }));
          break;
        case 'mode':
          setDashboard(prev => ({ ...prev, mode: msg.mode as string }));
          break;
        case 'elapsed':
          setDashboard(prev => ({ ...prev, elapsed: msg.elapsed as string }));
          break;
        case 'subtask_progress':
          setDashboard(prev => ({
            ...prev,
            subtasks: { done: msg.done as number, total: msg.total as number },
          }));
          break;
        case 'agent_spawn': {
          const agentId = msg.agent_id as string;
          const kind = (msg.kind as string) || 'general';
          setDashboard(prev => ({
            ...prev,
            agents: [...prev.agents, { id: agentId, kind, status: 'spawning', task: '' }],
          }));
          const newBee = createBee(agentId, agentId, kind);
          setBeeAnim(prev => ({ ...prev, bees: [...prev.bees, newBee] }));
          let ticks = 0;
          const anim = setInterval(() => {
            setBeeAnim(prev => updateBees(prev));
            setBeeFrame(f => (f + 1) % 4);
            ticks++;
            if (ticks > 12) clearInterval(anim);
          }, 125);
          break;
        }
        case 'agent_work': {
          const agentId = msg.agent_id as string;
          setDashboard(prev => ({
            ...prev,
            agents: prev.agents.map(a =>
              a.id === agentId ? { ...a, status: 'working', task: (msg.task as string) || '' } : a
            ),
          }));
          setBeeAnim(prev => ({
            ...prev,
            bees: prev.bees.map(b =>
              b.agentId === agentId && b.state !== 'dying' && b.state !== 'dead'
                ? { ...b, state: 'flying_out' as const } : b
            ),
          }));
          let ticks = 0;
          const anim = setInterval(() => {
            setBeeAnim(prev => updateBees(prev));
            setBeeFrame(f => (f + 1) % 4);
            ticks++;
            if (ticks > 20) clearInterval(anim);
          }, 125);
          break;
        }
        case 'agent_done': {
          const agentId = msg.agent_id as string;
          setDashboard(prev => ({
            ...prev,
            agents: prev.agents.map(a => a.id === agentId ? { ...a, status: 'done' } : a),
          }));
          setBeeAnim(prev => ({
            ...prev,
            bees: prev.bees.map(b =>
              b.agentId === agentId && b.state !== 'dying' && b.state !== 'dead'
                ? { ...b, state: 'returning' as const, targetX: HIVE_ENTRANCE.x, targetY: HIVE_ENTRANCE.y } : b
            ),
          }));
          let ticks = 0;
          const anim = setInterval(() => {
            setBeeAnim(prev => updateBees(prev));
            setBeeFrame(f => (f + 1) % 4);
            ticks++;
            if (ticks > 20) {
              clearInterval(anim);
              setBeeAnim(prev => ({ ...prev, bees: prev.bees.filter(b => b.agentId !== agentId) }));
            }
          }, 125);
          break;
        }
        case 'agent_fail': {
          const agentId = msg.agent_id as string;
          setDashboard(prev => ({
            ...prev,
            agents: prev.agents.map(a => a.id === agentId ? { ...a, status: 'failed' } : a),
          }));
          setBeeAnim(prev => ({
            ...prev,
            bees: prev.bees.map(b =>
              b.agentId === agentId && b.state !== 'dying' && b.state !== 'dead'
                ? { ...b, state: 'dying' as const, dieFrame: 0, poofFrame: 0 } : b
            ),
          }));
          let ticks = 0;
          const anim = setInterval(() => {
            setBeeAnim(prev => updateBees(prev));
            setBeeFrame(f => (f + 1) % 4);
            ticks++;
            if (ticks > 6) {
              clearInterval(anim);
              setBeeAnim(prev => ({ ...prev, bees: prev.bees.filter(b => b.agentId !== agentId) }));
            }
          }, 125);
          break;
        }
        case 'spend':
          setDashboard(prev => ({
            ...prev,
            budget: { ...prev.budget, spent: prev.budget.spent + (msg.amount as number) },
          }));
          break;
        case 'earn':
          setDashboard(prev => ({
            ...prev,
            budget: { ...prev.budget, spent: Math.max(0, prev.budget.spent - (msg.amount as number)) },
          }));
          break;
        case 'response':
          setMessages(prev => [...prev, { id: nextMsgId(), role: 'assistant', content: msg.content as string }]);
          setProcessing(false);
          setToolCalls([]);
          setStreamText('');
          setDashboard(prev => ({ ...prev, mode: 'auto' }));
          if (elapsedInterval.current) { clearInterval(elapsedInterval.current); elapsedInterval.current = null; }
          setTimeout(() => {
            setDashboard(prev => ({
              ...prev,
              agents: prev.agents.filter(a => a.status === 'working' || a.status === 'spawning'),
              status: 'idle',
            }));
          }, 2000);
          break;
        case 'error':
          setMessages(prev => [...prev, { id: nextMsgId(), role: 'error', content: msg.message as string }]);
          setProcessing(false);
          setStreamText('');
          setDashboard(prev => ({ ...prev, mode: 'auto' }));
          if (elapsedInterval.current) { clearInterval(elapsedInterval.current); elapsedInterval.current = null; }
          break;
      }
    });

    const cleanupErr = bridge.onError((err) => {
      if (!err.message.startsWith('[python stderr]')) {
        setMessages(prev => [...prev, { id: nextMsgId(), role: 'error', content: err.message }]);
        setConnected(false);
      }
    });

    bridge.start();

    return () => {
      clearTimeout(readyTimeout);
      cleanupMsg();
      cleanupErr();
      bridge.removeAllListeners();
      bridge.stop();
      if (elapsedInterval.current) { clearInterval(elapsedInterval.current); }
    };
  }, []);

  const handleSubmit = useCallback((text: string) => {
    if (!text.trim() || processingRef.current) return;
    setMessages(prev => [...prev, { id: nextMsgId(), role: 'user', content: text }]);
    setToolCalls([]);
    setStreamText('');
    setProcessing(true);
    setScrollOffset(0);
    setDashboard(prev => ({ ...prev, task: text, status: 'routing' }));
    taskStartTime.current = Date.now();
    elapsedInterval.current = setInterval(() => {
      const elapsed = ((Date.now() - taskStartTime.current) / 1000).toFixed(1);
      setDashboard(prev => ({ ...prev, elapsed: `${elapsed}s` }));
    }, 500);
    bridge.send({ type: 'user_message', content: text });
  }, []);

  const handleCancel = useCallback(() => {
    if (processingRef.current) {
      setProcessing(false);
      setToolCalls([]);
      setStreamText('');
      if (elapsedInterval.current) { clearInterval(elapsedInterval.current); elapsedInterval.current = null; }
      setDashboard(prev => ({ ...prev, status: 'idle', elapsed: '0.0s' }));
    }
  }, []);

  const handlePermission = useCallback((requestId: string, decision: string) => {
    bridge.send({ type: 'permission_response', request_id: requestId, decision });
    setPendingPermission(null);
  }, []);

  useInput((keyInput, key) => {
    if (key.escape || (key.ctrl && keyInput === 'c')) {
      bridge.stop();
      exit();
      return;
    }
    if (key.ctrl && keyInput === 'x') { handleCancel(); return; }
    if (key.return) {
      const val = inputRef.current;
      if (val.trim() && !processingRef.current) {
        handleSubmit(val);
        setHistory(prev => [...prev, val]);
        setHistoryIdx(-1);
        setInput('');
      }
      return;
    }
    if (key.upArrow) {
      setHistoryIdx(prev => {
        const h = historyRef.current;
        const next = prev + 1;
        if (next < h.length) { setInput(h[h.length - 1 - next]); return next; }
        return prev;
      });
      return;
    }
    if (key.downArrow) {
      setHistoryIdx(prev => {
        const h = historyRef.current;
        const next = prev - 1;
        if (next >= 0) { setInput(h[h.length - 1 - next]); return next; }
        setInput('');
        return -1;
      });
      return;
    }
    if (key.ctrl && keyInput === 'u') {
      setScrollOffset(prev => Math.min(messagesRef.current.length, prev + 3));
      return;
    }
    if (key.ctrl && keyInput === 'd') {
      setScrollOffset(prev => Math.max(0, prev - 3));
      return;
    }
    if (key.backspace || key.delete) { setInput(prev => prev.slice(0, -1)); return; }
    if (keyInput && !key.ctrl && !key.meta && keyInput.length > 1) {
      setInput(prev => prev + keyInput);
      return;
    }
    if (keyInput && !key.ctrl && !key.meta && keyInput.length === 1) {
      setInput(prev => prev + keyInput);
    }
  });

  if (connectError) {
    return (
      <Box flexDirection="column" alignItems="center" paddingY={2}>
        <HiveHeader beeFrame={beeFrame} honeyFrame={beeAnim.honeyFrame} bees={beeAnim.bees} />
        <Box marginTop={1} borderStyle="round" borderColor="red" paddingX={2}>
          <Text color="red" bold> {connectError} </Text>
        </Box>
        <Box marginTop={1}>
          <Text color="dim">Check .env for DASHSCOPE_API_KEY</Text>
        </Box>
        <Text color="dim">Ctrl+C to exit</Text>
      </Box>
    );
  }

  if (!connected) {
    return (
      <Box flexDirection="column" alignItems="center" paddingY={2}>
        <HiveHeader beeFrame={beeFrame} honeyFrame={beeAnim.honeyFrame} bees={beeAnim.bees} />
        <Box marginTop={1}>
          <Text color="yellow">Starting backend...</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <HiveHeader beeFrame={beeFrame} honeyFrame={beeAnim.honeyFrame} bees={beeAnim.bees} />
      <StatusLine
        status={dashboard.status}
        mode={dashboard.mode}
        elapsed={dashboard.elapsed}
        budgetSpent={dashboard.budget.spent}
        budgetTotal={dashboard.budget.total}
        beeFrame={beeFrame}
      />

      <Box flexDirection="row">
        <Box flexDirection="column" flexGrow={7} borderStyle="round" borderColor="gray" paddingX={1}>
          <Box flexDirection="column" height={12}>
            <MessageLog
              messages={messages.slice(-scrollOffset - 8, messages.length - scrollOffset)}
              processing={processing}
              streamText={streamText}
              toolCalls={toolCalls}
            />
          </Box>
          {scrollOffset > 0 && (
            <Text color="dim">  ^ Ctrl+D scroll up ({scrollOffset} msgs above) ^</Text>
          )}
          {pendingPermission && (
            <PermissionDialog
              tool={pendingPermission.tool}
              target={pendingPermission.target}
              tier={pendingPermission.tier}
              requestId={pendingPermission.request_id}
              onDecision={handlePermission}
            />
          )}
        </Box>

        <Box flexDirection="column" flexGrow={3} borderStyle="round" borderColor="yellow" paddingX={1}>
          <BeeSwarm
            agents={dashboard.agents}
            beeFrame={beeFrame}
            honeyFrame={beeAnim.honeyFrame}
          />
        </Box>
      </Box>

      <Box marginTop={1}>
        <Text color="yellow" bold> honey@hive </Text>
        <Text color="dim">{'>'} </Text>
        <Text color="white">{input}</Text>
        {!processing && <Text color="yellow">_</Text>}
        {processing && <Text color="yellow"> ... Ctrl+X cancel</Text>}
      </Box>
    </Box>
  );
}
