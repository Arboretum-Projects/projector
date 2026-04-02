# The Projector — Composition Guide

*How to think with the Projector. How to compose structure. How to make art.*

---

## The Core Idea

**You are the intelligence. The Projector is the execution.**

You decide WHAT to draw — the structure, content, meaning, aesthetics.
The Projector guarantees HOW it renders — pixel-perfect borders, alignment, compositing.

Language models conceptualize ASCII art layouts well — structure, content, aesthetics.
The Projector handles the part that requires mechanical precision: right-side border
alignment, character counting, and nested structures maintaining their bounds.

**Your job:** Compose a JSON spec that expresses your intent.
**Projector's job:** Turn that spec into perfect ASCII/Unicode art.

---

## Quick Start

### CLI Usage

```bash
# Render from file
python3 projector.py spec.json

# Render from stdin
echo '{"type":"box","title":"Hello","content":"World"}' | python3 projector.py

# Save to file
python3 projector.py spec.json > output.txt

# Show all built-in examples (30 total)
python3 projector.py --examples

# Show JSON + render for one example
python3 projector.py --example dashboard

# ASCII-safe mode (Unicode → ASCII substitution)
python3 projector.py --ascii < spec.json

# Post-render structural validation
python3 projector.py --validate < spec.json

# Browse the Unicode character palette
python3 projector.py --palette              # all categories
python3 projector.py --palette celestial     # one category
```

### Minimal Spec

```json
{"type": "box", "title": "Hello", "content": "World"}
```

Renders:
```
┌─ Hello ─┐
│         │
│ World   │
│         │
└─────────┘
```

### Two-Column Layout

```json
{
    "type": "box", "title": "STATUS", "style": "double",
    "children": [
        {
            "type": "row", "gap": 2,
            "children": [
                {"type": "box", "title": "CPU", "content": "45%"},
                {"type": "box", "title": "MEM", "content": "8.2 GB"}
            ]
        }
    ]
}
```

---

## The Element Vocabulary

23 element types in 6 categories (with `frame` as a `box` alias). Every piece of ASCII art is composed from these primitives.

### Containers — Hold Children, Provide Structure

#### `box` — The Fundamental Container
Bordered container with optional title. The workhorse of every layout.

```json
{
    "type": "box",
    "title": "TITLE",          // optional — appears in top border
    "style": "single",         // single | double | rounded | heavy | dashed
    "content": "text here",    // string or list of strings (for leaf boxes)
    "pad": 1,                  // padding inside border (default 1)
    "w": 40,                   // explicit width (otherwise auto-sized)
    "h": 10,                   // explicit height (otherwise auto-sized)
    "maxW": 60,                // max width cap
    "gap": 0,                  // vertical gap between children
    "align": "left",           // text alignment: left | center | right
    "children": [...]          // nested elements (replaces content)
}
```

**Key insight:** A box can either have `content` (text) OR `children` (nested elements), not both. Children take precedence.

**Style hierarchy for nesting:** double → single → rounded (outer to inner).

#### `row` — Horizontal Layout
Arranges children side by side.

```json
{
    "type": "row",
    "gap": 2,                  // horizontal space between children (default 1)
    "align": "top",            // vertical alignment: top | center | bottom
    "children": [...]
}
```

#### `stack` — Vertical Layout
Arranges children top to bottom.

```json
{
    "type": "stack",
    "gap": 1,                  // vertical space between children (default 0)
    "children": [...]
}
```

#### `group` — Offset Coordinate Space
Shifts children by an offset. Useful for positioning within boards.

```json
{
    "type": "group",
    "x": 5, "y": 3,           // offset (also: offsetX, offsetY)
    "w": 40, "h": 20,         // explicit size (optional)
    "children": [...]
}
```

#### `board` — Freeform Absolute Positioning
The power tool. Children placed at absolute (x, y) coordinates within the board.
Ideal for maps, diagrams, artistic compositions, anything spatial.

