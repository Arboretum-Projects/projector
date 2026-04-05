# ASCII/Unicode Layout Engine — Full Showcase

> 3,598 lines · zero dependencies · 23 element types · 35 built-in examples
> Three-pass layout (measure → layout → render) · JSON in → pixel-perfect art out

All output below is rendered by `projector.py` from JSON structural descriptions. The model describes **what**, the engine guarantees **how**.

---

## 1. Basics — Boxes, Labels, Content

```
┌─ Hello ─┐
│         │
│ World   │
│         │
└─────────┘
```

```
┌─ Note ──────┐
│             │
│ First line  │
│ Second line │
│ Third line  │
│             │
└─────────────┘
```

---

## 2. Row Layout — Side by Side

```
╔═ LAYOUT ════════════════╗
║                         ║
║ ┌─ Left ─┐  ┌─ Right ─┐ ║
║ │        │  │         │ ║
║ │ Side A │  │ Side B  │ ║
║ │        │  │         │ ║
║ └────────┘  └─────────┘ ║
║                         ║
╚═════════════════════════╝
```

---

## 3. Border Hierarchy — double > single > rounded

Three border styles that nest cleanly. Smart merge handles all intersections automatically.

```
╔═ TRUST BOUNDARY ══════╗
║                       ║
║ ┌─ Scope ───────────┐ ║
║ │                   │ ║
║ │ ╭─ Category ────╮ │ ║
║ │ │               │ │ ║
║ │ │ Inner content │ │ ║
║ │ │               │ │ ║
║ │ ╰───────────────╯ │ ║
║ │                   │ ║
║ └───────────────────┘ ║
║                       ║
╚═══════════════════════╝
```

---

## 4. Dashboard — Bars, Separators, Sections

Separators auto-connect to parent box borders with junction characters (╠═╣ for double, ├─┤ for single).

```
╔═ SYSTEM STATUS ═══════════════════╗
║                                   ║
║ ┌─ CPU ─┐  ┌─ MEM ──┐  ┌─ DISK ─┐ ║
║ │       │  │        │  │        │ ║
║ │ 45%   │  │ 8.2 GB │  │ 234 GB │ ║
║ │       │  │        │  │        │ ║
║ └───────┘  └────────┘  └────────┘ ║
╠═ Health ══════════════════════════╣
║ CPU [█████████░░░░░░░░░░░] 45/100 ║
║ MEM [████████████████░░░░] 82/100 ║
╠═ Logs ════════════════════════════╣
║ All systems nominal.              ║
║ No errors detected.               ║
║                                   ║
╚═══════════════════════════════════╝
```

---

## 5. Legend — Formatted Key-Value

```
╭─ SYMBOLS ────────────╮
│                      │
│ ●  Active node       │
│ ○  Inactive node     │
│ ◆  Critical path     │
│ ═  Strong connection │
│                      │
╰──────────────────────╯
```

---

## 6. Semantic Node Types — 8 Bracket Styles

```
╔═ NODE TYPES ═════╗
║                  ║
║ [Server]         ║
║                  ║
║ (Handle Request) ║
║                  ║
║ {Auth Check}     ║
║                  ║
║ <HTTP/443>       ║
║                  ║
║ [[See Also]]     ║
║                  ║
║ ╔═Trust Zone═╗   ║
║                  ║
║ ● API Running    ║
║                  ║
║ ○ Cache Cold     ║
║                  ║
╚══════════════════╝
```

---

## 7. Flow Diagram — Pre-formatted with Grid

```
╔═ DATA FLOW ═══════════════════════════════════╗
║  [Client] ──────► (Gateway) ──────► [Server]  ║
║                      │                  │     ║
║                      │                  │     ║
║                      ▼                  ▼     ║
║                   {Auth?}          [Database] ║
║                    │  │                       ║
║                  ✓ │  │ ✗                     ║
║                    ▼  ▼                       ║
║               [Allow] [Deny]                  ║
╚═══════════════════════════════════════════════╝
```

---

## 8. RPG Status Panel — Composite Element

Status panel auto-builds a box containing bars, inventory grid, and turn log from a single JSON spec.

```
┌─ PLAYER STATUS ────────────────────┐
│                                    │
│ HP  [███████████░░░░] 73/100       │
│ MP  [██████░░░░░░░░░] 20/50        │
│ EXP [███████░░░░░░░░] 450/1000     │
├────────────────────────────────────┤
│ Torch (3)    Key (1)    Potion (5) │
│ Map (1)    Rope (2)                │
├─ Log ──────────────────────────────┤
│ T3: Defeated goblin (+50 EXP)      │
│ T4: Unlocked chest                 │
│ T5: Moved east                     │
│                                    │
└────────────────────────────────────┘
```

