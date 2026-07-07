import { useMemo } from 'react';
import { Box, Text } from 'ink';
import { PixelBuffer, RGB, BLACK } from '../lib/pixelbuffer.js';
import { BEE_FRAMES, BEE_CARRY_FRAMES, BEE_DIE_FRAMES, POOF_FRAMES } from '../lib/sprites.js';
import { SWARM_HIVE_ENTRANCE, SWARM_IDLE_POSITIONS, SWARM_WORK_TARGETS } from '../lib/animations.js';
import { AgentState } from '../types.js';
import { PixelCanvas } from './PixelCanvas.js';

const YELLOW: RGB = { r: 255, g: 215, b: 0 };
const DARK_YELLOW: RGB = { r: 218, g: 165, b: 32 };
const BROWN: RGB = { r: 139, g: 69, b: 19 };
const DARK_BROWN: RGB = { r: 61, g: 43, b: 31 };
const HONEY: RGB = { r: 255, g: 193, b: 7 };

// Small beehive (12 wide x 10 tall) for the side panel
function drawSmallHive(buf: PixelBuffer, ox: number, oy: number) {
  const rows: [RGB, number][] = [
    [BROWN, 3],
    [BROWN, 4],
    [YELLOW, 5],
    [DARK_YELLOW, 6],
    [YELLOW, 7],
    [DARK_YELLOW, 7],
    [YELLOW, 7],
    [DARK_YELLOW, 6],
    [YELLOW, 5],
  ];

  let y = oy;
  for (const [color, width] of rows) {
    const startX = ox + Math.floor((12 - width) / 2);
    for (let x = startX; x < startX + width; x++) {
      buf.setPixel(x, y, color);
    }
    y++;
  }

  // Entrance
  const ex = ox + 4;
  buf.setPixel(ex, oy + 5, DARK_BROWN);
  buf.setPixel(ex + 1, oy + 5, DARK_BROWN);
  buf.setPixel(ex, oy + 6, DARK_BROWN);
  buf.setPixel(ex + 1, oy + 6, DARK_BROWN);

  // Honey drip
  buf.setPixel(ox + 5, oy + 9, HONEY);
  buf.setPixel(ox + 6, oy + 9, HONEY);
  buf.setPixel(ox + 5, oy + 10, HONEY);
}

// Derive bee positions for the side panel from agent states
interface SwarmBee {
  x: number;
  y: number;
  status: 'idle' | 'spawning' | 'working' | 'returning' | 'dying';
  kind: string;
}

function deriveSwarmBees(agents: AgentState[]): SwarmBee[] {
  const bees: SwarmBee[] = [];

  // 3 idle bees always at hive (wings flapping)
  for (const pos of SWARM_IDLE_POSITIONS) {
    bees.push({ x: pos.x, y: pos.y, status: 'idle', kind: 'idle' });
  }

  // Agent bees at their work positions
  for (const agent of agents) {
    const target = SWARM_WORK_TARGETS[agent.kind] || SWARM_WORK_TARGETS.general;
    switch (agent.status) {
      case 'spawning':
        bees.push({ x: SWARM_HIVE_ENTRANCE.x, y: SWARM_HIVE_ENTRANCE.y, status: 'spawning', kind: agent.kind });
        break;
      case 'working':
        bees.push({ x: target.x, y: target.y, status: 'working', kind: agent.kind });
        break;
      case 'done':
        bees.push({ x: SWARM_HIVE_ENTRANCE.x, y: SWARM_HIVE_ENTRANCE.y, status: 'returning', kind: agent.kind });
        break;
      case 'failed':
        bees.push({ x: SWARM_HIVE_ENTRANCE.x, y: SWARM_HIVE_ENTRANCE.y, status: 'dying', kind: agent.kind });
        break;
    }
  }

  return bees;
}

interface BeeSwarmProps {
  beeFrame: number;
  honeyFrame: number;
  agents: AgentState[];
}

export function BeeSwarm({ beeFrame, honeyFrame, agents }: BeeSwarmProps) {
  // Memoize counts and buffer together — only recompute when beeFrame or agents change
  const { buffer, workingCount, doneCount, failedCount } = useMemo(() => {
    const buf = new PixelBuffer(20, 16);
    const wingFrameIdx = beeFrame % 4;

    // Draw small hive
    drawSmallHive(buf, 4, 1);

    // Draw bees (already tiny 5x4 sprites)
    const swarmBees = deriveSwarmBees(agents);
    for (const bee of swarmBees) {
      let sprite: RGB[][];
      if (bee.status === 'dying') {
        sprite = BEE_DIE_FRAMES[Math.min(beeFrame % 4, 3)];
      } else if (bee.status === 'working' || bee.status === 'spawning') {
        sprite = BEE_CARRY_FRAMES[wingFrameIdx];
      } else {
        sprite = BEE_FRAMES[wingFrameIdx];
      }

      // Draw tiny sprite directly (no scaling needed)
      for (let dy = 0; dy < sprite.length; dy++) {
        for (let dx = 0; dx < sprite[dy].length; dx++) {
          const px = sprite[dy][dx];
          if (px.r !== 0 || px.g !== 0 || px.b !== 0) {
            buf.setPixel(bee.x + dx, bee.y + dy, px);
          }
        }
      }

      // Poof effect for dying bees
      if (bee.status === 'dying') {
        const poofIdx = beeFrame % 4;
        const poof = POOF_FRAMES[poofIdx];
        for (let dy = 0; dy < poof.length; dy++) {
          for (let dx = 0; dx < poof[dy].length; dx++) {
            const px = poof[dy][dx];
            if (px.r !== 0 || px.g !== 0 || px.b !== 0) {
              buf.setPixel(bee.x + dx - 1, bee.y + dy - 1, px);
            }
          }
        }
      }
    }

    return {
      buffer: buf,
      workingCount: agents.filter(a => a.status === 'working' || a.status === 'spawning').length,
      doneCount: agents.filter(a => a.status === 'done').length,
      failedCount: agents.filter(a => a.status === 'failed').length,
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beeFrame, agents]);

  return (
    <Box flexDirection="column">
      <Text color="yellow" bold>THE HIVE</Text>
      <PixelCanvas buffer={buffer} />
      <Text> </Text>
      <Text color="yellow">active:{workingCount} </Text>
      <Text color="green">done:{doneCount} </Text>
      <Text color="red">fail:{failedCount}</Text>
    </Box>
  );
}