```json
{
    "type": "board",
    "w": 60, "h": 30,         // size (recommended for boards)
    "title": "Map",            // optional (requires border)
    "style": "single",         // optional border style
    "border": true,            // default true if title/style set
    "pad": 1,                  // padding inside border (default 1)
    "children": [
        {"type": "label", "text": "~~~OCEAN~~~", "x": 10, "y": 2},
        {"type": "box", "title": "Cave", "x": 5, "y": 15, "pad": 0, "content": "dark"},
        {"type": "fill", "x": 20, "y": 8, "w": 10, "h": 3, "char": "."}
    ]
}
```

**Board vs box:** Box auto-layouts children vertically. Board places children wherever you specify. Use box for structured layouts, board for spatial art.

**Borderless boards:** Set `"border": false` (or just omit title/style) for invisible boards. Children float freely — great for composing complex diagrams inside boxes.

#### `status_panel` — Composite Game UI
Wraps bars + inventory + turn_log in a titled box. Convenience element.

```json
{
    "type": "status_panel",
    "title": "PLAYER",
    "bars": [{"label": "HP", "value": 73, "max": 100, "width": 15}],
    "items": [{"name": "Torch", "count": 3}],
    "entries": ["T1: Entered dungeon", "T2: Found torch"],
    "show_last": 3
}
```

---

### Content — Display Text and Data

#### `label` — Text Display
The simplest content element. Supports multi-line text and alignment.

```json
{
    "type": "label",
    "text": "Line 1\nLine 2",  // \n for line breaks
    "align": "center"          // left | center | right
}
```

**Pro tip:** Labels are your brush for freeform art inside boards. Place Unicode characters exactly where you want them with x, y coordinates.

#### `legend` — Key-Value Pairs
Formatted key-value display with aligned columns.

```json
{
    "type": "legend",
    "entries": [
        {"key": "●", "val": "Active node"},
        {"key": "○", "val": "Inactive node"},
        {"key": "◆", "val": "Critical path"}
    ]
}
```

⚠️ The field is `entries`, not `items`.

Entries can also be a dict: `{"●": "Active", "○": "Inactive"}` or strings with colons: `["●: Active", "○: Inactive"]`.

#### `grid` — Raw Pre-formatted Lines
Pastes raw text lines directly. No wrapping, no processing. Use when you've pre-composed ASCII art and just want to embed it.

```json
{
    "type": "grid",
    "lines": [
        "  [Client] ──────► (Gateway)",
        "                      │      ",
        "                      ▼      ",
        "                   {Auth?}   "
    ]
}
```

---

### Structural — Dividers and Spacing

#### `separator` — Horizontal Divider
Creates a horizontal rule. When inside a box, automatically connects to the box's borders using junction characters (├───┤).

```json
{"type": "separator"}                          // plain line
{"type": "separator", "title": "Section"}      // titled divider
{"type": "separator", "char": "═"}             // custom character
```

#### `spacer` — Empty Space
Inserts blank lines or columns.

```json
{"type": "spacer", "h": 2}          // 2 blank lines (also: "lines": 2)
{"type": "spacer", "w": 10}         // 10 columns wide (also: "cols": 10)
```

#### `transition` — Scene Divider
Decorative scene transition for narratives.

```json
{
    "type": "transition",
    "label": "time passes",
    "style": "dissolve"        // hard_cut | fade | dissolve | fast_forward |
                               // flashback | dream | temporal_skip
}
```

---

### Data Display — Bars, Inventories, Logs

#### `bar` — Progress/Status Bar

```json
{
    "type": "bar",
    "label": "HP",
    "value": 73,
    "max": 100,
    "width": 15,               // bar width in characters
    "filled": "█",             // fill character (default █)
    "empty": "░"               // empty character (default ░)
}
```

Renders: `HP [███████████░░░░] 73/100`

#### `inventory` — Item List

```json
{
    "type": "inventory",
    "items": [
        {"name": "Torch", "count": 3},
        {"name": "Key", "count": 1},
        {"name": "Potion", "count": 5}
    ],
    "cols": 3                  // items per row
}
```

#### `turn_log` — History Display

```json
{
    "type": "turn_log",
    "entries": [
        "T1: Entered dungeon",
        "T2: Found torch",
        "T3: Defeated goblin"
    ],
    "show_last": 3             // only show last N entries
}
```

---

### Drawing — Lines, Nodes, Fills

