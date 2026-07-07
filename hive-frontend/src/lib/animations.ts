export type BeeState =
  | 'spawning'
  | 'flying_out'
  | 'working'
  | 'returning'
  | 'roaming'
  | 'dying'
  | 'dead';

export interface BeeEntity {
  id: string;
  agentId: string;
  state: BeeState;
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  wingFrame: number;
  dieFrame: number;
  poofFrame: number;
  spawnTimer: number;
  roamTimer: number;
  roamTargetX: number;
  roamTargetY: number;
}

export interface HiveAnimation {
  honeyFrame: number;
  bees: BeeEntity[];
}

// ============================================================
// HiveHeader coordinates (42x28 canvas — big hive with leaves)
// ============================================================

// Big hive at (7, 4), 28 wide x 24 tall, entrance at relative x=12-15, y=10-12
// Absolute entrance center: 7+13=20, 4+11=15
export const HIVE_ENTRANCE = { x: 20, y: 15 };

export const WORK_TARGETS: Record<string, { x: number; y: number }> = {
  code:     { x: 38, y: 5 },
  research: { x: 38, y: 9 },
  general:  { x: 38, y: 13 },
  security: { x: 38, y: 17 },
  forge:    { x: 38, y: 7 },
  cleanup:  { x: 38, y: 15 },
  judge:    { x: 38, y: 11 },
  safety:   { x: 38, y: 13 },
};

// Idle bees roam near the hive entrance (outside the hive body)
export const IDLE_POSITIONS = [
  { x: 17, y: 13 },
  { x: 23, y: 13 },
  { x: 20, y: 12 },
];

// ============================================================
// BeeSwarm coordinates (20x16 canvas)
// ============================================================

export const SWARM_HIVE_ENTRANCE = { x: 9, y: 13 };

export const SWARM_IDLE_POSITIONS = [
  { x: 5, y: 11 },
  { x: 13, y: 11 },
  { x: 9, y: 10 },
];

export const SWARM_WORK_TARGETS: Record<string, { x: number; y: number }> = {
  code:     { x: 17, y: 1 },
  research: { x: 17, y: 3 },
  general:  { x: 17, y: 6 },
  security: { x: 17, y: 9 },
  forge:    { x: 17, y: 2 },
  cleanup:  { x: 17, y: 8 },
  judge:    { x: 17, y: 4 },
  safety:   { x: 17, y: 7 },
};

// ============================================================

const FLY_SPEED = 2;
const ROAM_SPEED = 1;
const SPAWN_DELAY = 8;
const ROAM_PAUSE = 12;

function randomRoamTarget(scale: 'header' | 'swarm'): { x: number; y: number } {
  if (scale === 'swarm') {
    return {
      x: 2 + Math.floor(Math.random() * 16),
      y: 8 + Math.floor(Math.random() * 6),
    };
  }
  // Header: roam around the hive area (x: 5-38, y: 6-26)
  return {
    x: 5 + Math.floor(Math.random() * 33),
    y: 6 + Math.floor(Math.random() * 20),
  };
}

export function createBee(
  id: string,
  agentId: string,
  workType: string,
  scale: 'header' | 'swarm' = 'header',
): BeeEntity {
  const targets = scale === 'swarm' ? SWARM_WORK_TARGETS : WORK_TARGETS;
  const entrance = scale === 'swarm' ? SWARM_HIVE_ENTRANCE : HIVE_ENTRANCE;
  const target = targets[workType] || targets.general;
  const roamTarget = randomRoamTarget(scale);
  return {
    id,
    agentId,
    state: 'spawning',
    x: entrance.x,
    y: entrance.y,
    targetX: target.x,
    targetY: target.y,
    wingFrame: 0,
    dieFrame: 0,
    poofFrame: 0,
    spawnTimer: 0,
    roamTimer: 0,
    roamTargetX: roamTarget.x,
    roamTargetY: roamTarget.y,
  };
}