---

## 9. Dungeon Minimap — 2D Grid Cells

```
╔═ DUNGEON MAP ═══╗
║                 ║
║ ███░░░███       ║
║ █·····░░█       ║
║ █·█████·█       ║
║ █·····●·█       ║
║ █·███·█·█       ║
║ █·░░░·█·█       ║
║ █·····█·█       ║
║ ███████·█       ║
║ ░░░░░░·░░       ║
╠═ Legend ════════╣
║ ●  You are here ║
║ █  Wall         ║
║ ·  Path         ║
║ ░  Unexplored   ║
║                 ║
╚═════════════════╝
```

---

## 10. Fill Patterns & Gradients

```
┌─ PATTERNS ─────────────────────────────────────────────┐
│                                                        │
│ ┌─ Light ─┐  ┌─ Medium ─┐  ┌─ Dense ─┐  ┌─ Gradient ─┐ │
│ │░░░░░░░░░│  │▒▒▒▒▒▒▒▒▒▒│  │▓▓▓▓▓▓▓▓▓│  │   ░░░▒▒▒▓▓█│ │
│ │░░░░░░░░░│  │▒▒▒▒▒▒▒▒▒▒│  │▓▓▓▓▓▓▓▓▓│  │   ░░░▒▒▒▓▓█│ │
│ │░░░░░░░░░│  │▒▒▒▒▒▒▒▒▒▒│  │▓▓▓▓▓▓▓▓▓│  │   ░░░▒▒▒▓▓█│ │
│ └─────────┘  └──────────┘  └─────────┘  └────────────┘ │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 11. Braille Subpixel Canvas — 2×4 Dots Per Cell ⚠️ TERMINAL ONLY

> **Note:** Braille output requires a monospace terminal for correct rendering. Character widths vary in markdown code blocks. Use only when targeting terminal output.

Each terminal cell holds a 2×4 braille dot matrix (U+2800–U+28FF), giving **160×80 effective resolution** in an 80×20 space. Supports lines, circles, rectangles, polygons, and a built-in 3×4 bitmap font with auto-snap (text renders unified at any y position).

```
╔═ BRAILLE CANVAS ═══════════════════════════════════════════════════════════════════════════════╗
║                                                                                                ║
║ ┌─ Circle ───────────┐  ┌─ Square ───────────┐  ┌─ Lines ────────────┐  ┌─ Text ─────────────┐ ║
║ │                    │  │                    │  │⠑⢄        ⡇       ⡠⠊│  │ ⡗⡇⣟⡁⣇⡀⣇⡀⣏⡇         │ ║
║ │     ⢀⠤⠒⠊⠉⠉⠉⠒⠢⢄     │  │  ⢰⠒⠒⠒⠒⠒⠒⠒⠒⠒⠒⠒⠒⠒⠒⢲  │  │  ⠑⢄      ⡇     ⡠⠊  │  │                    │ ║
║ │   ⢀⠎⠁         ⠉⢆   │  │  ⢸              ⢸  │  │    ⠑⢄    ⡇   ⡠⠊    │  │ ⡧⡇⣏⡇⡯⡃⣇⡀⣏⠆         │ ║
║ │  ⢠⠃             ⢣  │  │  ⢸              ⢸  │  │      ⠑⢄  ⡇ ⡠⠊      │  │                    │ ║
║ │  ⡎              ⠈⡆ │  │  ⢸              ⢸  │  │        ⠑⢄⡧⠊        │  │                    │ ║
║ │  ⡇               ⡇ │  │  ⢸              ⢸  │  │⠉⠉⠉⠉⠉⠉⠉⠉⡩⠋⡟⢍⠉⠉⠉⠉⠉⠉⠉⠉│  └────────────────────┘ ║
║ │  ⠸⡀             ⡸  │  │  ⢸              ⢸  │  │      ⡠⠊  ⡇ ⠑⢄      │                         ║
║ │   ⠑⡄           ⡔⠁  │  │  ⢸              ⢸  │  │    ⡠⠊    ⡇   ⠑⢄    │                         ║
║ │    ⠈⠑⠤⣀⡀   ⣀⡠⠔⠉    │  │  ⢸⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣸  │  │  ⡠⠊      ⡇     ⠑⢄  │                         ║
║ │        ⠈⠉⠉⠉        │  │                    │  │⡠⠊        ⡇       ⠑⢄│                         ║
║ └────────────────────┘  └────────────────────┘  └────────────────────┘                         ║
║                                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## 12. Block Subpixel Canvas — 2×2 Per Cell ✅ Works in Markdown