#### `line` — Point-to-Point Line

```json
{
    "type": "line",
    "x1": 0, "y1": 0,
    "x2": 20, "y2": 0,        // horizontal line
    "edge": "standard",        // standard | strong | weak | dashed | temporal
    "head": "right"            // arrow head (see arrow element)
}
```

Lines are routed: horizontal segments use ─, vertical use │, L-bends create junctions.

#### `arrow` — Line with Arrowhead
Same as line but auto-detects direction for arrowhead.

```json
{"type": "arrow", "x1": 0, "y1": 5, "x2": 20, "y2": 5}
```

Arrow heads: right, left, up, down, right-thin (→), left-thin (←), up-thin (↑), down-thin (↓), right-double (⇒), left-double (⇐), terminated (┤).

#### `node` — Semantic Labeled Node

```json
{"type": "node", "name": "Server", "nodeType": "entity"}       // [Server]
{"type": "node", "name": "Handle", "nodeType": "process"}      // (Handle)
{"type": "node", "name": "Auth?", "nodeType": "decision"}      // {Auth?}
{"type": "node", "name": "HTTP", "nodeType": "io"}             // <HTTP>
{"type": "node", "name": "API", "nodeType": "active"}          // ● API
{"type": "node", "name": "Cache", "nodeType": "inactive"}      // ○ Cache
```

Node types: entity `[]`, process `()`, decision `{}`, io `<>`, reference `[[]]`, critical `╔═ ═╗`, group `┌─ ─┐`, soft `╭─ ─╮`, active `●`, inactive `○`.

#### `connector` — Junction Point

```json
{"type": "connector", "char": "◆", "label": "nexus"}
```

#### `fill` — Pattern Region

```json
{"type": "fill", "w": 20, "h": 5, "char": "░"}                              // solid fill
{"type": "fill", "w": 20, "h": 5, "chars": " ░▒▓█", "gradient": true}       // horizontal gradient
{"type": "fill", "w": 20, "h": 5, "chars": "░▒▓█", "gradient": true, "direction": "vertical"}
{"type": "fill", "w": 20, "h": 10, "chars": " ░▒▓█", "gradient": true, "direction": "radial"}
```

Gradient directions: horizontal (default), vertical, radial.

#### `minimap` — 2D Grid Map

```json
{
    "type": "minimap",
    "cells": [
        "███░░░███",
        "█·····░░█",
        "█·█████·█",
        "█·····●·█",
        "███████·█"
    ]
}
```

#### `hexgrid` — Hex Territory Grid

```json
{
    "type": "hexgrid",
    "cells": [
        ["A", "A", ".", "B", "B"],
        ["A", ".", ".", "B"],
        [".", ".", "*", ".", "."],
        ["C", ".", ".", "D"],
        ["C", "C", ".", "D", "D"]
    ],
    "align": "center"
}
```

Even rows (0, 2, 4...) are wide; odd rows (1, 3...) are narrow (offset right). The engine handles all hex geometry automatically.

---

### Subpixel — High-Resolution Drawing

#### `canvas` — Subpixel Drawing Surface

```json
{
    "type": "canvas",
    "mode": "block",           // block (2×2, works everywhere) or braille (2×4, terminal only!)
    "w": 40, "h": 10,         // output size in terminal cells
    "draw": [
        {"cmd": "circle", "cx": 40, "cy": 10, "r": 8, "fill": true},
        {"cmd": "rect", "x0": 5, "y0": 2, "x1": 30, "y1": 18},
        {"cmd": "line", "x0": 0, "y0": 0, "x1": 79, "y1": 19},
        {"cmd": "dot", "x": 10, "y": 10},
        {"cmd": "polygon", "points": [[0,0], [20,5], [10,19]]},
        {"cmd": "text", "x": 2, "y": 0, "text": "HELLO"}
    ]
}
```

⚠️ **Braille mode is TERMINAL ONLY.** Braille characters do not render at consistent widths in markdown viewers, chat apps, or web UIs. Use `"mode": "block"` for universal compatibility.

Coordinate space is subpixel:
- Block mode: w×2 by h×2 (e.g., 40 cells → 80×20 subpixels)
- Braille mode: w×2 by h×4 (e.g., 40 cells → 80×40 subpixels)

