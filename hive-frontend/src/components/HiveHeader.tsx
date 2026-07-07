import { useMemo, useRef } from 'react';
import { Box } from 'ink';
import { PixelBuffer, RGB, BLACK as _ } from '../lib/pixelbuffer.js';
import { BEE_FRAMES, BEE_CARRY_FRAMES, BEE_DIE_FRAMES, POOF_FRAMES, HIVE, LEAVES, HONEY_DRIP } from '../lib/sprites.js';
import { BeeEntity } from '../lib/animations.js';
import { PixelCanvas } from './PixelCanvas.js';

const YELLOW: RGB = { r: 255, g: 215, b: 0 };

// Block-letter HIVE (each letter 5 wide x 3 tall)
const HIVE_TEXT: RGB[][][] = [
  // H
  [
    [YELLOW,YELLOW,_,YELLOW,YELLOW],
    [YELLOW,YELLOW,YELLOW,YELLOW,YELLOW],
    [YELLOW,YELLOW,_,YELLOW,YELLOW],
  ],
  // I
  [
    [YELLOW,YELLOW,YELLOW,YELLOW,YELLOW],
    [_,_,YELLOW,_,_],
    [YELLOW,YELLOW,YELLOW,YELLOW,YELLOW],
  ],
  // V
  [
    [YELLOW,YELLOW,_,YELLOW,YELLOW],
    [_,YELLOW,YELLOW,YELLOW,_],
    [_,_,YELLOW,_,_],
  ],
  // E
  [
    [YELLOW,YELLOW,YELLOW,YELLOW,YELLOW],
    [YELLOW,YELLOW,YELLOW,_,_],
    [YELLOW,YELLOW,YELLOW,YELLOW,YELLOW],
  ],
];

// Hive positioned at (7, 4), leaves at (14, 0), honey drip at (7, 14)
const HIVE_OX = 7;
const HIVE_OY = 4;
const LEAVES_OX = 14;
const LEAVES_OY = 0;
const HONEY_OX = 7;
const HONEY_OY = 14;

interface HiveHeaderProps {
  beeFrame: number;
  honeyFrame: number;
  bees: BeeEntity[];
}

// Pre-render the static background (leaves + hive + HIVE text) once
let staticBgCache: PixelBuffer | null = null;

function getStaticBackground(): PixelBuffer {
  if (staticBgCache) return staticBgCache;
  const buf = new PixelBuffer(42, 28);
  buf.drawSprite(LEAVES_OX, LEAVES_OY, LEAVES);
  let textX = 9;
  for (const letter of HIVE_TEXT) {
    for (let ly = 0; ly < letter.length; ly++) {
      for (let lx = 0; lx < letter[ly].length; lx++) {
        if (letter[ly][lx].r !== 0 || letter[ly][lx].g !== 0 || letter[ly][lx].b !== 0) {
          buf.setPixel(textX + lx, ly, letter[ly][lx]);
        }
      }
    }
    textX += 6;
  }
  buf.drawSprite(HIVE_OX, HIVE_OY, HIVE);
  staticBgCache = buf;
  return buf;
}

export function HiveHeader({ beeFrame, honeyFrame, bees }: HiveHeaderProps) {
  const buffer = useMemo(() => {
    // Clone static background (cheap — just copies pixel array)
    const buf = getStaticBackground().clone();

    // Layer 4: Honey drip overlay (animated)
    const dripFrame = HONEY_DRIP[honeyFrame % HONEY_DRIP.length];
    buf.drawSprite(HONEY_OX, HONEY_OY, dripFrame);

    // Layer 5: Animated bees
    const wingFrameIdx = beeFrame % 4;
    for (const bee of bees) {
      if (bee.state === 'dead') continue;

      let sprite: RGB[][];
      if (bee.state === 'dying') {
        sprite = BEE_DIE_FRAMES[Math.min(bee.dieFrame, 3)];
      } else if (bee.state === 'working' || bee.state === 'flying_out') {
        sprite = BEE_CARRY_FRAMES[wingFrameIdx];
      } else {
        sprite = BEE_FRAMES[wingFrameIdx];
      }

      buf.drawSprite(Math.round(bee.x), Math.round(bee.y), sprite);

      // Poof effect for dying bees
      if (bee.state === 'dying' && bee.poofFrame > 0) {
        const poofIdx = Math.min(bee.poofFrame, 3);
        buf.drawSprite(
          Math.round(bee.x) - 1,
          Math.round(bee.y) - 1,
          POOF_FRAMES[poofIdx]
        );
      }
    }

    return buf;
  }, [beeFrame, honeyFrame, bees]);

  return (
    <Box flexDirection="column" alignItems="center">
      <PixelCanvas buffer={buffer} />
    </Box>
  );
}
