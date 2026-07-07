import { useMemo } from 'react';
import { Box, Text } from 'ink';
import { PixelBuffer, RGB, BLACK as _ } from '../lib/pixelbuffer.js';
import { BEE_FRAMES, BEE_CARRY_FRAMES, BEE_DIE_FRAMES, HONEY_DRIP, POOF_FRAMES } from '../lib/sprites.js';
import { BeeEntity } from '../lib/animations.js';
import { PixelCanvas } from './PixelCanvas.js';

const YELLOW: RGB = { r: 255, g: 215, b: 0 };
const DARK_YELLOW: RGB = { r: 218, g: 165, b: 32 };
const BROWN: RGB = { r: 139, g: 69, b: 19 };
const DARK_BROWN: RGB = { r: 61, g: 43, b: 31 };

// Block-letter HIVE (each letter 5 wide x 3 tall, compact)
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

// Compact beehive (20 wide x 10 tall)
function drawCompactHive(buf: PixelBuffer, ox: number, oy: number) {
  const rows: [RGB, number][] = [
    [BROWN, 4],
    [YELLOW, 5],
    [DARK_YELLOW, 6],
    [YELLOW, 7],
    [DARK_YELLOW, 8],
    [YELLOW, 9],
    [DARK_YELLOW, 8],
    [YELLOW, 7],
    [DARK_YELLOW, 6],
    [YELLOW, 5],
  ];

  let y = oy;
  for (const [color, width] of rows) {
    const startX = ox + Math.floor((20 - width) / 2);
    for (let x = startX; x < startX + width; x++) {
      buf.setPixel(x, y, color);
    }
    y++;
  }

  // Entrance (dark brown 3x2)
  const ex = ox + 8;
  buf.setPixel(ex, oy + 5, DARK_BROWN);
  buf.setPixel(ex + 1, oy + 5, DARK_BROWN);
  buf.setPixel(ex + 2, oy + 5, DARK_BROWN);
  buf.setPixel(ex, oy + 6, DARK_BROWN);
  buf.setPixel(ex + 1, oy + 6, DARK_BROWN);
  buf.setPixel(ex + 2, oy + 6, DARK_BROWN);
}

interface HiveHeaderProps {
  beeFrame: number;
  honeyFrame: number;
  bees: BeeEntity[];
}

export function HiveHeader({ beeFrame, honeyFrame, bees }: HiveHeaderProps) {
  const buffer = useMemo(() => {
    // 42 wide x 14 tall = 7 terminal rows
    const buf = new PixelBuffer(42, 14);

    // Layer 1: Block-letter HIVE text (centered)
    let textX = 11;
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

    // Layer 2: Compact beehive (centered below text)
    drawCompactHive(buf, 11, 4);

    // Layer 3: Honey drip
    const hFrame = Math.floor(honeyFrame / 4) % HONEY_DRIP.length;
    // Only draw drip columns that exist in the small buffer
    const drip = HONEY_DRIP[hFrame];
    for (let dx = 0; dx < drip[0].length; dx++) {
      for (let dy = 0; dy < drip.length; dy++) {
        const px = drip[dy][dx];
        if (px.r !== 0 || px.g !== 0 || px.b !== 0) {
          buf.setPixel(11 + dx, 12 + dy, px);
        }
      }
    }

    // Layer 4: Animated bees
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
