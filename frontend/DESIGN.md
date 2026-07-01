---
version: 1.0.0
name: HIVE OS — Design System
description: An Operating System Where AI Agents Form Temporary Societies. Gothic terminal meets SaaS dashboard meets retro gaming. Blasphemous dark atmosphere + Sentry data density + Y2K neon + Hermes CLI.
platforms: [web]
tags: [hive, autonomous-agents, dark-gothic, retro, terminal, y2k, blasphemous]

# HIVE OS — Design Token Specification

## 1. Overview

HIVE OS is a dark, atmospheric web interface for an autonomous multi-agent swarm system. The visual identity merges four aesthetic streams:
- **Blasphemous gothic** — Spanish Catholic iconography, candlelit blood-red atmosphere, medieval dread
- **Sentry dark SaaS** — data-dense developer dashboards, purple-tinted surfaces, frosted glass
- **Hermes/Claude Code terminal** — monospace data, green-on-black terminal vibes, command execution
- **Y2K retro gaming** — CRT scanlines, neon pulse, glitch effects, pixel nostalgia, holographic borders

The result: an interface that feels like a medieval monastery running a 1990s hacker terminal from the future.

## 2. Color Palette

### Backgrounds (Layered Depth)
- **Void** `#050508` — deepest background, page base
- **Abyss** `#0a0a10` — primary surface background
- **Chapel** `#12101c` — elevated surfaces, cards
- **Choir** `#1a1830` — high-elevation, modals, dropdowns
- **Pews** `#241f38` — subtle dividers, borders

### Brand Colors
- **Blood** `#8b0000` — primary accent, Blasphemous red, danger/alert
- **Crimson** `#c41e3a` — hover on blood, important actions
- **Vermillion** `#d44a3a` — error states, warnings
- **Gold Ochre** `#c8a84b` — secondary accent, sacred gold, holy highlight
- **Tarnished Gold** `#8b7355` — muted gold, secondary text on dark

### Terminal / Neon
- **Terminal Green** `#00ff41` — primary terminal text, success, online status
- **Cyber Lime** `#39ff14` — bright highlights, live data
- **Neon Cyan** `#00f5d4` — info, links, interactive elements
- **Neon Purple** `#9d4edd` — Sentry-purple, primary brand
- **Hot Magenta** `#f72585` — focus states, special accents
- **Electric Blue** `#00b4d8` — secondary interactive, data highlights

### Text
- **White** `#ffffff` — primary text, headings
- **Parchment** `#e8e0d0` — body text, warm white
- **Dust** `#a09890` — secondary text, muted
- **Ash** `#6b6570` — tertiary text, placeholders
- **Terminal White** `#e0ffe0` — terminal text tint

### Semantic
- **Success** `#00ff41` (Terminal Green)
- **Warning** `#ffcc00` (Amber)
- **Error** `#c41e3a` (Crimson)
- **Info** `#00b4d8` (Electric Blue)
- **Online** `#39ff14` (Cyber Lime)
- **Offline** `#6b6570` (Ash)

### Surfaces & Borders
- **Border Dark** `#1e1b2e` — subtle structural lines
- **Border Mid** `#2d2845` — standard borders
- **Border Bright** `#4a4470` — emphasis borders
- **Surface Glow** `rgba(157, 78, 221, 0.08)` — purple ambient
- **Blood Glow** `rgba(139, 0, 0, 0.15)` — red ambient
- **Gold Glow** `rgba(200, 168, 75, 0.12)` — gold ambient

## 3. Typography

### Font Families
- **Display/Gothic**: `Cinzel Decorative` (Google Fonts) — for HIVE logo and major headings
- **Display Sans**: `Cinzel` — section headings, labels
- **Body**: `Rubik` — all body text, UI labels
- **Monospace/Terminal**: `JetBrains Mono` — all data, code, terminal, metrics
- **Pixel**: `Press Start 2P` — retro gaming accents, Y2K badges