Half-block characters (▀▄▌▐ + quadrant chars) give **160×40 effective resolution** in 80×20. Good for smooth fills, basic curves, bold shapes.

```
╔═ BLOCK CANVAS ═════════════════════════════════════════════════════════╗
║                                                                        ║
║                                                                        ║
║        ▄▄▄▄▙▄▄▄▖         ▛▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▌        ▄▄▀▀▀▀▀▀▚▄▖      ║
║     ▄████████████▙▖      ▌                   ▌     ▗▞▀          ▝▀▄    ║
║   ▗████████████████▙     ▌                   ▌    ▗▘               ▚   ║
║  ▗██████████████████▙    ▌                   ▌   ▗▘                 ▚  ║
║  ▐███████████████████    ▌                   ▌   ▌                   ▌ ║
║  ▜███████████████████▀▀▀▘▌                   ▌▀▀▀▌                   ▌ ║
║  ▐███████████████████    ▌                   ▌   ▚                  ▗▘ ║
║   ▜█████████████████▘    ▌                   ▌    ▚                ▗▘  ║
║    ▀██████████████▛▘     ▌                   ▌     ▚▖             ▄▘   ║
║      ▀▀████████▛▀▘       ▌                   ▌      ▝▀▄▄      ▗▄▞▀     ║
║            ▘             ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▘          ▀▀▀▀▀▀▘        ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝
```

---

## 13. Complex Nested Architecture