Draw commands: `dot`, `line`, `rect` (+ fill), `circle` (+ fill, aspect-corrected), `polygon`, `text` (3×4 bitmap font, A-Z + digits + basic punctuation).

⚠️ **Circle aspect correction extends x-range.** Circles are stretched horizontally to appear circular on screen. A circle of radius `r` extends ~`2r` subpixels in x but only `r` in y. When placing circles near canvas edges, leave margins of at least `2r` in x and `r` in y to avoid clipping.

---

## Border Styles Reference

```
Style      Horizontal  Vertical  Corners            Junctions
─────────────────────────────────────────────────────────────────
single     ─           │         ┌ ┐ └ ┘            ├ ┤ ┬ ┴ ┼
double     ═           ║         ╔ ╗ ╚ ╝            ╠ ╣ ╦ ╩ ╬
rounded    ─           │         ╭ ╮ ╰ ╯            ├ ┤ ┬ ┴ ┼
heavy      ━           ┃         ┏ ┓ ┗ ┛            ┣ ┫ ┳ ┻ ╋
dashed     ┄           ┊         ┌ ┐ └ ┘            ├ ┤ ┬ ┴ ┼

Mixed (cross-style intersections — engine handles automatically):
single+double:  ╒ ╕ ╘ ╛ ╞ ╡ ╤ ╧ ╪ (single V + double H)
                ╓ ╖ ╙ ╜ ╟ ╢ ╥ ╨ ╫ (double V + single H)
```

---

## Unicode Character Palette

The Projector includes a comprehensive palette accessible via `--palette`. Here are the most-used categories:

### Box Drawing
```
single    ─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼
double    ═ ║ ╔ ╗ ╚ ╝ ╠ ╣ ╦ ╩ ╬
heavy     ━ ┃ ┏ ┓ ┗ ┛ ┣ ┫ ┳ ┻ ╋
rounded   ╭ ╮ ╰ ╯
dashed    ┄ ┅ ┆ ┇ ┈ ┉ ╌ ╍ ╎ ╏
```

### Shapes & Markers
```
filled    ■ ● ▲ ▼ ◆ ◉ ⬟ ⬡
open      □ ○ △ ▽ ◇ ◎ ⬠ ⬢
small     ▪ ▫ ∙ · ˙ ⋅
```

### Shading & Fills
```
blocks    ░ ▒ ▓ █                          (light → dense)
elevation ▁ ▂ ▃ ▄ ▅ ▆ ▇ █                 (terrain profiles)
half      ▀ ▄ ▌ ▐ █ ▘ ▝ ▖ ▗ ▚ ▞ ▛ ▜ ▙ ▟  (subpixel blocks)
```

### Arrows
```
basic     ← → ↑ ↓ ↔ ↕
diagonal  ↗ ↘ ↙ ↖
double    ⇐ ⇒ ⇑ ⇓ ⇔ ⇕
fancy     ➜ ➤ ▶ ◀ ▸ ◂
```

### Semantic Combinations
```
nodes       ◉──◉──◉
gradient    ░▒▓█▓▒░
elevation   ▁▂▃▄▅▆▇█
brightness  ·✦★◆★✦·
wave_field  ∿∿∿∿∿∿∿
moon_phases ☽ ◐ ○ ◑ ☾
```

### Mystical / Celestial / Musical
```
stars     ★ ☆ ✦ ✧ ✶ ✷ ✸ ✹ ✺ ⍟
sun/moon  ☀ ☉ ☼ ☽ ☾ ◐ ◑ ◒ ◓
runes     ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛈ ᛇ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛝ ᛟ ᛞ
elements  🜁 🜂 🜃 🜄
notes     ♩ ♪ ♫ ♬ 𝄞 𝄢
suits     ♠ ♣ ♥ ♦ ♤ ♧ ♡ ♢
chess     ♔ ♕ ♖ ♗ ♘ ♙ ♚ ♛ ♜ ♝ ♞ ♟
zodiac    ♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓
```

Run `python3 projector.py --palette` for the complete palette with all 18 categories.

---

## Composition Patterns

These patterns show how to combine elements for common layouts.

