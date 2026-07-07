import { RGB, BLACK } from './pixelbuffer.js';

const _ = BLACK;

// === COLOR PALETTE ===
const YELLOW: RGB     = { r: 255, g: 215, b: 0 };
const DARK_YELLOW: RGB = { r: 218, g: 165, b: 32 };
const BROWN: RGB      = { r: 139, g: 69,  b: 19 };
const DARK_BROWN: RGB = { r: 61,  g: 43,  b: 31 };
const HONEY: RGB      = { r: 255, g: 193, b: 7 };
const HONEY_LIGHT: RGB = { r: 255, g: 224, b: 102 };
const WING: RGB       = { r: 220, g: 240, b: 255 };
const WING_DARK: RGB  = { r: 180, g: 210, b: 240 };
const BLACK_S: RGB    = { r: 26,  g: 26,  b: 26 };
const GREEN: RGB      = { r: 34,  g: 139, b: 34 };
const GREEN_DARK: RGB = { r: 0,   g: 100, b: 0 };
const FLOWER_W: RGB   = { r: 255, g: 250, b: 250 };
const POOF: RGB       = { r: 200, g: 200, b: 200 };
const POOF_LIGHT: RGB = { r: 230, g: 230, b: 230 };
const PAYLOAD: RGB    = { r: 255, g: 165, b: 0 };
const RED: RGB        = { r: 220, g: 50,  b: 50 };

