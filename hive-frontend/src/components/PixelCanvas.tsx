import { Box, Text } from 'ink';
import { PixelBuffer, BLACK } from '../lib/pixelbuffer.js';
import { ReactNode } from 'react';

interface PixelCanvasProps {
  buffer: PixelBuffer;
}

export function PixelCanvas({ buffer }: PixelCanvasProps) {
  const rows: ReactNode[] = [];

  for (let y = 0; y < buffer.height; y += 2) {
    let allBlack = true;
    const cells: ReactNode[] = [];

    for (let x = 0; x < buffer.width; x++) {
      const top = buffer.getPixel(x, y);
      const bottom = y + 1 < buffer.height
        ? buffer.getPixel(x, y + 1)
        : BLACK;

      if (top.r !== 0 || top.g !== 0 || top.b !== 0 ||
          bottom.r !== 0 || bottom.g !== 0 || bottom.b !== 0) {
        allBlack = false;
      }

      if (top.r === 0 && top.g === 0 && top.b === 0 &&
          bottom.r === 0 && bottom.g === 0 && bottom.b === 0) {
        cells.push(<Text key={x}>{' '}</Text>);
      } else {
        cells.push(
          <Text
            key={x}
            color={`rgb(${top.r},${top.g},${top.b})`}
            backgroundColor={`rgb(${bottom.r},${bottom.g},${bottom.b})`}
          >{'\u2580'}</Text>
        );
      }
    }

    if (allBlack) {
      rows.push(<Box key={y} flexDirection="row"><Text>{' '.repeat(buffer.width)}</Text></Box>);
    } else {
      rows.push(<Box key={y} flexDirection="row">{cells}</Box>);
    }
  }

  return <Box flexDirection="column">{rows}</Box>;
}