### Type Scale
| Role | Font | Size | Weight | Line Height | Letter Spacing | Usage |
|------|------|------|--------|-------------|----------------|-------|
| Logo/Display | Cinzel Decorative | 48px | 700 | 1.1 | 0.05em | HIVE wordmark |
| Hero H1 | Cinzel | 56px | 700 | 1.1 | 0.03em | Hero headlines |
| Section H2 | Cinzel | 36px | 600 | 1.2 | 0.02em | Major sections |
| Section H3 | Rubik | 24px | 600 | 1.25 | normal | Card titles |
| Body | Rubik | 15px | 400 | 1.6 | normal | Paragraphs |
| UI Label | Rubik | 13px | 500 | 1.3 | 0.02em | Buttons, labels |
| Mono Data | JetBrains Mono | 13px | 400 | 1.5 | normal | Metrics, codes |
| Terminal | JetBrains Mono | 14px | 400 | 1.6 | normal | Terminal output |
| Pixel Accent | Press Start 2P | 10px | 400 | 1.8 | normal | Badges, Y2K elements |

## 4. Spacing System
- Base unit: 8px
- Scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128px
- Container max-width: 1400px
- Content max-width: 1100px
- Card padding: 20px / 24px
- Section gap: 64px–96px

## 5. Borders & Radius
- Border width: 1px (standard), 2px (emphasis)
- Border style: solid
- Border colors: use Border Dark/Mid/Bright palette
- Radius scale: 2px (inputs), 4px (chips), 8px (cards), 12px (panels), 16px (modals), 24px (hero elements)
- Pixel-art corners: `clip-path: polygon(0 0, 8px 0, 8px 2px, 10px 2px, ...)` for Y2K effects

## 6. Shadows & Elevation

| Level | Shadow | Use |
|-------|--------|-----|
| None | none | Base backgrounds |
| Surface | `0 2px 8px rgba(0,0,0,0.4)` | Cards on dark surfaces |
| Raised | `0 4px 16px rgba(0,0,0,0.6), 0 0 24px rgba(157,78,221,0.08)` | Modals, popups |
| Ambient | `0 0 40px rgba(157,78,221,0.15), 0 0 80px rgba(139,0,0,0.08)` | Hero glows |
| Blood | `0 0 30px rgba(196,30,58,0.3)` | Error highlights |
| Gold | `0 0 20px rgba(200,168,75,0.2)` | Success/premium |

## 7. Motion & Animation

### CRT / Scanline Effect
```css
.scanlines::after {
  content: '';
  position: fixed;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    rgba(0,0,0,0.08) 0px,
    rgba(0,0,0,0.08) 1px,
    transparent 1px,
    transparent 3px
  );
  pointer-events: none;
  z-index: 9999;
}
```

### Neon Pulse
```css
@keyframes neon-pulse {
  0%, 100% { text-shadow: 0 0 10px currentColor, 0 0 20px currentColor; }
  50% { text-shadow: 0 0 5px currentColor, 0 0 10px currentColor; }
}
```

### Glitch Effect
```css
@keyframes glitch {
  0%, 100% { clip-path: inset(0 0 0 0); transform: translate(0); }
  20% { clip-path: inset(20% 0 60% 0); transform: translate(-2px, 2px); }
  40% { clip-path: inset(60% 0 10% 0); transform: translate(2px, -2px); }
  60% { clip-path: inset(40% 0 30% 0); transform: translate(-1px, 1px); }
  80% { clip-path: inset(80% 0 5% 0); transform: translate(1px, -1px); }
}
```

### CRT Flicker
```css
@keyframes crt-flicker {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.97; }
  52% { opacity: 1; }
  54% { opacity: 0.95; }
  56% { opacity: 1; }
}
```

### Typing Cursor
```css
@keyframes blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}
```

## 8. Component Specifications

### Primary Button (Gothic CTA)
- Background: `#8b0000` (Blood)
- Border: `1px solid #c41e3a`
- Text: `#ffffff`, uppercase, Rubik 13px weight 600, letter-spacing 0.08em
- Padding: 12px 24px
- Radius: 2px (sharp, gothic)
- Shadow: `0 0 20px rgba(139,0,0,0.3)` (blood glow on hover)
- Hover: background `#c41e3a`, shadow expands

### Secondary Button (Terminal)
- Background: `#0a0a10`
- Border: `1px solid #00ff41`
- Text: `#00ff41`, JetBrains Mono 13px
- Hover: background `rgba(0,255,65,0.08)`, text glow increases

### Glass Panel
- Background: `rgba(26,24,48,0.7)`
- Border: `1px solid rgba(157,78,221,0.3)`
- Backdrop-filter: `blur(20px) saturate(150%)`
- Radius: 12px
- Shadow: `0 8px 32px rgba(0,0,0,0.4)`

