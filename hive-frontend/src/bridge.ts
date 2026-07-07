import { spawn, ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import { PythonMessage, NodeMessage } from './types.js';

export type MessageHandler = (msg: PythonMessage) => void;
export type ErrorHandler = (err: Error) => void;

export class PythonBridge {
  private process: ChildProcess | null = null;
  private handlers: MessageHandler[] = [];
  private errorHandlers: ErrorHandler[] = [];
  private buffer = '';
  private _running = false;
  private _starting = false;

  start(pythonPath: string = 'python', args: string[] = []) {
    if (this._running || this._starting) return;
    this._starting = true;

    if (this.process) {
      try { this.process.kill(); } catch {}
      this.process = null;
    }

    const hiveRoot = new URL('../../', import.meta.url).pathname
      .replace(/^\/([A-Z]:)/, '$1')
      .replace(/\//g, '\\');

    const venvPython = hiveRoot + '\\.venv\\Scripts\\python.exe';
    const actualPython = fs.existsSync(venvPython) ? venvPython : pythonPath;

    this.process = spawn(actualPython, ['-m', 'hive.cli', '--server', ...args], {
      cwd: hiveRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    this._running = true;
    this._starting = false;

    this.process.stdout?.on('data', (data: Buffer) => {
      this.buffer += data.toString('utf-8');
      this.processBuffer();
    });

    this.process.stderr?.on('data', (data: Buffer) => {
      const text = data.toString('utf-8').trim();
      if (text) {
        for (const handler of this.errorHandlers) {
          handler(new Error(`[python stderr] ${text}`));
        }
      }
    });

    this.process.on('error', (err) => {
      this._running = false;
      this._starting = false;
      for (const handler of this.errorHandlers) {
        handler(err);
      }
    });

    this.process.on('exit', (code) => {
      this._running = false;
      this._starting = false;
      if (code !== 0 && code !== null) {
        for (const handler of this.errorHandlers) {
          handler(new Error(`Python process exited with code ${code}`));
        }
      }
    });
  }

  private processBuffer() {
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      try {
        const msg = JSON.parse(trimmed) as PythonMessage;
        for (const handler of this.handlers) {
          handler(msg);
        }
      } catch {}
    }
  }

  send(msg: NodeMessage) {
    if (!this._running || !this.process?.stdin?.writable) return;
    try {
      this.process.stdin.write(JSON.stringify(msg) + '\n');
    } catch {
      this._running = false;
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler);
    };
  }

  onError(handler: ErrorHandler): () => void {
    this.errorHandlers.push(handler);
    return () => {
      this.errorHandlers = this.errorHandlers.filter(h => h !== handler);
    };
  }

  stop() {
    if (this.process) {
      try {
        this.process.stdin?.write(JSON.stringify({ type: 'quit' }) + '\n');
      } catch {}
      const proc = this.process;
      setTimeout(() => {
        try { proc.kill(); } catch {}
      }, 500);
      this.process = null;
      this._running = false;
      this._starting = false;
    }
  }

  removeAllListeners() {
    this.handlers = [];
    this.errorHandlers = [];
  }

  get running() {
    return this._running && this.process !== null && !this.process.killed;
  }
}

let bridge: PythonBridge | null = null;

export function getBridge(): PythonBridge {
  if (!bridge) {
    bridge = new PythonBridge();
  }
  return bridge;
}