```
╔═ ARCHITECTURE ════════════════════════════════╗
║                                               ║
║ ┌─ Frontend ─┐  ┌─ Backend ─┐  ┌─ Database ─┐ ║
║ │            │  │           │  │            │ ║
║ │ React App  │  │ FastAPI   │  │ PostgreSQL │ ║
║ ├────────────┤  ├───────────┤  ├────────────┤ ║
║ │ Port 3000  │  │ Port 8000 │  │ Port 5432  │ ║
║ │            │  │           │  │            │ ║
║ └────────────┘  └───────────┘  └────────────┘ ║
╠═ Status ══════════════════════════════════════╣
║             All services running              ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

---

## 14. Full RPG Screen — The Catacombs of Xumelor

All auto-sized from JSON — 30-char dungeon map, party stats, inventory, turn log, and legend composed into a single structure.

```
╔═  THE CATACOMBS OF XUMELOR  ═══════════════════════════════════════════╗
║                                                                        ║
║ ┌─  Level 3  ────────────────────┐  ┌─  Party  ──────────────────────┐ ║
║ │                                │  │                                │ ║
║ │ ██████████████████████████████ │  │ Kael HP [██████████░░] 85/100  │ ║
║ │ █░░░░░██····██░░░░░░██·······█ │  │ Sira HP [██████░░░░░░] 42/80   │ ║
║ │ █░░░░░██····██░░░░░░██·······█ │  │ Dorn HP [████████████] 100/100 │ ║
║ │ █░░░░░██····██░░░░░░██···▲···█ │  ├────────────────────────────────┤ ║
║ │ █░░░░░██·······░░░░░██·······█ │  │ Mana [███████░░░░░] 35/60      │ ║
║ │ ██··████····██░░░░░░████···███ │  │                                │ ║
║ │ ██··████····██░░░░░░████···███ │  └────────────────────────────────┘ ║
║ │ ██··██████████████████████··██ │                                     ║
║ │ ██··██░░░░░░░░░░░░░░░░░░██··██ │  ┌─  Inventory  ──────────────────┐ ║
║ │ ██······░░░░░░░░░░░░░░░░██··██ │  │                                │ ║
║ │ ██··██░░░░░░░░░░░░░░░░░░██··██ │  │ Torch (4)        Potion (2)    │ ║
║ │ ██··██████████████████████··██ │  │ Skeleton Key (1) Scroll (3)    │ ║
║ │ ██··████····██········████··██ │  │ Rations (7)      Rope (1)      │ ║
║ │ ██··████····██···●····████··██ │  │                                │ ║
║ │ ██········████········██····██ │  └────────────────────────────────┘ ║
║ │ ██··████····██········████··██ │                                     ║
║ │ ██··████····██████████████··██ │  ┌─  Log  ────────────────────────┐ ║
║ │ ██··████····██░░░░░░░░░░██··██ │  │                                │ ║
║ │ ██··██████··██░░░░░░░░░░██··██ │  │ T13: Sira disarmed trap        │ ║
║ │ ██··········██░░░░░░░░░░██··██ │  │ T14: Found hidden passage      │ ║
║ │ ██··██████████░░░░░░░░░░██··██ │  │ T15: Fought skeleton x2        │ ║
║ │ ██████████████████████████████ │  │ T16: Sira took 38 damage       │ ║
║ │                                │  │ T17: Moved south               │ ║
║ └────────────────────────────────┘  │                                │ ║
║                                     └────────────────────────────────┘ ║
╠═  Legend  ═════════════════════════════════════════════════════════════╣
║ ●  You                                                                 ║
║ ░  Unexplored                                                          ║
║ ▲  Stairs up                                                           ║
║ ◆  Treasure                                                            ║
║ █  Wall                                                                ║
║ †  Enemy                                                               ║
║ ·  Explored                                                            ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝
```

---

## 15. ASCII-Safe Mode — `--ascii` Flag

Same JSON input, same engine. Pass `--ascii` and all Unicode box-drawing is substituted to pure ASCII. Everything else stays identical.

```
+= SAFE =================+
|                        |
| +- Inner ------------+ |
| |                    | |
| | Works!             | |
| |                    | |
| +--------------------+ |
+= Status ===============+
| HP [########..] 75/100 |
|                        |
+========================+
```

---

## 16. Validation — `--validate` Flag

Post-render structural analysis. Read-only — verifies frame completeness, character census, dimensions.

```
┌─ Test ─┐
│        │
│ Hello  │
│        │
└────────┘

--- Validation ---
Valid: True
Stats: 29 chars, 13 unique, 5 lines, max width 10
  Box-drawing: 20  Braille: 0  Block: 0
  Frames: 1 openers, 1 closers
```

---

## Element Type Reference

| # | Type | Description |
|---|------|-------------|
| 1 | `box` / `frame` | Bordered container with title, 5 border styles |
| 2 | `label` | Text with left/center/right alignment |
| 3 | `spacer` | Configurable empty space |
| 4 | `separator` | Horizontal divider, auto-connects to parent borders |
| 5 | `legend` | Formatted key-value pairs |
| 6 | `grid` | Raw pre-formatted line passthrough |
| 7 | `bar` | Progress/status bar with customizable chars |
| 8 | `row` | Horizontal layout with gap and alignment |
| 9 | `stack` | Vertical layout with gap |
| 10 | `line` | Horizontal, vertical, or L-route path |
| 11 | `arrow` | Line with auto-detected arrowhead |
| 12 | `node` | Semantic bracket types: entity, process, decision, io, reference, critical, active, inactive |
| 13 | `connector` | Junction point with optional label |
| 14 | `fill` | Region fill with single char or horizontal gradient |
| 15 | `group` | Nested coordinate space with offset |
| 16 | `transition` | Scene divider (7 styles: hard_cut, fade, dissolve, fast_forward, flashback, dream, temporal_skip) |
| 17 | `inventory` | Multi-column item grid with counts |
| 18 | `turn_log` | Append-only history with show_last |
| 19 | `status_panel` | Composite: auto-builds box with bars + inventory + log |
| 20 | `minimap` | 2D grid cells for maps / heatmaps |
| 21 | `canvas` | Subpixel drawing (braille 2×4 or block 2×2). Draw commands: dot, line, rect, circle, polygon, text |
| 22 | `hexgrid` | Hex territory map with labeled cells |
| 23 | `board` | Freeform absolute positioning — children placed at x, y coordinates |

## Key Features

- **Smart merge** — box-drawing characters auto-intersect via directional decomposition (`─` + `│` = `┼`)
- **Auto-sizing** — every element measures its content; parents expand to fit
- **Border hierarchy** — double > single > rounded, nest cleanly
- **Parent junction** — separators merge with enclosing box borders (╠═╣ / ├─┤)
- **Wide char support** — emoji and CJK render at correct display widths
- **ASCII-safe mode** — `--ascii` flag for pure ASCII output
- **Validation** — `--validate` flag for post-render structural checks
- **Subpixel rendering** — braille (160×80 in 80×20) and block (160×40 in 80×20) modes

---

*Generated by `projector.py` — 3,598 lines, zero dependencies, Python 3.*