### Agent Card
- Background: `#12101c`
- Border: `1px solid #1e1b2e`
- Hover border: `#4a4470`
- Radius: 8px
- Contains: agent name (Cinzel), status badge, emotion indicator, key metric

### Status Badge (Retro Pixel Style)
- Pixel font (Press Start 2P)
- Color-coded: green=online, red=error, gold=warning, ash=offline
- Background: `rgba(0,0,0,0.4)`
- Padding: 4px 8px, radius: 2px
- Box shadow: `inset 0 0 0 1px rgba(255,255,255,0.05)`

### Metric Counter
- JetBrains Mono for numbers
- Large size (32-48px) for hero metrics
- Animates on value change (CSS counter or JS)
- Label below in small Rubik

### Terminal Line
- JetBrains Mono 14px
- Prompt character: `>` in blood red
- Output: terminal green
- Error: crimson
- Comment: gold/ochre
- Timestamp: ash, smaller

### Navigation
- Fixed top bar, `#0a0a10` background, `backdrop-filter: blur(12px)`
- Cinzel for logo
- Rubik 13px for nav items
- Active: neon purple underline glow
- Y2K pixel-art favicon

## 9. Page Structure

### index.html — Landing
- Hero: full-viewport, animated hex-grid hive visualization, particle field, HIVE logo, tagline
- Features section: 4-column cards showing key capabilities
- How it works: numbered steps with terminal animation
- Architecture diagram: animated SVG of the agent hierarchy
- Live demo section: "Try it now" embedded terminal
- CTA: Deploy / Get Started buttons
- Footer: links, version, status

### terminal.html — Command Terminal
- Full-screen terminal emulator aesthetic
- Command input with `>` prompt
- Output panel with scrollback
- Auto-refresh for task status
- Command history (up/down arrows)
- Tab completion suggestions
- Status bar: budget, active agents, swarm health

### dashboard.html — Live Hive Status
- Top: key metrics row (agents, tasks, budget, health)
- Agent state grid: each agent card with emotion indicator
- Real-time event log (SSE)
- Budget gauge
- GPU utilization bar (if available)

### arena.html — Arena
- Task input
- Side-by-side panels: single agent vs society
- Live scoring as tasks complete
- Winner reveal with glitch animation
- Leaderboard/history

### agents.html — Agent Registry
- List of all agents with status
- Create agent button
- Kill agent button
- Agent detail modal: state, history, cost

### economy.html — Economy
- Budget display
- Transaction list
- Per-agent spend chart
- Cost breakdown by agent type

### tasks.html — Task Queue
- Pending / In Progress / Completed tabs
- Task detail view
- Submit new task form

### benchmarks.html — Benchmarks
- 6 benchmark cards
- Run button for each
- Results history

## 10. Technical Implementation

### Auto-Refresh Strategy
- All pages poll their respective API endpoints every 3-5 seconds
- SSE connection on `/events` for real-time dashboard updates
- Exponential backoff on API errors

### API Endpoints Used
- `GET /api/metrics` — swarm metrics
- `GET /api/agents/states` — all agent states
- `GET /api/economy` — budget + transactions
- `GET /api/tasks` — task list
- `GET /api/audit` — audit log
- `GET /events` — SSE stream
- `POST /api/tasks/sync` — submit task
- `POST /api/arena` — run arena match
- `POST /api/benchmark/{id}` — run benchmark
- `GET /api/hive` — hive status

### Performance
- Single CSS file shared across all pages (design system)
- Single JS file (app.js) with page-specific init
- CSS animations preferred over JS where possible
- Passive event listeners for scroll/touch
- IntersectionObserver for lazy animations

## 11. Do's and Don'ts

### Do
- Use `Cinzel Decorative` ONLY for the HIVE wordmark — nowhere else
- Apply CRT scanline overlay on ALL pages uniformly
- Use blood red (`#8b0000`) sparingly — only for CTAs and errors
- Use `JetBrains Mono` for all data, metrics, codes, timestamps
- Apply neon pulse on key status indicators (online, active)
- Use frosted glass panels for layered information
- Show real data from backend on all displays

### Don't
- Use pure black (`#000000`) backgrounds — use Void (`#050508`)
- Use more than 2 accent colors in one component
- Put Cinzel Decorative on anything except the main logo
- Use animations for decoration only — every animation communicates state
- Put sensitive data (API keys, tokens) in frontend
- Forget the CRT scanline overlay — it unifies the aesthetic