### Pattern 1: Sectioned Dashboard
Box with separators dividing logical sections.

```json
{
    "type": "box", "title": "SYSTEM", "style": "double",
    "children": [
        {"type": "label", "text": "Server: online", "align": "center"},
        {"type": "separator", "title": "Resources"},
        {"type": "bar", "label": "CPU", "value": 45, "max": 100, "width": 20},
        {"type": "bar", "label": "MEM", "value": 82, "max": 100, "width": 20},
        {"type": "separator", "title": "Logs"},
        {"type": "label", "text": "All systems nominal."}
    ]
}
```

### Pattern 2: Multi-Column Information
Row of boxes inside an outer frame.

```json
{
    "type": "box", "title": "OVERVIEW", "style": "double",
    "children": [{
        "type": "row", "gap": 2,
        "children": [
            {"type": "box", "title": "A", "content": "Panel A"},
            {"type": "box", "title": "B", "content": "Panel B"},
            {"type": "box", "title": "C", "content": "Panel C"}
        ]
    }]
}
```

### Pattern 3: Spatial Map
Board with scattered elements at absolute positions.

```json
{
    "type": "board", "title": "World Map", "style": "single",
    "w": 60, "h": 20,
    "children": [
        {"type": "label", "text": "~~~OCEAN~~~", "x": 5, "y": 2},
        {"type": "box", "title": "Town", "x": 25, "y": 5, "pad": 0, "content": "population: 50"},
        {"type": "label", "text": "♣♣♣ FOREST ♣♣♣", "x": 10, "y": 12},
        {"type": "fill", "x": 40, "y": 8, "w": 10, "h": 5, "char": "▲"}
    ]
}
```

### Pattern 4: Artistic Composition
Boardless board inside a styled box for freeform art with a frame.

```json
{
    "type": "box", "title": "The Scene", "style": "double",
    "children": [{
        "type": "board", "border": false, "w": 50, "h": 15, "pad": 0,
        "children": [
            {"type": "label", "text": "★", "x": 25, "y": 0},
            {"type": "label", "text": "╭───╮", "x": 22, "y": 2},
            {"type": "label", "text": "│ ◉ │", "x": 22, "y": 3},
            {"type": "label", "text": "╰───╯", "x": 22, "y": 4},
            {"type": "fill", "x": 0, "y": 10, "w": 50, "h": 3, "char": "░"}
        ]
    }]
}
```

### Pattern 5: Sidebar + Main Area
Row combining a structured panel with a spatial board.

```json
{
    "type": "box", "title": "GAME", "style": "double",
    "children": [{
        "type": "row", "gap": 2,
        "children": [
            {
                "type": "board", "title": "Map", "style": "single",
                "w": 40, "h": 15,
                "children": [
                    {"type": "label", "text": "@", "x": 20, "y": 7}
                ]
            },
            {
                "type": "box", "title": "Status", "style": "single",
                "children": [
                    {"type": "bar", "label": "HP", "value": 80, "max": 100, "width": 10},
                    {"type": "separator"},
                    {"type": "inventory", "items": [{"name": "Sword", "count": 1}]}
                ]
            }
        ]
    }]
}
```

### Pattern 6: Nested Border Hierarchy
Convey structural depth through border style progression.

```json
{
    "type": "box", "title": "SYSTEM", "style": "double",
    "children": [{
        "type": "box", "title": "Module", "style": "single",
        "children": [{
            "type": "box", "title": "Detail", "style": "rounded",
            "content": "innermost"
        }]
    }]
}
```

### Pattern 7: Data Visualization
Board-based chart with axis labels and data points.

```json
{
    "type": "box", "title": "Chart", "style": "single",
    "children": [{
        "type": "board", "border": false, "w": 50, "h": 12, "pad": 0,
        "children": [
            {"type": "label", "text": "▲ Y", "x": 0, "y": 0},
            {"type": "label", "text": "│", "x": 2, "y": 1},
            {"type": "label", "text": "│  ●", "x": 2, "y": 2},
            {"type": "label", "text": "│      ●", "x": 2, "y": 4},
            {"type": "label", "text": "│          ●", "x": 2, "y": 6},
            {"type": "label", "text": "└──────────────► X", "x": 2, "y": 8}
        ]
    }]
}
```