// === TINY BEE SPRITES (5 wide x 4 tall) ===
// Frame 0: wings up
const BEE_0: RGB[][] = [
  [_,_,WING,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,BLACK_S,_,_],
];
// Frame 1: wings side
const BEE_1: RGB[][] = [
  [WING,_,_,_,WING],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,BLACK_S,_,_],
];
// Frame 2: wings down
const BEE_2: RGB[][] = [
  [_,_,_,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [WING,BLACK_S,BLACK_S,BLACK_S,WING],
];
// Frame 3: wings mid (same as frame 1)
const BEE_3: RGB[][] = BEE_1;

export const BEE_FRAMES: RGB[][][] = [BEE_0, BEE_1, BEE_2, BEE_3];

// === TINY BEE CARRYING PAYLOAD (5 wide x 5 tall) ===
const BEE_CARRY_0: RGB[][] = [
  [_,_,WING,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,BLACK_S,_,_],
  [_,_,PAYLOAD,_,_],
];
const BEE_CARRY_1: RGB[][] = [
  [WING,_,_,_,WING],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,BLACK_S,_,_],
  [_,_,PAYLOAD,_,_],
];
const BEE_CARRY_2: RGB[][] = [
  [_,_,_,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [WING,BLACK_S,BLACK_S,BLACK_S,WING],
  [_,_,PAYLOAD,_,_],
];

export const BEE_CARRY_FRAMES: RGB[][][] = [BEE_CARRY_0, BEE_CARRY_1, BEE_CARRY_2, BEE_CARRY_1];

// === TINY BEE DIE FRAMES (5 wide x 4 tall) ===
const BEE_DIE_0: RGB[][] = BEE_0;
const BEE_DIE_1: RGB[][] = [
  [_,_,BLACK_S,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,YELLOW,YELLOW,_],
  [_,WING,_,_,WING],
];
const BEE_DIE_2: RGB[][] = [
  [_,_,BLACK_S,_,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,YELLOW,YELLOW,YELLOW,_],
  [_,_,WING,WING,_],
];
const BEE_DIE_3: RGB[][] = [
  [_,_,_,_,_],
  [_,YELLOW,YELLOW,_,_],
  [_,_,YELLOW,_,_],
  [_,_,_,_,_],
];

export const BEE_DIE_FRAMES: RGB[][][] = [BEE_DIE_0, BEE_DIE_1, BEE_DIE_2, BEE_DIE_3];

// === POOF EFFECT (4 wide x 4 tall) ===
const POOF_0: RGB[][] = [
  [_,RED,RED,_],
  [RED,POOF_LIGHT,POOF_LIGHT,RED],
  [RED,POOF_LIGHT,POOF_LIGHT,RED],
  [_,RED,RED,_],
];
const POOF_1: RGB[][] = [
  [RED,_,_,RED],
  [_,POOF,POOF,_],
  [_,POOF,POOF,_],
  [RED,_,_,RED],
];
const POOF_2: RGB[][] = [
  [RED,_,_,RED],
  [_,POOF,_,POOF],
  [POOF,_,POOF,_],
  [RED,_,_,RED],
];
const POOF_3: RGB[][] = [
  [_,POOF_LIGHT,_,POOF_LIGHT],
  [POOF_LIGHT,_,_,POOF_LIGHT],
  [_,POOF_LIGHT,POOF_LIGHT,_],
  [POOF_LIGHT,_,_,POOF_LIGHT],
];

export const POOF_FRAMES: RGB[][][] = [POOF_0, POOF_1, POOF_2, POOF_3];

// === BEEHIVE (28 wide x 24 tall) ===
export const HIVE: RGB[][] = (() => {
  const h = 24;
  const w = 28;
  const grid: RGB[][] = Array.from({ length: h }, () => Array.from({ length: w }, () => _));

  for (let x = 10; x < 18; x++) {
    grid[0][x] = BROWN;
  }
  grid[1][12] = BROWN;
  grid[1][13] = BROWN;
  grid[1][14] = BROWN;
  grid[1][15] = BROWN;
  grid[2][13] = BROWN;
  grid[2][14] = BROWN;

  const stripePattern: [RGB, number][] = [
    [YELLOW, 4],
    [DARK_YELLOW, 5],
    [YELLOW, 6],
    [DARK_YELLOW, 7],
    [YELLOW, 8],
    [DARK_YELLOW, 9],
    [YELLOW, 10],
    [DARK_YELLOW, 10],
    [YELLOW, 10],
    [DARK_YELLOW, 10],
    [YELLOW, 10],
    [DARK_YELLOW, 9],
    [YELLOW, 8],
    [DARK_YELLOW, 7],
    [YELLOW, 6],
    [DARK_YELLOW, 5],
    [YELLOW, 4],
  ];

  let row = 3;
  for (const [color, width] of stripePattern) {
    const startX = Math.floor((w - width) / 2);
    for (let x = startX; x < startX + width; x++) {
      grid[row][x] = color;
    }
    row++;
  }

  const entranceStart = Math.floor((w - 4) / 2);
  for (let dy = 0; dy < 3; dy++) {
    for (let dx = 0; dx < 4; dx++) {
      grid[10 + dy][entranceStart + dx] = DARK_BROWN;
    }
  }

  for (let x = 9; x < 19; x++) {
    grid[9][x] = BROWN;
    grid[13][x] = BROWN;
  }

  return grid;
})();

// === HONEY DRIP OVERLAY (28 wide x 6 tall, 4 frames) ===
const HONEY_X = [13, 14, 15];

function makeHoneyFrame(dripLength: number): RGB[][] {
  const grid: RGB[][] = Array.from({ length: 6 }, () => Array.from({ length: 28 }, () => _));
  for (const x of HONEY_X) {
    for (let dy = 0; dy < dripLength; dy++) {
      if (dy === 0) grid[dy][x] = HONEY_LIGHT;
      else if (dy === dripLength - 1) grid[dy][x] = HONEY;
      else grid[dy][x] = HONEY;
    }
  }
  return grid;
}

export const HONEY_DRIP: RGB[][][] = [
  makeHoneyFrame(1),
  makeHoneyFrame(2),
  makeHoneyFrame(4),
  makeHoneyFrame(6),
];

// === LEAF CLUSTER (14 wide x 8 tall) ===
export const LEAVES: RGB[][] = (() => {
  const grid: RGB[][] = Array.from({ length: 8 }, () => Array.from({ length: 14 }, () => _));
  const leafShape = [
    [0,0,0,1,1,0,0,0,0,1,1,0,0,0],
    [0,0,1,1,1,1,0,0,1,1,1,1,0,0],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [0,1,1,1,1,1,1,1,1,1,1,1,1,0],
    [0,0,1,1,1,1,1,1,1,1,1,1,0,0],
    [0,0,0,0,1,1,1,1,1,1,0,0,0,0],
  ];
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 14; x++) {
      if (leafShape[y][x]) {
        grid[y][x] = (x + y) % 3 === 0 ? GREEN_DARK : GREEN;
      }
    }
  }
  const flowers = [[2,1],[9,1],[5,3],[11,3],[1,5],[12,5]];
  for (const [fx, fy] of flowers) {
    grid[fy][fx] = FLOWER_W;
    if (fx + 1 < 14) grid[fy][fx + 1] = FLOWER_W;
    if (fy + 1 < 8) grid[fy + 1][fx] = YELLOW;
    if (fy + 1 < 8 && fx + 1 < 14) grid[fy + 1][fx + 1] = YELLOW;
  }
  return grid;
})();

// === SMALL FLOWER (3 wide x 3 tall) ===
export const FLOWER_SPRITE: RGB[][] = [
  [_,FLOWER_W,_],
  [FLOWER_W,YELLOW,FLOWER_W],
  [_,FLOWER_W,_],
];