export function createIdleBee(
  id: string,
  pos: { x: number; y: number },
  scale: 'header' | 'swarm' = 'header',
): BeeEntity {
  const roamTarget = randomRoamTarget(scale);
  return {
    id,
    agentId: id,
    state: 'roaming',
    x: pos.x,
    y: pos.y,
    targetX: pos.x,
    targetY: pos.y,
    wingFrame: Math.floor(Math.random() * 4),
    dieFrame: 0,
    poofFrame: 0,
    spawnTimer: 0,
    roamTimer: Math.floor(Math.random() * ROAM_PAUSE),
    roamTargetX: roamTarget.x,
    roamTargetY: roamTarget.y,
  };
}

export function updateBee(bee: BeeEntity, scale: 'header' | 'swarm' = 'header'): BeeEntity {
  switch (bee.state) {
    case 'spawning': {
      const next = (bee.wingFrame + 1) % 4;
      const timer = bee.spawnTimer + 1;
      if (timer >= SPAWN_DELAY) {
        return { ...bee, state: 'flying_out', wingFrame: next, spawnTimer: timer };
      }
      return { ...bee, wingFrame: next, spawnTimer: timer };
    }

    case 'flying_out': {
      const dx = bee.targetX - bee.x;
      const dy = bee.targetY - bee.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < FLY_SPEED * 2) {
        return { ...bee, state: 'working', wingFrame: (bee.wingFrame + 1) % 4 };
      }
      const nx = dx / dist;
      const ny = dy / dist;
      return {
        ...bee,
        x: Math.round(bee.x + nx * FLY_SPEED),
        y: Math.round(bee.y + ny * FLY_SPEED),
        wingFrame: (bee.wingFrame + 1) % 4,
      };
    }

    case 'working':
      return { ...bee, wingFrame: (bee.wingFrame + 1) % 4 };

    case 'returning': {
      const dx = bee.targetX - bee.x;
      const dy = bee.targetY - bee.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < FLY_SPEED * 2) {
        return { ...bee, state: 'dead', wingFrame: (bee.wingFrame + 1) % 4 };
      }
      const nx = dx / dist;
      const ny = dy / dist;
      return {
        ...bee,
        x: Math.round(bee.x + nx * FLY_SPEED),
        y: Math.round(bee.y + ny * FLY_SPEED),
        wingFrame: (bee.wingFrame + 1) % 4,
      };
    }

    case 'roaming': {
      const dx = bee.roamTargetX - bee.x;
      const dy = bee.roamTargetY - bee.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < ROAM_SPEED * 2 || bee.roamTimer <= 0) {
        const newTarget = randomRoamTarget(scale);
        return {
          ...bee,
          roamTargetX: newTarget.x,
          roamTargetY: newTarget.y,
          roamTimer: ROAM_PAUSE,
          wingFrame: (bee.wingFrame + 1) % 4,
        };
      }

      const nx = dx / dist;
      const ny = dy / dist;
      return {
        ...bee,
        x: Math.round(bee.x + nx * ROAM_SPEED),
        y: Math.round(bee.y + ny * ROAM_SPEED),
        roamTimer: bee.roamTimer - 1,
        wingFrame: (bee.wingFrame + 1) % 4,
      };
    }

    case 'dying': {
      const nextDieFrame = Math.min(bee.dieFrame + 1, 3);
      const nextPoof = Math.min(bee.poofFrame + 1, 3);
      return {
        ...bee,
        dieFrame: nextDieFrame,
        poofFrame: nextPoof,
        y: bee.y + 1,
        x: bee.x + (bee.dieFrame % 2 === 0 ? 1 : -1),
        state: nextDieFrame >= 3 ? 'dead' : 'dying',
      };
    }

    case 'dead':
      return bee;
  }
}

export function updateBees(anim: HiveAnimation, scale: 'header' | 'swarm' = 'header'): HiveAnimation {
  return {
    honeyFrame: (anim.honeyFrame + 1) % 16,
    bees: anim.bees.map(b => updateBee(b, scale)),
  };
}