---

## Composition Philosophy

### Think in Layers

1. **Frame** — What contains everything? (box with style, or bare stack)
2. **Structure** — How is content organized? (row for columns, stack for sections, board for spatial)
3. **Content** — What fills the structure? (labels, legends, bars, grids)
4. **Detail** — What adds meaning? (fills for texture, separators for sections, transitions for narrative)

### The Board is Your Canvas

When you need pixel-perfect control, use a `board`. Every label, fill, and box inside it goes exactly where you specify. This is how you compose:
- Scatter plots (labels at x,y coordinates)
- Architectural diagrams (boxes connected by label arrows)
- Artistic scenes (fills for atmosphere, labels for details)
- Game maps (mix of boxes, labels, and fills)

### Separators are Smart

Inside a box, separators automatically connect to the box's borders:
```
┌─ Title ─────────┐
│ content above    │
├── Section ───────┤    ← separator connects to box borders
│ content below    │
└──────────────────┘
```

Free-standing separators (not in a box) render as plain lines.

### The Grid Escape Hatch

When something is too complex for structured elements — intricate ASCII art, complex wiring diagrams, pre-composed patterns — use `grid` to paste raw lines:

```json
{
    "type": "box", "title": "Circuit", "style": "double", "pad": 0,
    "children": [{
        "type": "grid",
        "lines": [
            "  [A] ──── [B]  ",
            "   │        │   ",
            "   └── [C] ─┘   "
        ]
    }]
}
```

The engine frames it perfectly. You handle the internal art.

### Labels Inside Boards: The Artistic Brush

For freeform art, labels placed at specific coordinates in a borderless board are your primary tool. Each label is a text string stamped at a precise location:

```json
{"type": "label", "text": "✧ ◆◆◆ ✧", "x": 24, "y": 1}
```

This is how all the artistic examples (Watcher, Tarot, Ocean Depths) are composed — dozens of labels at precise positions creating the illusion of freeform art, with the engine guaranteeing alignment.

---

## Lessons from the Field

These are hard-won lessons from building 35 examples.

### 1. Double-Width Unicode
Some Unicode characters (mystical symbols, emoji, CJK) render as 2 cells wide in monospace fonts. The engine handles measurement correctly, but you need to account for this in labels on boards:
- **One symbol per label** on spatial layouts. Don't mix wide and narrow characters in a label you're aligning.
- The engine's `char_width()` uses `unicodedata.east_asian_width()` — trust it.

### 2. Diagonal Alignment
For diagonal lines in boards (using ╱ and ╲ labels):
- **Consistent step=1.** Each row, the x coordinate shifts by exactly 1.
- `\` descends: x increases as y increases (6, 7, 8, 9)
- `/` descends: x decreases as y increases (24, 23, 22, 21)
- **Connect to markers, not letters.** Diagonals visually connect to ◆, ■, ●, ▫, ▪ — not to text labels like "R" or "E".

### 3. Waveforms
For audio-style waveforms (╱╲ patterns):
- Use ONLY ╱ and ╲. Do NOT mix with ─ (horizontal dash) — they don't visually connect.
- Center line = even alternation. Peaks/troughs = stacked ╱╱ or ╲╲.

### 4. Verify Alignment with Code
Verify x positions in complex board layouts with code:
```python
for j, ch in enumerate(line):
    if ch != ' ':
        print(f"  char '{ch}' at x={j}")
