export interface RGB {
  r: number;
  g: number;
  b: number;
}

export const BLACK: RGB = { r: 0, g: 0, b: 0 };
export const TRANSPARENT: RGB = { r: 0, g: 0, b: 0 };

export class PixelBuffer {
  width: number;
  height: number;
  data: RGB[][];

  constructor(width: number, height: number, fill: RGB = BLACK) {
    this.width = width;
    this.height = height;
    this.data = Array.from({ length: height }, () =>
      Array.from({ length: width }, () => ({ ...fill }))
    );
  }

  setPixel(x: number, y: number, color: RGB): void {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return;
    this.data[y][x] = { ...color };
  }

  getPixel(x: number, y: number): RGB {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return BLACK;
    return { ...this.data[y][x] };
  }

  fill(color: RGB): void {
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        this.data[y][x] = { ...color };
      }
    }
  }

  drawSprite(x: number, y: number, sprite: RGB[][], transparent: RGB = BLACK): void {
    for (let sy = 0; sy < sprite.length; sy++) {
      for (let sx = 0; sx < sprite[sy].length; sx++) {
        const pixel = sprite[sy][sx];
        const isTrans = pixel.r === transparent.r && pixel.g === transparent.g && pixel.b === transparent.b;
        if (!isTrans) {
          this.setPixel(x + sx, y + sy, pixel);
        }
      }
    }
  }

  drawSpriteAlpha(x: number, y: number, sprite: RGB[][], alpha: number, transparent: RGB = BLACK): void {
    for (let sy = 0; sy < sprite.length; sy++) {
      for (let sx = 0; sx < sprite[sy].length; sx++) {
        const pixel = sprite[sy][sx];
        const isTrans = pixel.r === transparent.r && pixel.g === transparent.g && pixel.b === transparent.b;
        if (!isTrans) {
          const existing = this.getPixel(x + sx, y + sy);
          const r = Math.round(existing.r + (pixel.r - existing.r) * alpha);
          const g = Math.round(existing.g + (pixel.g - existing.g) * alpha);
          const b = Math.round(existing.b + (pixel.b - existing.b) * alpha);
          this.setPixel(x + sx, y + sy, { r, g, b });
        }
      }
    }
  }

  drawRect(x: number, y: number, w: number, h: number, color: RGB): void {
    for (let dy = 0; dy < h; dy++) {
      for (let dx = 0; dx < w; dx++) {
        this.setPixel(x + dx, y + dy, color);
      }
    }
  }

  clear(): void {
    this.fill(BLACK);
  }

  clone(): PixelBuffer {
    const buf = new PixelBuffer(this.width, this.height);
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        buf.data[y][x] = { ...this.data[y][x] };
      }
    }
    return buf;
  }
}