```

### 5. Legend Uses `entries`
The legend element reads `entries`, not `items`. Easy to mix up.

### 6. Fills Render Under Labels
In boards, element render order is list order — later children render on top. Place fills BEFORE labels so text shows on top of shading:

```json
"children": [
    {"type": "fill", "x": 0, "y": 3, "w": 50, "h": 5, "char": "░"},   // background first
    {"type": "label", "text": "VISIBLE TEXT", "x": 10, "y": 5}          // text on top
]
```

### 7. Compute Inner Dimensions Before Placing Children
The engine does not clip content at borders. Anything placed past the inner boundary renders past the border. Always compute the inner budget first:

```
bordered (default pad=1):  inner_w = w - 4,  inner_h = h - 4
borderless (pad=0):        inner_w = w,      inner_h = h
general:                   inner = size - 2 * (border + padding)
```

Then verify every child fits: `x + child_w <= inner_w` and `y + child_h <= inner_h`.

A full-interior fill for a `"w": 40, "h": 20` bordered board is `"w": 36, "h": 16`. Not 40x20.

### 8. Fill Gradients Are Asymmetric
The gradient index mapping uses `int()` (floor), so the first character in the `chars` array always gets more columns than the last. Two fills with reversed chars (`" ░▒▓"` vs `"▓▒░ "`) produce different density distributions, not a mirror. For perfectly symmetric gradients, use a single centered label with hand-typed characters instead.

### 9. Centering Counts All Characters
`align: center` centers the full string including leading and trailing spaces. A label with `"    ░░▒▒▓▓TEXT▓▓▒▒░░"` (4 leading spaces, 0 trailing) will render visually off-center. Keep decorative text symmetric, or omit padding and let the natural gap between the border and the first visible character serve as the fade.

---

## Iteration Workflow

The best results come from iterating:

1. **Compose** — Write the JSON spec expressing your intent
2. **Render** — `python3 projector.py spec.json`
3. **Review** — Does it express what you intended? Check alignment, spacing, aesthetics.
4. **Refine** — Adjust the spec. Tweak coordinates, change styles, add elements.
5. **Repeat** — Until it's right.

Save intermediate specs to files for complex pieces. The JSON is the source of truth — you can always re-render.

---

## Built-in Examples (31)

Run `python3 projector.py --example NAME` to see JSON + rendered output.

| Name | Description | Key Techniques |
|------|-------------|----------------|
| simple | Basic titled box | Minimal spec |
| multiline | Multi-line content | Content line breaks |
| row | Two boxes side by side | Row layout |
| hierarchy | Nested border styles | Style progression |
| dashboard | Status bars and sections | Separators, bars, labels |
| legend | Key-value display | Legend element |
| nodes | Semantic node types | All 10 node types |
| diagram | Flow diagram | Grid with hand-drawn arrows |
| game | RPG status panel | status_panel composite |
| minimap | Dungeon map | minimap + legend |
| fills | Fill patterns | Solid and gradient fills |
| braille | Braille subpixel shapes | Canvas + braille mode |
| blocks | Block subpixel shapes | Canvas + block mode |
| hexgrid | Hex territory map | hexgrid + labels |
| holographic | Multi-scale projection | Board + separators + labels |
| orthographic | 2D scatter plot | Board + axis labels + data points |
| architecture | System architecture | Nested boards + directional arrows |
| celestial | Observatory dashboard | Row + board + bars + turn_log |
| watcher | Freeform ASCII art | Board + dozens of positioned labels |
| board | Game world map | Board with mixed elements |
| complex | Multi-column architecture | Row of boxes + separator |
| alchemist | Mystical workspace | Row + board + fills + bars + legend |
| tarot | Tarot card | Board + symbols + zodiac |
| ocean | Underwater scene | Fills for density zones + labels for creatures |
| comic | Three-panel comic | Boxes + transitions + boards |
| spectrum | Audio spectrum analyzer | Board for bars + waveform + VU meters |
| circuit | PCB circuit board | Heavy traces + boards + BOM legend |
| terrain | Mountain cross-section | Board + elevation bars + fills |
| ancient_map | Fantasy map | Board + runes + hex territory + coastline |
| dungeon_crawler | Full RPG screen | Row + dungeon map + party stats + inventory + turn log + legend |
| rift | Sacred geometry manifold | Canvas subpixel + rune columns + zodiac + heavy border |
| fractal | Sierpinski gasket with recursion panels | Canvas polygons + row of depth comparisons |
| merkaba | Star tetrahedron with 3D perspective | Canvas wireframe + gradient fill + moon phases |
| flower | Flower of Life sacred geometry | Canvas overlapping circles + progressive construction row |
| garden | Sacred garden with Metatron's Cube | Canvas polygons + lines + circles + board starfield + legend |

---

*The model is the intelligence. The Projector is the execution. Together, they make perfect art.*
