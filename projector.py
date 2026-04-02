#!/usr/bin/env python3
"""
The Projector — ASCII/Unicode Layout Engine
============================================

Reads JSON structure descriptions, produces pixel-perfect ASCII/Unicode art.
Zero dependencies — Python 3 stdlib only.

The model is the intelligence. It decides WHAT to draw.
The Projector is the execution. It guarantees HOW it renders.

Architecture: Three-Pass Layout (measure → layout → render)
    Pass 1 — MEASURE (bottom-up):  How big does each element need to be?
    Pass 2 — LAYOUT  (top-down):   Where does each element go?
    Pass 3 — RENDER  (to canvas):  Draw to 2D character grid with smart compositing.

Smart compositing: when box-drawing characters overlap, the engine merges them
intelligently (─ meets │ = ┼, ═ meets ║ = ╬, etc.). Text always wins over borders.

Usage:
    echo '{"type":"box","title":"Hello","content":"World"}' | python3 projector.py
    python3 projector.py input.json
    python3 projector.py input.json > output.txt
    python3 projector.py --examples              # render all 30 built-in examples
    python3 projector.py --example dashboard      # show JSON + render for one example
    python3 projector.py --validate               # post-render structural validation
    python3 projector.py --ascii                  # Unicode → ASCII-safe substitution
    python3 projector.py --palette                # show full Unicode character palette
    python3 projector.py --palette celestial       # show one palette category

JSON Spec Format:
    Every element is a JSON object with at minimum a "type" field.
    Elements can contain "children" arrays for nesting.
    The root element can set "width" for fixed output width (otherwise auto-sized).

    Example — a titled box with two columns:
    {
        "type": "box", "title": "DASHBOARD", "style": "double",
        "children": [
            {
                "type": "row", "gap": 2,
                "children": [
                    {"type": "box", "title": "Left", "content": "Panel A"},
                    {"type": "box", "title": "Right", "content": "Panel B"}
                ]
            },
            {"type": "separator", "title": "Status"},
            {"type": "bar", "label": "CPU", "value": 73, "max": 100, "width": 20}
        ]
    }

Element Types (23 types, with `frame` as a `box` alias):
    CONTAINERS — hold children, provide structure
        box         Bordered container with optional title. Styles: single/double/rounded/heavy/dashed.
                    Props: title, style, content (string or list), pad/padding, w, h, maxW, gap, align
        row         Arrange children horizontally. Props: gap (default 1), align (top/center/bottom)
        stack       Arrange children vertically. Props: gap (default 0)
        group       Offset children by (x, y) — nested coordinate space. Props: offsetX/x, offsetY/y, w, h
        board       Freeform absolute positioning — children placed at their own x, y coords.
                    Props: w, h, title, style, border (bool), pad. Ideal for maps, diagrams, spatial art.
        status_panel Composite: box with bars + inventory + turn_log. Props: title, bars[], items[], entries[]

    CONTENT — display text and data
        label       Text with alignment. Props: text (string, supports \\n), align (left/center/right)
        legend      Key-value pairs. Props: entries (dict, or list of {key, val} objects)
        grid        Raw pre-formatted lines — no layout, just paste. Props: lines (list of strings or \\n string)

    STRUCTURAL — dividers and spacing
        separator   Horizontal divider, optionally titled. Connects to parent box borders automatically.
                    Props: title, char (default ─)
        spacer      Empty space. Props: lines/h (height), cols/w (width)
        transition  Scene transition marker. Props: label/text, style (hard_cut/fade/dissolve/fast_forward/
                    flashback/dream/temporal_skip)

    DATA DISPLAY — bars, inventories, logs
        bar         Progress/status bar. Props: label, value, max, width, filled (char), empty (char)
        inventory   Game-style item list. Props: items [{name, count}], cols
        turn_log    Append-only history. Props: entries [], show_last

    DRAWING — lines, nodes, fills
        line        Point-to-point line. Props: x1, y1, x2, y2, edge (standard/strong/weak/dashed/temporal), head
        arrow       Line with auto-detected arrowhead. Same props as line.
        node        Semantic labeled node: [Entity], (Process), {Decision}, <IO>, etc.
                    Props: name/text, nodeType (entity/process/decision/io/reference/critical/group/soft/active/inactive)
        connector   Junction point (●, ○, ◆, etc.). Props: char, label
        fill        Rectangle filled with pattern/gradient. Props: w, h, char/chars, gradient (bool), direction
                    (horizontal/vertical/radial)
        minimap     2D grid map with single-char cells. Props: cells (list of strings or char lists)
        hexgrid     Hex territory grid. Props: cells (2D array — even rows wide, odd rows offset)

    SUBPIXEL — high-resolution drawing
        canvas      Subpixel drawing surface (braille: 2×4 dots/cell, block: 2×2 dots/cell).
                    ⚠️ Braille mode is TERMINAL ONLY. Block mode works everywhere.
                    Props: mode (braille/block), w, h, draw [{cmd, ...}]
                    Draw commands: dot, line, rect, circle, polygon, text (3×4 bitmap font)

Border Styles:
    single   ─ │ ┌ ┐ └ ┘    (default)
    double   ═ ║ ╔ ╗ ╚ ╝
    rounded  ─ │ ╭ ╮ ╰ ╯
    heavy    ━ ┃ ┏ ┓ ┗ ┛
    dashed   ┄ ┊ ┌ ┐ └ ┘

Composability:
    Any element can nest inside any container. Common patterns:
    - box > row > [box, box, box]           — multi-column layout
    - box > [separator, label, bar]          — sectioned dashboard
    - board > [label, label, fill, box]      — freeform spatial layout
    - box > board > [label at x,y coords]    — artistic/map composition
    - row > [board, box]                     — side-by-side: spatial + structured

The engine handles all alignment, borders, character compositing, and Unicode
width measurement. The model focuses purely on structure and content.
"""

from __future__ import annotations

import json
import sys
import textwrap
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════

NONE, LIGHT, DOUBLE, HEAVY = 0, 1, 2, 3

# ═══════════════════════════════════════════════
# Unicode Character Palette
# Reference map of all documented character categories.
# Models use these in labels/boards; engine renders them.
# Reference map of all documented character categories
# ═══════════════════════════════════════════════

UNICODE_PALETTE: Dict[str, Dict[str, str]] = {
    "box_drawing": {
        "single":   "─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼",
        "double":   "═ ║ ╔ ╗ ╚ ╝ ╠ ╣ ╦ ╩ ╬",
        "heavy":    "━ ┃ ┏ ┓ ┗ ┛ ┣ ┫ ┳ ┻ ╋",
        "mixed":    "╒ ╕ ╘ ╛ ╞ ╡ ╥ ╨ ╪ ╓ ╖ ╙ ╜ ╟ ╢ ╫",
        "dashed":   "┄ ┅ ┆ ┇ ┈ ┉ ╌ ╍ ╎ ╏",
        "rounded":  "╭ ╮ ╰ ╯",
    },
    "shapes_markers": {
        "filled":   "■ ● ▲ ▼ ◆ ◉ ⬟ ⬡",
        "open":     "□ ○ △ ▽ ◇ ◎ ⬠ ⬢",
        "small":    "▪ ▫ ∙ · ˙ ⋅",
        "block":    "▀ ▄ ▌ ▐ ▁ ▂ ▃ ▅ ▆ ▇ █",
    },
    "arrows": {
        "basic":    "← → ↑ ↓ ↔ ↕",
        "diagonal": "↗ ↘ ↙ ↖",
        "double":   "⇐ ⇒ ⇑ ⇓ ⇔ ⇕",
        "fancy":    "➜ ➤ ▶ ◀ ▸ ◂",
    },
    "shading": {
        "block":    "░ ▒ ▓ █",
        "diagonal": "╱ ╲ ╳",
    },
    "elevation": {
        "bars":     "▁ ▂ ▃ ▄ ▅ ▆ ▇ █",
    },
    "half_block": {
        "pixels":   "▀ ▄ ▌ ▐ █ ░ ▒ ▓",
    },
    "diagonals": {
        "lines":    "╱ ╲ ╳",
    },
    "geometric": {
        "hexagons":   "⬡ ⬢",
        "pentagons":  "⬠ ⬟",
        "circles":    "◉ ◎ ○ ● ◌ ◍",
        "diamonds":   "◆ ◇ ◈",
        "triangles":  "▲ ▼ ◀ ▶ △ ▽ ◁ ▷",
        "squares":    "■ □ ▪ ▫ ▣ ▤ ▥ ▦ ▧ ▨ ▩",
    },
    "celestial": {
        "stars":    "★ ☆ ✦ ✧ ✶ ✷ ✸ ✹ ✺ ⍟ ✡ ⚝ ✫ ✬ ✭ ✮ ✯",
        "sun_moon": "☀ ☉ ☼ ☽ ☾ ◐ ◑ ◒ ◓",
        "planets":  "⊕ ⊗ ⊙",
        "zodiac":   "♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓",
    },
    "mystical": {
        "elements": "🜁 🜂 🜃 🜄",
        "symbols":  "☿ ♀ ♂ ♃ ♄ ♅ ♆ ♇",
        "sacred":   "✝ ☦ ☪ ☮ ☯ ✡ ☸",
        "occult":   "⛤ ⛧ ⍟ ⎈",
        "misc":     "∞ ℵ ∴ ∵ ※ ⁂ ☥",
        "runes":    "ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛈ ᛇ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛝ ᛟ ᛞ",
    },
    "musical": {
        "notes":    "♩ ♪ ♫ ♬ 𝄞 𝄢",
    },
    "weather": {
        "sky":      "☁ ☂ ☃ ❄ ❅ ❆ ☇ ☈",
        "waves":    "⌇ ≋ ∿ 〰",
        "flora":    "❀ ✿ ❁ ✾ ❃",
    },
    "abstract": {
        "sparks":   "⚡ ✧ ✦ ∗ ⁕ ⁑",
        "waves":    "∿ ≋ 〰 ⌇ ∼",
        "rotation": "⟳ ⟲ ↻ ↺",
        "radiation": "☢ ☣ ⚛",
        "eyes":     "◉ ◎ ⊙ ⊚ ⊛",
        "void":     "∅ ⌀ ◌",
        "sparkle":  "⁂ ※ ✻ ✼ ❋",
    },
    "cards_dice": {
        "suits":    "♠ ♣ ♥ ♦ ♤ ♧ ♡ ♢",
        "dice":     "⚀ ⚁ ⚂ ⚃ ⚄ ⚅",
        "chess":    "♔ ♕ ♖ ♗ ♘ ♙ ♚ ♛ ♜ ♝ ♞ ♟",
    },
    "electrical": {
        "symbols":  "⏚ ⎓ ⏛ ⎍ ⎎ ⏣ ⎊ ⏧",
    },
    "math_logic": {
        "operators": "∞ ≈ × ÷ ± ∑ ∫ ∂ ∇ √ ≤ ≥ ≠ ∈ ∉ ⊂ ⊃ ∪ ∩ ∧ ∨ ¬ ∀ ∃ ℵ",
        "greek":     "π φ ε δ λ Ω Σ Δ Θ Ψ",
        "circled":   "⊕ ⊖ ⊗ ⊘ ⊙ ⊚ ⊛ ⊜ ⊝",
        "brackets":  "⟨ ⟩ ⟪ ⟫",
    },
    "ellipsis": {
        "dots":     "⋮ ⋯ ⋰ ⋱",
    },
    "semantic_combos": {
        "nodes":       "◉──◉──◉",
        "gradient":    "░▒▓█▓▒░",
        "elevation":   "▁▂▃▄▅▆▇█",
        "brightness":  "·✦★◆★✦·",
        "wave_field":  "∿∿∿∿∿∿∿",
        "rune_line":   "ᚠ ᚢ ᚦ ᚨ",
        "moon_phases": "☽ ◐ ○ ◑ ☾",
        "dice_chain":  "⚀→⚁→⚂→⚃",
    },
}


# ═══════════════════════════════════════════════
# Border Styles
# ═══════════════════════════════════════════════

BORDER_STYLES: Dict[str, Dict[str, str]] = {
    "single": {
        "h": "─", "v": "│",
        "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
        "lj": "├", "rj": "┤", "tj": "┬", "bj": "┴", "x": "┼",
    },
    "double": {
        "h": "═", "v": "║",
        "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
        "lj": "╠", "rj": "╣", "tj": "╦", "bj": "╩", "x": "╬",
    },
    "rounded": {
        "h": "─", "v": "│",
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "lj": "├", "rj": "┤", "tj": "┬", "bj": "┴", "x": "┼",
    },
    "heavy": {
        "h": "━", "v": "┃",
        "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛",
        "lj": "┣", "rj": "┫", "tj": "┳", "bj": "┻", "x": "╋",
    },
    "dashed": {
        "h": "┄", "v": "┊",
        "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
        "lj": "├", "rj": "┤", "tj": "┬", "bj": "┴", "x": "┼",
    },
}


# ═══════════════════════════════════════════════
# Box Drawing Decomposition & Merge
# ═══════════════════════════════════════════════

# Each box-drawing char → (up, right, down, left) line weights.
# Merging two chars: max weight per direction, look up result.

_BOX_DECOMP: Dict[str, Tuple[int, int, int, int]] = {
    # Light (single)
    '─': (0,1,0,1), '│': (1,0,1,0),
    '┌': (0,1,1,0), '┐': (0,0,1,1), '└': (1,1,0,0), '┘': (1,0,0,1),
    '├': (1,1,1,0), '┤': (1,0,1,1), '┬': (0,1,1,1), '┴': (1,1,0,1), '┼': (1,1,1,1),
    # Double
    '═': (0,2,0,2), '║': (2,0,2,0),
    '╔': (0,2,2,0), '╗': (0,0,2,2), '╚': (2,2,0,0), '╝': (2,0,0,2),
    '╠': (2,2,2,0), '╣': (2,0,2,2), '╦': (0,2,2,2), '╩': (2,2,0,2), '╬': (2,2,2,2),
    # Heavy
    '━': (0,3,0,3), '┃': (3,0,3,0),
    '┏': (0,3,3,0), '┓': (0,0,3,3), '┗': (3,3,0,0), '┛': (3,0,0,3),
    '┣': (3,3,3,0), '┫': (3,0,3,3), '┳': (0,3,3,3), '┻': (3,3,0,3), '╋': (3,3,3,3),
    # Rounded (same weight as single, special corners)
    '╭': (0,1,1,0), '╮': (0,0,1,1), '╰': (1,1,0,0), '╯': (1,0,0,1),
    # Mixed: single vertical + double horizontal
    '╒': (0,2,1,0), '╕': (0,0,1,2), '╘': (1,2,0,0), '╛': (1,0,0,2),
    '╞': (1,2,1,0), '╡': (1,0,1,2), '╤': (0,2,1,2), '╧': (1,2,0,2), '╪': (1,2,1,2),
    # Mixed: double vertical + single horizontal
    '╓': (0,1,2,0), '╖': (0,0,2,1), '╙': (2,1,0,0), '╜': (2,0,0,1),
    '╟': (2,1,2,0), '╢': (2,0,2,1), '╥': (0,1,2,1), '╨': (2,1,0,1), '╫': (2,1,2,1),
    # Dashed (treated as light for merging)
    '┄': (0,1,0,1), '┈': (0,1,0,1), '┊': (1,0,1,0),
}

# Reverse lookup: (up, right, down, left) → char
_DIRS_TO_CHAR: Dict[Tuple[int, int, int, int], str] = {}
# Priority: standard chars first (not rounded/dashed)
for _ch, _dirs in _BOX_DECOMP.items():
    if _ch not in ('╭', '╮', '╰', '╯', '┄', '┈', '┊'):
        _DIRS_TO_CHAR.setdefault(_dirs, _ch)
for _ch, _dirs in _BOX_DECOMP.items():
    _DIRS_TO_CHAR.setdefault(_dirs, _ch)


def merge_box_chars(a: str, b: str) -> str:
    """Merge two box-drawing characters by combining their directional lines."""
    da = _BOX_DECOMP.get(a)
    db = _BOX_DECOMP.get(b)
    if da is None:
        return b
    if db is None:
        return a
    merged = (max(da[0], db[0]), max(da[1], db[1]),
              max(da[2], db[2]), max(da[3], db[3]))
    return _DIRS_TO_CHAR.get(merged, b)


# ═══════════════════════════════════════════════
# Text Measurement
# ═══════════════════════════════════════════════

def char_width(ch: str) -> int:
    """Display width of a single character."""
    if ch == '\n':
        return 0
    cat = unicodedata.category(ch)
    if cat.startswith('M'):  # combining marks
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ('F', 'W'):  # fullwidth or wide
        return 2
    return 1


def str_width(s: str) -> int:
    """Display width of a string."""
    return sum(char_width(ch) for ch in s)


def wrap_text(text: str, width: int) -> List[str]:
    """Wrap text to fit within display columns."""
    if width <= 0:
        return text.split('\n') if '\n' in text else [text]
    lines: List[str] = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('')
            continue
        wrapped = textwrap.wrap(paragraph, width=width,
                                break_long_words=True, break_on_hyphens=False)
        lines.extend(wrapped if wrapped else [''])
    return lines


def pad_to_width(s: str, width: int, align: str = 'left') -> str:
    """Pad string to exact display width."""
    sw = str_width(s)
    if sw >= width:
        return s
    gap = width - sw
    if align == 'center':
        left = gap // 2
        right = gap - left
        return ' ' * left + s + ' ' * right
    elif align == 'right':
        return ' ' * gap + s
    return s + ' ' * gap


# ═══════════════════════════════════════════════
# Canvas
# ═══════════════════════════════════════════════

class Canvas:
    """2D character grid with smart box-drawing merge."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid: List[List[str]] = [[' '] * width for _ in range(height)]

    def put(self, x: int, y: int, ch: str, merge: bool = False) -> None:
        """Place a character. If merge=True, smart-merge box-drawing chars."""
        if 0 <= x < self.width and 0 <= y < self.height:
            if merge and ch in _BOX_DECOMP and self.grid[y][x] in _BOX_DECOMP:
                self.grid[y][x] = merge_box_chars(self.grid[y][x], ch)
            else:
                self.grid[y][x] = ch

    def put_str(self, x: int, y: int, s: str) -> None:
        """Write a string at (x, y). No merge — text overwrites.
        Handles wide chars (emoji, CJK) by blanking the next cell."""
        cx = x
        for ch in s:
            w = char_width(ch)
            if w == 0:
                continue
            if 0 <= cx < self.width and 0 <= y < self.height:
                self.grid[y][cx] = ch
                if w == 2 and cx + 1 < self.width:
                    self.grid[y][cx + 1] = ''  # blank: wide char continuation
            cx += w

    def put_hline(self, x: int, y: int, length: int, ch: str = '─',
                  merge: bool = True) -> None:
        """Draw a horizontal line."""
        for i in range(length):
            self.put(x + i, y, ch, merge=merge)

    def put_vline(self, x: int, y: int, length: int, ch: str = '│',
                  merge: bool = True) -> None:
        """Draw a vertical line."""
        for i in range(length):
            self.put(x, y + i, ch, merge=merge)

    def render(self) -> str:
        """Render canvas to string. Skips wide-char continuation cells."""
        lines = []
        for row in self.grid:
            lines.append(''.join(ch for ch in row if ch != '').rstrip())
        while lines and not lines[-1]:
            lines.pop()
        return '\n'.join(lines)


# ═══════════════════════════════════════════════
# Element Base
# ═══════════════════════════════════════════════

@dataclass
class Rect:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class Element:
    """Base class for layout elements."""

    def __init__(self, props: Dict[str, Any]):
        self.props = props
        self.rect = Rect()
        self._min_w = 0
        self._min_h = 0

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        """Pass 1 (bottom-up): return (min_width, min_height)."""
        return (0, 0)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        """Pass 2 (top-down): assign position and size."""
        self.rect = Rect(x, y, w, h)

    def render(self, canvas: Canvas) -> None:
        """Pass 3: draw to canvas."""
        pass


# ═══════════════════════════════════════════════
# Label
# ═══════════════════════════════════════════════

class LabelElement(Element):
    """Text with alignment."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._lines: List[str] = []

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        text = self.props.get('text', '')
        raw = text.split('\n') if isinstance(text, str) else list(text)
        if avail_w > 0:
            lines: List[str] = []
            for line in raw:
                lines.extend(wrap_text(line, avail_w))
        else:
            lines = raw
        self._lines = lines
        w = max((str_width(l) for l in lines), default=0)
        h = len(lines)
        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)
        # Re-wrap to actual width
        text = self.props.get('text', '')
        raw = text.split('\n') if isinstance(text, str) else list(text)
        lines: List[str] = []
        for line in raw:
            lines.extend(wrap_text(line, w))
        self._lines = lines

    def render(self, canvas: Canvas) -> None:
        align = self.props.get('align', 'left')
        for i, line in enumerate(self._lines):
            if i >= self.rect.h:
                break
            padded = pad_to_width(line, self.rect.w, align)
            canvas.put_str(self.rect.x, self.rect.y + i, padded)


# ═══════════════════════════════════════════════
# Spacer
# ═══════════════════════════════════════════════

class SpacerElement(Element):
    """Empty space."""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        h = self.props.get('lines', self.props.get('h', 1))
        w = self.props.get('cols', self.props.get('w', 0))
        self._min_w, self._min_h = w, h
        return (w, h)


# ═══════════════════════════════════════════════
# Separator
# ═══════════════════════════════════════════════

class SeparatorElement(Element):
    """Horizontal divider, optionally with title. Connects to parent box borders."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._parent_style: Optional[Dict[str, str]] = None

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        title = self.props.get('title', '')
        w = str_width(title) + 6 if title else 1
        self._min_w, self._min_h = w, 1
        return (w, 1)

    def render(self, canvas: Canvas) -> None:
        x, y, w = self.rect.x, self.rect.y, self.rect.w
        title = self.props.get('title', '')

        if self._parent_style:
            # Inside a box: use junction chars
            style = self._parent_style
            canvas.put(x, y, style['lj'], merge=True)
            if title:
                inner = style['h'] + ' ' + title + ' '
                canvas.put_str(x + 1, y, inner)
                rem_start = x + 1 + str_width(inner)
                rem_len = (x + w - 1) - rem_start
                if rem_len > 0:
                    canvas.put_hline(rem_start, y, rem_len, style['h'], merge=True)
            else:
                canvas.put_hline(x + 1, y, w - 2, style['h'], merge=True)
            canvas.put(x + w - 1, y, style['rj'], merge=True)
        else:
            # Free-standing separator
            ch = self.props.get('char', '─')
            if title:
                prefix = ch * 2 + ' '
                suffix_len = max(w - str_width(prefix) - str_width(title) - 1, 2)
                line = prefix + title + ' ' + ch * suffix_len
                canvas.put_str(x, y, line)
            else:
                canvas.put_hline(x, y, w, ch, merge=True)


# ═══════════════════════════════════════════════
# Legend
# ═══════════════════════════════════════════════

class LegendElement(Element):
    """Key-value legend display."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._items: List[Tuple[str, str]] = []
        self._key_width = 0

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        entries = self.props.get('entries', [])
        if isinstance(entries, dict):
            self._items = [(str(k), str(v)) for k, v in entries.items()]
        elif isinstance(entries, list):
            self._items = []
            for e in entries:
                if isinstance(e, dict) and 'key' in e:
                    self._items.append((str(e['key']), str(e.get('val', e.get('value', '')))))
                elif isinstance(e, (list, tuple)) and len(e) >= 2:
                    self._items.append((str(e[0]), str(e[1])))
                elif isinstance(e, str) and ':' in e:
                    k, v = e.split(':', 1)
                    self._items.append((k.strip(), v.strip()))
                else:
                    self._items.append((str(e), ''))
        self._key_width = max((str_width(k) for k, _ in self._items), default=0)
        w = max((str_width(k) + 2 + str_width(v) for k, v in self._items), default=0)
        h = len(self._items)
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        for i, (k, v) in enumerate(self._items):
            if i >= self.rect.h:
                break
            line = pad_to_width(k, self._key_width, 'left') + '  ' + v
            canvas.put_str(self.rect.x, self.rect.y + i, line)


# ═══════════════════════════════════════════════
# Grid (raw passthrough)
# ═══════════════════════════════════════════════

class GridElement(Element):
    """Raw pre-formatted lines — no layout, just paste."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._lines: List[str] = []

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        lines = self.props.get('lines', [])
        if isinstance(lines, str):
            lines = lines.split('\n')
        self._lines = lines
        w = max((str_width(l) for l in lines), default=0)
        h = len(lines)
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        for i, line in enumerate(self._lines):
            if i >= self.rect.h:
                break
            canvas.put_str(self.rect.x, self.rect.y + i, line)


# ═══════════════════════════════════════════════
# Box
# ═══════════════════════════════════════════════

class BoxElement(Element):
    """Container with border, optional title, content or children. Auto-sizes."""

    def __init__(self, props: Dict[str, Any], children: Optional[List[Element]] = None):
        super().__init__(props)
        self.children = children or []
        self._content_lines: List[str] = []

    def _style(self) -> Dict[str, str]:
        name = self.props.get('style', 'single')
        if isinstance(name, dict):
            return name
        return BORDER_STYLES.get(name, BORDER_STYLES['single'])

    def _pad(self) -> int:
        return self.props.get('pad', self.props.get('padding', 1))

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        pad = self._pad()
        border = 2  # left + right
        inner_avail = max(avail_w - border - 2 * pad, 0) if avail_w > 0 else 0

        title = self.props.get('title', '')
        # Title needs: corner + h + space + title + space + h + corner
        title_min_w = str_width(title) + 6 if title else 0

        if self.children:
            child_w, child_h = 0, 0
            gap = self.props.get('gap', 0)
            for i, child in enumerate(self.children):
                cw, ch = child.measure(inner_avail)
                child_w = max(child_w, cw)
                child_h += ch + (gap if i > 0 else 0)
            content_w, content_h = child_w, child_h
        else:
            content = self.props.get('content', '')
            if isinstance(content, list):
                lines = list(content)
            elif inner_avail > 0:
                lines = wrap_text(str(content), inner_avail)
            else:
                lines = str(content).split('\n')
            self._content_lines = lines
            content_w = max((str_width(l) for l in lines), default=0)
            content_h = len(lines) if lines != [''] else 0

        # Box width = max(content needs, title needs)
        w = max(content_w + 2 * pad + border, title_min_w)
        h = content_h + 2 * pad + border

        # Explicit overrides
        if 'w' in self.props and self.props['w'] != 'auto':
            w = int(self.props['w'])
        if 'maxW' in self.props:
            w = min(w, int(self.props['maxW']))
        if 'h' in self.props and self.props['h'] != 'auto':
            h = int(self.props['h'])

        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        # Respect declared dimensions over parent allocation
        if 'w' in self.props and self.props['w'] != 'auto':
            w = int(self.props['w'])
        if 'h' in self.props and self.props['h'] != 'auto':
            h = int(self.props['h'])
        self.rect = Rect(x, y, w, h)
        pad = self._pad()
        cx = x + 1 + pad
        cy = y + 1 + pad
        cw = w - 2 - 2 * pad
        ch = h - 2 - 2 * pad

        if self.children:
            gap = self.props.get('gap', 0)
            child_y = cy
            for child in self.children:
                child_h = child._min_h
                if isinstance(child, SeparatorElement):
                    # Separators extend to box borders
                    child.layout(x, child_y, w, 1)
                    child._parent_style = self._style()
                else:
                    child.layout(cx, child_y, cw, child_h)
                child_y += child_h + gap
        else:
            # Re-wrap content to actual width
            content = self.props.get('content', '')
            if isinstance(content, list):
                self._content_lines = list(content)
            elif cw > 0:
                self._content_lines = wrap_text(str(content), cw)
            else:
                self._content_lines = [str(content)]

    def render(self, canvas: Canvas) -> None:
        x, y, w, h = self.rect.x, self.rect.y, self.rect.w, self.rect.h
        if w < 2 or h < 2:
            return
        style = self._style()
        pad = self._pad()

        # Border
        canvas.put(x, y, style['tl'], merge=True)
        canvas.put(x + w - 1, y, style['tr'], merge=True)
        canvas.put_hline(x + 1, y, w - 2, style['h'], merge=True)
        canvas.put(x, y + h - 1, style['bl'], merge=True)
        canvas.put(x + w - 1, y + h - 1, style['br'], merge=True)
        canvas.put_hline(x + 1, y + h - 1, w - 2, style['h'], merge=True)
        for i in range(1, h - 1):
            canvas.put(x, y + i, style['v'], merge=True)
            canvas.put(x + w - 1, y + i, style['v'], merge=True)

        # Title
        title = self.props.get('title', '')
        if title and w > 6:
            title_str = ' ' + title + ' '
            canvas.put_str(x + 2, y, title_str)

        # Content
        if self.children:
            for child in self.children:
                child.render(canvas)
        else:
            cx = x + 1 + pad
            cy = y + 1 + pad
            cw = w - 2 - 2 * pad
            align = self.props.get('align', 'left')
            for i, line in enumerate(self._content_lines):
                if cy + i >= y + h - 1:
                    break
                padded = pad_to_width(line, cw, align)
                canvas.put_str(cx, cy + i, padded)


# ═══════════════════════════════════════════════
# Row (horizontal layout)
# ═══════════════════════════════════════════════

class RowElement(Element):
    """Arrange children horizontally."""

    def __init__(self, props: Dict[str, Any], children: List[Element]):
        super().__init__(props)
        self.children = children

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        gap = self.props.get('gap', 1)
        total_w, max_h = 0, 0
        for i, child in enumerate(self.children):
            cw, ch = child.measure(0)
            total_w += cw + (gap if i > 0 else 0)
            max_h = max(max_h, ch)
        self._min_w, self._min_h = total_w, max_h
        return (total_w, max_h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)
        gap = self.props.get('gap', 1)
        align = self.props.get('align', 'top')
        cx = x
        for child in self.children:
            cw = child._min_w
            ch = child._min_h
            if align == 'center':
                cy = y + (h - ch) // 2
            elif align == 'bottom':
                cy = y + h - ch
            else:
                cy = y
            child.layout(cx, cy, cw, ch)
            cx += cw + gap

    def render(self, canvas: Canvas) -> None:
        for child in self.children:
            child.render(canvas)


# ═══════════════════════════════════════════════
# Stack (vertical layout)
# ═══════════════════════════════════════════════

class StackElement(Element):
    """Arrange children vertically."""

    def __init__(self, props: Dict[str, Any], children: List[Element]):
        super().__init__(props)
        self.children = children

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        gap = self.props.get('gap', 0)
        max_w, total_h = 0, 0
        for i, child in enumerate(self.children):
            cw, ch = child.measure(avail_w)
            max_w = max(max_w, cw)
            total_h += ch + (gap if i > 0 else 0)
        self._min_w, self._min_h = max_w, total_h
        return (max_w, total_h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)
        gap = self.props.get('gap', 0)
        cy = y
        for child in self.children:
            ch = child._min_h
            child.layout(x, cy, w, ch)
            cy += ch + gap

    def render(self, canvas: Canvas) -> None:
        for child in self.children:
            child.render(canvas)


# ═══════════════════════════════════════════════
# Bar (progress/status bar)
# ═══════════════════════════════════════════════

class BarElement(Element):
    """Progress/status bar: HP [████████░░] 80/100"""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        label = self.props.get('label', '')
        width = self.props.get('width', 10)
        mx = self.props.get('max', 100)
        val = self.props.get('value', 0)
        # "Label [██████████] val/max"
        bar_str = f"{label} [{'█' * width}] {val}/{mx}"
        self._min_w = str_width(bar_str)
        self._min_h = 1
        return (self._min_w, 1)

    def render(self, canvas: Canvas) -> None:
        label = self.props.get('label', '')
        width = self.props.get('width', 10)
        mx = self.props.get('max', 100)
        val = min(self.props.get('value', 0), mx)
        filled_char = self.props.get('filled', '█')
        empty_char = self.props.get('empty', '░')

        filled = round(val / mx * width) if mx > 0 else 0
        empty = width - filled
        bar = f"{label} [{filled_char * filled}{empty_char * empty}] {val}/{mx}"
        canvas.put_str(self.rect.x, self.rect.y, bar)


# ═══════════════════════════════════════════════
# Line / Arrow
# ═══════════════════════════════════════════════

# Edge style characters
EDGE_STYLES: Dict[str, str] = {
    'standard': '─',
    'strong': '═',
    'weak': '·',
    'dashed': '╌',
    'temporal': '~',
}

ARROW_HEADS: Dict[str, str] = {
    'right': '►', 'left': '◄', 'up': '▲', 'down': '▼',
    'right-thin': '→', 'left-thin': '←', 'up-thin': '↑', 'down-thin': '↓',
    'right-double': '⇒', 'left-double': '⇐',
    'terminated': '┤',
}

ARROW_V_CHARS: Dict[str, str] = {
    'standard': '│', 'strong': '║', 'weak': '·', 'dashed': '╎', 'temporal': '~',
}


class LineElement(Element):
    """Point-to-point line (horizontal, vertical, or routed)."""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        x1 = self.props.get('x1', 0)
        y1 = self.props.get('y1', 0)
        x2 = self.props.get('x2', x1)
        y2 = self.props.get('y2', y1)
        w = abs(x2 - x1) + 1
        h = abs(y2 - y1) + 1
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        x1 = self.rect.x + self.props.get('x1', 0)
        y1 = self.rect.y + self.props.get('y1', 0)
        x2 = self.rect.x + self.props.get('x2', x1 - self.rect.x)
        y2 = self.rect.y + self.props.get('y2', y1 - self.rect.y)

        edge = self.props.get('edge', 'standard')
        h_ch = EDGE_STYLES.get(edge, '─')
        v_ch = ARROW_V_CHARS.get(edge, '│')
        head = self.props.get('head', '')
        head_ch = ARROW_HEADS.get(head, head) if head else ''

        if y1 == y2:
            # Horizontal line
            start, end = min(x1, x2), max(x1, x2)
            for x in range(start, end + 1):
                canvas.put(x, y1, h_ch, merge=True)
            if head_ch:
                if x2 >= x1:
                    canvas.put(x2, y2, head_ch)
                else:
                    canvas.put(x2, y2, head_ch)
        elif x1 == x2:
            # Vertical line
            start, end = min(y1, y2), max(y1, y2)
            for y in range(start, end + 1):
                canvas.put(x1, y, v_ch, merge=True)
            if head_ch:
                canvas.put(x2, y2, head_ch)
        else:
            # L-route: horizontal then vertical
            mid_x = x2
            for x in range(min(x1, mid_x), max(x1, mid_x) + 1):
                canvas.put(x, y1, h_ch, merge=True)
            for y in range(min(y1, y2), max(y1, y2) + 1):
                canvas.put(mid_x, y, v_ch, merge=True)
            # Corner
            canvas.put(mid_x, y1, '┼' if edge == 'standard' else '+', merge=True)
            if head_ch:
                canvas.put(x2, y2, head_ch)


class ArrowElement(LineElement):
    """Line with an arrowhead — sugar over LineElement."""

    def __init__(self, props: Dict[str, Any]):
        # Auto-detect arrow direction if not specified
        if 'head' not in props:
            x1 = props.get('x1', 0)
            y1 = props.get('y1', 0)
            x2 = props.get('x2', x1)
            y2 = props.get('y2', y1)
            if y1 == y2:
                props['head'] = 'right-thin' if x2 >= x1 else 'left-thin'
            else:
                props['head'] = 'down-thin' if y2 >= y1 else 'up-thin'
        super().__init__(props)


# ═══════════════════════════════════════════════
# Node (semantic labeled node)
# ═══════════════════════════════════════════════

NODE_BRACKETS: Dict[str, Tuple[str, str]] = {
    'entity': ('[', ']'),
    'process': ('(', ')'),
    'decision': ('{', '}'),
    'io': ('<', '>'),
    'reference': ('[[', ']]'),
    'critical': ('╔═', '═╗'),
    'group': ('┌─', '─┐'),
    'soft': ('╭─', '─╮'),
}

NODE_MARKERS: Dict[str, str] = {
    'active': '●',
    'inactive': '○',
}


class NodeElement(Element):
    """Semantic labeled node: [Entity], (Process), {Decision}, etc."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._rendered = ''

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        name = self.props.get('name', self.props.get('text', ''))
        ntype = self.props.get('nodeType', self.props.get('node_type', 'entity'))

        if ntype in NODE_MARKERS:
            self._rendered = f"{NODE_MARKERS[ntype]} {name}"
        elif ntype in NODE_BRACKETS:
            left, right = NODE_BRACKETS[ntype]
            self._rendered = f"{left}{name}{right}"
        else:
            self._rendered = f"[{name}]"

        w = str_width(self._rendered)
        self._min_w, self._min_h = w, 1
        return (w, 1)

    def render(self, canvas: Canvas) -> None:
        canvas.put_str(self.rect.x, self.rect.y, self._rendered)


# ═══════════════════════════════════════════════
# Connector (junction point)
# ═══════════════════════════════════════════════

class ConnectorElement(Element):
    """Junction node: ●, ○, ◆, ┼, etc."""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        ch = self.props.get('char', '●')
        label = self.props.get('label', '')
        w = str_width(ch) + (1 + str_width(label) if label else 0)
        self._min_w, self._min_h = w, 1
        return (w, 1)

    def render(self, canvas: Canvas) -> None:
        ch = self.props.get('char', '●')
        label = self.props.get('label', '')
        canvas.put_str(self.rect.x, self.rect.y, ch)
        if label:
            canvas.put_str(self.rect.x + str_width(ch) + 1, self.rect.y, label)


# ═══════════════════════════════════════════════
# Fill (pattern region)
# ═══════════════════════════════════════════════

class FillElement(Element):
    """Rectangle filled with a repeating character or gradient pattern."""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        w = self.props.get('w', self.props.get('cols', 1))
        h = self.props.get('h', self.props.get('lines', 1))
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        chars = self.props.get('chars', self.props.get('char', '░'))
        gradient = self.props.get('gradient', False)
        direction = self.props.get('direction', 'horizontal')
        if gradient and isinstance(chars, str) and len(chars) > 1:
            if direction == 'vertical':
                # Vertical gradient across height
                for row in range(self.rect.h):
                    idx = int(row / max(self.rect.h - 1, 1) * (len(chars) - 1))
                    for col in range(self.rect.w):
                        canvas.put(self.rect.x + col, self.rect.y + row, chars[idx])
            elif direction == 'radial':
                # Radial gradient from center outward
                cx, cy = self.rect.w / 2, self.rect.h / 2
                max_dist = ((cx ** 2) + (cy ** 2)) ** 0.5
                for row in range(self.rect.h):
                    for col in range(self.rect.w):
                        dist = (((col - cx) ** 2) + (((row - cy) * 2) ** 2)) ** 0.5
                        idx = int(min(dist / max(max_dist, 1), 1.0) * (len(chars) - 1))
                        canvas.put(self.rect.x + col, self.rect.y + row, chars[idx])
            else:
                # Horizontal gradient across width
                for row in range(self.rect.h):
                    for col in range(self.rect.w):
                        idx = int(col / max(self.rect.w - 1, 1) * (len(chars) - 1))
                        canvas.put(self.rect.x + col, self.rect.y + row, chars[idx])
        else:
            ch = chars if isinstance(chars, str) and len(chars) == 1 else '░'
            for row in range(self.rect.h):
                for col in range(self.rect.w):
                    canvas.put(self.rect.x + col, self.rect.y + row, ch)


# ═══════════════════════════════════════════════
# Group (nested coordinate space)
# ═══════════════════════════════════════════════

class GroupElement(Element):
    """Offset children by (x, y) — nested coordinate space."""

    def __init__(self, props: Dict[str, Any], children: List[Element]):
        super().__init__(props)
        self.children = children

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        ox = self.props.get('offsetX', self.props.get('x', 0))
        oy = self.props.get('offsetY', self.props.get('y', 0))
        max_w, max_h = 0, 0
        for child in self.children:
            cw, ch = child.measure(avail_w)
            max_w = max(max_w, cw)
            max_h = max(max_h, ch)
        # Group size includes offset + largest child
        w = ox + max_w
        h = oy + max_h
        if 'w' in self.props:
            w = int(self.props['w'])
        if 'h' in self.props:
            h = int(self.props['h'])
        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)
        ox = self.props.get('offsetX', self.props.get('x', 0))
        oy = self.props.get('offsetY', self.props.get('y', 0))
        # Stack children vertically within the group
        cy = y + oy
        for child in self.children:
            child.layout(x + ox, cy, child._min_w, child._min_h)
            cy += child._min_h

    def render(self, canvas: Canvas) -> None:
        for child in self.children:
            child.render(canvas)


# ═══════════════════════════════════════════════
# Board (freeform absolute positioning)
# ═══════════════════════════════════════════════

class BoardElement(Element):
    """Freeform container where children are placed at absolute (x, y) positions.

    Each child specifies its own x, y coordinates within the board.
    Children can overlap — later children render on top of earlier ones.
    The board can optionally have a border (like box) or be borderless.

    Unlike box/row/stack which auto-layout children, board gives full
    spatial control for maps, game boards, spatial diagrams, etc.

    JSON spec:
        {
            "type": "board",
            "w": 60, "h": 30,          // explicit size (recommended)
            "title": "The Map",         // optional title (requires border)
            "style": "single",          // optional border style
            "border": True,             // default true if title/style set
            "children": [
                {"type": "label", "text": "~~~OCEAN~~~", "x": 10, "y": 2},
                {"type": "box", "title": "Cave", "x": 5, "y": 15, ...},
                {"type": "fill", "x": 20, "y": 8, "w": 10, "h": 3, "char": "."},
                ...
            ]
        }

    Children read x, y from their own props for positioning.
    If a child has no x/y, it defaults to (0, 0) within the content area.
    """

    def __init__(self, props: Dict[str, Any], children: List[Element]):
        super().__init__(props)
        self.children = children

    def _has_border(self) -> bool:
        if 'border' in self.props:
            return bool(self.props['border'])
        return bool(self.props.get('title') or self.props.get('style'))

    def _style(self) -> Dict[str, str]:
        name = self.props.get('style', 'single')
        if isinstance(name, dict):
            return name
        return BORDER_STYLES.get(name, BORDER_STYLES['single'])

    def _pad(self) -> int:
        return self.props.get('pad', self.props.get('padding', 1))

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        has_border = self._has_border()
        pad = self._pad() if has_border else 0
        border = 2 if has_border else 0

        # If explicit size given, use it
        if 'w' in self.props and 'h' in self.props:
            w = int(self.props['w'])
            h = int(self.props['h'])
            self._min_w, self._min_h = w, h
            # Still measure children so they know their sizes
            inner_avail = max(w - border - 2 * pad, 0)
            for child in self.children:
                child.measure(inner_avail)
            return (w, h)

        # Auto-size: find the bounding box of all children
        inner_avail = max(avail_w - border - 2 * pad, 0) if avail_w > 0 else 0
        max_right, max_bottom = 0, 0
        for child in self.children:
            cx = child.props.get('x', 0)
            cy = child.props.get('y', 0)
            cw, ch = child.measure(inner_avail)
            max_right = max(max_right, cx + cw)
            max_bottom = max(max_bottom, cy + ch)

        w = max_right + 2 * pad + border
        h = max_bottom + 2 * pad + border

        title = self.props.get('title', '')
        if title and has_border:
            title_min_w = str_width(title) + 6
            w = max(w, title_min_w)

        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        # Respect declared dimensions over parent allocation (e.g., stack
        # passes its full width to every child — boards must clamp to their
        # own declared size so borders and content don't overflow).
        if 'w' in self.props:
            w = int(self.props['w'])
        if 'h' in self.props:
            h = int(self.props['h'])
        self.rect = Rect(x, y, w, h)
        has_border = self._has_border()
        pad = self._pad() if has_border else 0
        border_offset = 1 if has_border else 0

        # Content origin — children's (0,0) starts here
        ox = x + border_offset + pad
        oy = y + border_offset + pad
        inner_w = w - 2 * (border_offset + pad)
        inner_h = h - 2 * (border_offset + pad)

        for child in self.children:
            cy = child.props.get('y', 0)
            cw = child._min_w
            ch = child._min_h
            align = child.props.get('align', None)
            if 'x' in child.props:
                cx = child.props['x']
            elif align == 'center':
                cx = max((inner_w - cw) // 2, 0)
            elif align == 'right':
                cx = max(inner_w - cw, 0)
            else:
                cx = 0
            child.layout(ox + cx, oy + cy, cw, ch)

    def render(self, canvas: Canvas) -> None:
        x, y, w, h = self.rect.x, self.rect.y, self.rect.w, self.rect.h
        has_border = self._has_border()

        if has_border and w >= 2 and h >= 2:
            style = self._style()
            # Border
            canvas.put(x, y, style['tl'], merge=True)
            canvas.put(x + w - 1, y, style['tr'], merge=True)
            canvas.put_hline(x + 1, y, w - 2, style['h'], merge=True)
            canvas.put(x, y + h - 1, style['bl'], merge=True)
            canvas.put(x + w - 1, y + h - 1, style['br'], merge=True)
            canvas.put_hline(x + 1, y + h - 1, w - 2, style['h'], merge=True)
            for i in range(1, h - 1):
                canvas.put(x, y + i, style['v'], merge=True)
                canvas.put(x + w - 1, y + i, style['v'], merge=True)

            # Title
            title = self.props.get('title', '')
            if title and w > 6:
                title_str = ' ' + title + ' '
                canvas.put_str(x + 2, y, title_str)

        # Render children (later children render on top)
        for child in self.children:
            child.render(canvas)


# ═══════════════════════════════════════════════
# HexGrid (territory / strategy maps)
# ═══════════════════════════════════════════════

class HexGridElement(Element):
    """Hex grid with cell labels — for territory maps, strategy boards, etc.

    The engine handles all hex geometry (/ \\ | tiling). The model just provides
    a 2D array of cell values.

    JSON spec:
        {
            "type": "hexgrid",
            "cells": [
                ["A", "A", ".", "B", "B"],
                ["A", ".", ".", "B"],
                [".", ".", "*", ".", "."],
                ["C", ".", ".", "D"],
                ["C", "C", ".", "D", "D"]
            ]
        }

    Even rows (0, 2, 4...) are wide, odd rows (1, 3...) are narrow (offset right).
    Each cell is a single character. Convention: '.' = unclaimed, '*' = contested.
    """

    def _build_lines(self) -> List[str]:
        cells = self.props.get('cells', [])
        if not cells:
            return []
        lines: List[str] = []
        n_rows = len(cells)

        for ri in range(n_rows):
            row = cells[ri]
            n = len(row)
            is_wide = (ri % 2 == 0)

            if is_wide:
                # Top edge (only for first row — later wide rows get top from previous narrow's bottom)
                if ri == 0:
                    lines.append(' ' + ' '.join(['/ \\'] * n))
                # Content
                lines.append(''.join('| ' + str(c) + ' ' for c in row) + '|')
                # Bottom edge
                lines.append(' ' + ' '.join(['\\ /'] * n))
            else:
                # Narrow row content (indented by 2)
                lines.append('  ' + ''.join('| ' + str(c) + ' ' for c in row) + '|')
                # Bottom edge — sized for the next wide row if it exists
                if ri + 1 < n_rows:
                    next_n = len(cells[ri + 1])
                    lines.append(' ' + ' '.join(['/ \\'] * next_n))
                else:
                    lines.append(' ' + ' '.join(['/ \\'] * n))

        return lines

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        self._lines = self._build_lines()
        w = max((len(l) for l in self._lines), default=0)
        h = len(self._lines)
        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)

    def render(self, canvas: Canvas) -> None:
        x, y = self.rect.x, self.rect.y
        w = self.rect.w
        align = self.props.get('align', 'left')
        max_line_w = max((len(l) for l in self._lines), default=0)
        for i, line in enumerate(self._lines):
            if align == 'center' and w > max_line_w:
                offset = (w - max_line_w) // 2
            elif align == 'right' and w > max_line_w:
                offset = w - max_line_w
            else:
                offset = 0
            canvas.put_str(x + offset, y + i, line)


# ═══════════════════════════════════════════════
# Transition (scene divider)
# ═══════════════════════════════════════════════

TRANSITION_STYLES: Dict[str, str] = {
    'hard_cut': '═',
    'fade': '─ ',
    'dissolve': '░▒▓█▓▒░',
    'fast_forward': '>>> ',
    'flashback': '<<< ',
    'dream': '~ ',
    'temporal_skip': '▼ ',
}


class TransitionElement(Element):
    """Scene transition marker."""

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        label = self.props.get('label', self.props.get('text', ''))
        style = self.props.get('style', 'hard_cut')
        if label:
            w = str_width(label) + 6
        else:
            w = 10
        self._min_w, self._min_h = w, 1
        return (w, 1)

    def render(self, canvas: Canvas) -> None:
        x, y, w = self.rect.x, self.rect.y, self.rect.w
        label = self.props.get('label', self.props.get('text', ''))
        style = self.props.get('style', 'hard_cut')
        pattern = TRANSITION_STYLES.get(style, '═')

        if label:
            # Build: pattern + label + pattern
            left_len = 3
            left = (pattern * ((left_len // len(pattern)) + 1))[:left_len]
            right_len = max(w - left_len - str_width(label) - 2, 3)
            right = (pattern * ((right_len // len(pattern)) + 1))[:right_len]
            line = f"{left} {label} {right}"
            canvas.put_str(x, y, line[:w])
        else:
            full = (pattern * ((w // len(pattern)) + 1))[:w]
            canvas.put_str(x, y, full)


# ═══════════════════════════════════════════════
# Inventory (game state: item list)
# ═══════════════════════════════════════════════

class InventoryElement(Element):
    """Game-style inventory: Torch (3)  Key (1)"""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._lines: List[str] = []

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        items = self.props.get('items', [])
        cols = self.props.get('cols', 3)
        # Build item strings
        item_strs = []
        for item in items:
            if isinstance(item, dict):
                name = item.get('name', '')
                count = item.get('count', 1)
                item_strs.append(f"{name} ({count})")
            else:
                item_strs.append(str(item))

        # Arrange in rows
        self._lines = []
        for i in range(0, len(item_strs), cols):
            chunk = item_strs[i:i+cols]
            self._lines.append('    '.join(chunk))

        w = max((str_width(l) for l in self._lines), default=0)
        h = len(self._lines)
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        for i, line in enumerate(self._lines):
            if i >= self.rect.h:
                break
            canvas.put_str(self.rect.x, self.rect.y + i, line)


# ═══════════════════════════════════════════════
# Turn Log (game state: history)
# ═══════════════════════════════════════════════

class TurnLogElement(Element):
    """Append-only turn history display."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._display_lines: List[str] = []

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        entries = self.props.get('entries', [])
        show_last = self.props.get('show_last', len(entries))
        visible = entries[-show_last:] if show_last < len(entries) else entries
        self._display_lines = [str(e) for e in visible]
        w = max((str_width(l) for l in self._display_lines), default=0)
        h = len(self._display_lines)
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        for i, line in enumerate(self._display_lines):
            if i >= self.rect.h:
                break
            canvas.put_str(self.rect.x, self.rect.y + i, line)


# ═══════════════════════════════════════════════
# Status Panel (game state: composite)
# ═══════════════════════════════════════════════

class StatusPanelElement(Element):
    """Game-style status panel with bars and items. Wraps in a box."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._child_box: Optional[BoxElement] = None

    def _build(self) -> BoxElement:
        children = []
        # Bars
        for bar in self.props.get('bars', []):
            bar['type'] = 'bar'
            children.append(bar)
        # Separator if both bars and items
        if children and self.props.get('items'):
            children.append({"type": "separator"})
        # Inventory
        if self.props.get('items'):
            children.append({
                "type": "inventory",
                "items": self.props['items'],
                "cols": self.props.get('cols', 3)
            })
        # Turn log
        if self.props.get('entries'):
            children.append({"type": "separator", "title": "Log"})
            children.append({
                "type": "turn_log",
                "entries": self.props['entries'],
                "show_last": self.props.get('show_last', 5)
            })

        box_spec = {
            "type": "box",
            "title": self.props.get('title', 'Status'),
            "style": self.props.get('style', 'single'),
            "children": children
        }
        return build_element(box_spec)

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        self._child_box = self._build()
        w, h = self._child_box.measure(avail_w)
        self._min_w, self._min_h = w, h
        return (w, h)

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, w, h)
        if self._child_box:
            self._child_box.layout(x, y, w, h)

    def render(self, canvas: Canvas) -> None:
        if self._child_box:
            self._child_box.render(canvas)


# ═══════════════════════════════════════════════
# Minimap (compressed grid view)
# ═══════════════════════════════════════════════

class MinimapElement(Element):
    """2D grid map with single-char cells. For game maps, heatmaps, etc."""

    def __init__(self, props: Dict[str, Any]):
        super().__init__(props)
        self._rows: List[str] = []

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        cells = self.props.get('cells', [])
        self._rows = []
        for row in cells:
            if isinstance(row, str):
                self._rows.append(row)
            elif isinstance(row, list):
                self._rows.append(''.join(str(c) for c in row))
        w = max((str_width(r) for r in self._rows), default=0)
        h = len(self._rows)
        self._min_w, self._min_h = w, h
        return (w, h)

    def render(self, canvas: Canvas) -> None:
        for i, row in enumerate(self._rows):
            if i >= self.rect.h:
                break
            canvas.put_str(self.rect.x, self.rect.y + i, row)


# ═══════════════════════════════════════════════
# ASCII-Safe Mode (Unicode → ASCII substitution)
# ═══════════════════════════════════════════════

ASCII_SUBS: Dict[str, str] = {
    '─': '-', '━': '=', '│': '|', '┃': '|',
    '┌': '+', '┐': '+', '└': '+', '┘': '+',
    '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+',
    '╔': '+', '╗': '+', '╚': '+', '╝': '+',
    '╠': '+', '╣': '+', '╦': '+', '╩': '+', '╬': '+',
    '═': '=', '║': '|',
    '╭': '+', '╮': '+', '╰': '+', '╯': '+',
    '┏': '+', '┓': '+', '┗': '+', '┛': '+',
    '┣': '+', '┫': '+', '┳': '+', '┻': '+', '╋': '+',
    '►': '>', '◄': '<', '▲': '^', '▼': 'v',
    '→': '->', '←': '<-', '↑': '^', '↓': 'v',
    '⇒': '=>', '⇐': '<=',
    '●': '*', '○': 'o', '◆': '#',
    '█': '#', '▓': '#', '▒': '=', '░': '.',
    '╌': '-', '╎': '|', '┄': '-', '┊': '|',
}


def ascii_safe(text: str) -> str:
    """Convert Unicode art to ASCII-safe equivalent."""
    result = []
    for ch in text:
        result.append(ASCII_SUBS.get(ch, ch))
    return ''.join(result)


# ═══════════════════════════════════════════════
# SubpixelCanvas — Phase 4 (purely additive)
# ═══════════════════════════════════════════════
# New class, separate from Canvas. Operates at higher
# resolution (braille: 2x4 dots per cell, block: 2x2),
# converts to regular Canvas via .to_canvas().

# Braille: Unicode braille block U+2800-U+28FF
# Each character is a 2x4 dot matrix. Dot positions:
#   (0,0)=0x01  (1,0)=0x08
#   (0,1)=0x02  (1,1)=0x10
#   (0,2)=0x04  (1,2)=0x20
#   (0,3)=0x40  (1,3)=0x80

_BRAILLE_BASE = 0x2800
_BRAILLE_DOT_MAP = {
    (0, 0): 0x01, (1, 0): 0x08,
    (0, 1): 0x02, (1, 1): 0x10,
    (0, 2): 0x04, (1, 2): 0x20,
    (0, 3): 0x40, (1, 3): 0x80,
}

# Block: half-block characters for 2x2 subpixels per cell
# Top/bottom halves: ▀ (top), ▄ (bottom), █ (both), ' ' (none)
# Left/right halves: ▌ (left), ▐ (right), █ (both), ' ' (none)
# We use top/bottom encoding (most common):
#   (0,0)=top-left, (1,0)=top-right, (0,1)=bottom-left, (1,1)=bottom-right
# Each cell = 2 columns × 2 rows of subpixels, but rendered as one char.
# Encoding: 4 bits → 16 states.
_BLOCK_CHARS = {
    0b0000: ' ',   # nothing
    0b0001: '▘',   # top-left
    0b0010: '▝',   # top-right
    0b0011: '▀',   # top
    0b0100: '▖',   # bottom-left
    0b0101: '▌',   # left
    0b0110: '▞',   # diagonal
    0b0111: '▛',   # all but bottom-right
    0b1000: '▗',   # bottom-right
    0b1001: '▚',   # reverse diagonal
    0b1010: '▐',   # right
    0b1011: '▜',   # all but bottom-left
    0b1100: '▄',   # bottom
    0b1101: '▙',   # all but top-right
    0b1110: '▟',   # all but top-left
    0b1111: '█',   # full
}


class SubpixelCanvas:
    """High-resolution drawing surface. Converts to regular Canvas.

    ⚠️ Braille mode is TERMINAL ONLY — braille characters do NOT render
    at consistent widths in markdown viewers. Only use when explicitly
    requested, and only output to terminal (stdout).
    Block mode renders correctly everywhere.

    Modes:
        braille — 2x4 dots per terminal cell (w*2 × h*4 subpixels) ⚠️ terminal only
        block   — 2x2 dots per terminal cell (w*2 × h*2 subpixels) ✅ works everywhere

    w, h = terminal cell dimensions of the output.
    Draw at subpixel coordinates, then .to_canvas() packs into characters.
    """

    def __init__(self, w: int, h: int, mode: str = 'braille'):
        assert mode in ('braille', 'block'), f"Unknown mode: {mode}"
        self.mode = mode
        self.cell_w = w
        self.cell_h = h

        if mode == 'braille':
            self.sub_w = w * 2
            self.sub_h = h * 4
        else:  # block
            self.sub_w = w * 2
            self.sub_h = h * 2

        # Subpixel grid (True = dot on)
        self.dots: List[List[bool]] = [
            [False] * self.sub_w for _ in range(self.sub_h)
        ]

    def set(self, x: int, y: int, on: bool = True) -> None:
        """Set a single subpixel."""
        if 0 <= x < self.sub_w and 0 <= y < self.sub_h:
            self.dots[y][x] = on

    def clear(self, x: int, y: int) -> None:
        """Clear a single subpixel."""
        self.set(x, y, False)

    def line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Draw a line using Bresenham's algorithm."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x0: int, y0: int, x1: int, y1: int,
             fill: bool = False) -> None:
        """Draw a rectangle (outline or filled)."""
        if fill:
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for x in range(min(x0, x1), max(x0, x1) + 1):
                    self.set(x, y)
        else:
            self.line(x0, y0, x1, y0)  # top
            self.line(x0, y1, x1, y1)  # bottom
            self.line(x0, y0, x0, y1)  # left
            self.line(x1, y0, x1, y1)  # right

    def _aspect(self) -> float:
        """Aspect ratio correction factor for the current mode.
        Terminal chars are ~2:1 (height:width).
        Braille (2x4 dots): subpixels are ~square → 1.0
        Block (2x2 dots): subpixels are ~2:1 tall → 2.0
        """
        return 1.0 if self.mode == 'braille' else 2.0

    def circle(self, cx: int, cy: int, r: int, fill: bool = False) -> None:
        """Draw a visually-round circle with aspect ratio correction.
        Uses ellipse internally: rx = r * aspect, ry = r."""
        aspect = self._aspect()
        rx = int(r * aspect)
        ry = r
        self.ellipse(cx, cy, rx, ry, fill=fill)

    def ellipse(self, cx: int, cy: int, rx: int, ry: int,
                fill: bool = False) -> None:
        """Draw an ellipse (outline or filled) using midpoint algorithm."""
        if fill:
            for y in range(-ry, ry + 1):
                for x in range(-rx, rx + 1):
                    if rx > 0 and ry > 0:
                        if (x * x * ry * ry + y * y * rx * rx) <= rx * rx * ry * ry:
                            self.set(cx + x, cy + y)
        else:
            # Midpoint ellipse algorithm
            rx2 = rx * rx
            ry2 = ry * ry
            # Region 1
            x, y = 0, ry
            d1 = ry2 - rx2 * ry + 0.25 * rx2
            while ry2 * x <= rx2 * y:
                for sx, sy in [(x, y), (-x, y), (x, -y), (-x, -y)]:
                    self.set(cx + sx, cy + sy)
                x += 1
                if d1 < 0:
                    d1 += 2 * ry2 * x + ry2
                else:
                    y -= 1
                    d1 += 2 * ry2 * x - 2 * rx2 * y + ry2
            # Region 2
            d2 = ry2 * (x + 0.5) ** 2 + rx2 * (y - 1) ** 2 - rx2 * ry2
            while y >= 0:
                for sx, sy in [(x, y), (-x, y), (x, -y), (-x, -y)]:
                    self.set(cx + sx, cy + sy)
                y -= 1
                if d2 > 0:
                    d2 += rx2 - 2 * rx2 * y
                else:
                    x += 1
                    d2 += 2 * ry2 * x - 2 * rx2 * y + rx2

    def polygon(self, points: List[Tuple[int, int]]) -> None:
        """Draw a closed polygon by connecting consecutive points."""
        for i in range(len(points)):
            x0, y0 = points[i]
            x1, y1 = points[(i + 1) % len(points)]
            self.line(x0, y0, x1, y1)

    def text(self, x: int, y: int, s: str) -> None:
        """Plot text as dots using a 3x4 bitmap font.

        In braille mode, y is auto-snapped to the nearest cell boundary
        (multiple of 4) so letters always render unified — no visual gaps
        from cell boundary crossings. User can specify any y freely.
        """
        # 3x4 font — fits exactly in one braille cell (4 dots tall)
        _MINI_FONT = {
            '0': ['111','101','101','111'], '1': ['010','110','010','111'],
            '2': ['111','001','110','111'], '3': ['111','011','001','111'],
            '4': ['101','111','001','001'], '5': ['111','110','001','111'],
            '6': ['111','100','111','111'], '7': ['111','001','001','001'],
            '8': ['111','111','101','111'], '9': ['111','111','001','111'],
            'A': ['111','101','111','101'], 'B': ['110','111','101','110'],
            'C': ['111','100','100','111'], 'D': ['110','101','101','110'],
            'E': ['111','110','100','111'], 'F': ['111','110','100','100'],
            'G': ['111','100','101','111'], 'H': ['101','111','101','101'],
            'I': ['111','010','010','111'], 'J': ['011','001','101','111'],
            'K': ['101','110','110','101'], 'L': ['100','100','100','111'],
            'M': ['101','111','101','101'], 'N': ['101','111','111','101'],
            'O': ['111','101','101','111'], 'P': ['111','101','111','100'],
            'Q': ['111','101','111','001'], 'R': ['111','101','110','101'],
            'S': ['111','100','011','111'], 'T': ['111','010','010','010'],
            'U': ['101','101','101','111'], 'V': ['101','101','101','010'],
            'W': ['101','101','111','101'], 'X': ['101','010','010','101'],
            'Y': ['101','111','010','010'], 'Z': ['111','010','100','111'],
            ' ': ['000','000','000','000'], '.': ['000','000','000','010'],
            '-': ['000','111','000','000'], '+': ['010','111','010','000'],
            ':': ['000','010','000','010'], '/': ['001','010','010','100'],
            '!': ['010','010','000','010'], '?': ['111','010','000','010'],
        }
        # Auto-snap y to braille cell boundary in braille mode
        if self.mode == 'braille':
            y = round(y / 4) * 4
        cx = x
        for ch in s.upper():
            glyph = _MINI_FONT.get(ch)
            if glyph:
                for gy, row in enumerate(glyph):
                    for gx, bit in enumerate(row):
                        if bit == '1':
                            self.set(cx + gx, y + gy)
                cx += len(glyph[0]) + 1
            else:
                cx += 4

    def to_canvas(self) -> Canvas:
        """Pack subpixels into characters and return a regular Canvas."""
        canvas = Canvas(self.cell_w, self.cell_h)

        if self.mode == 'braille':
            for cy in range(self.cell_h):
                for cx in range(self.cell_w):
                    code = 0
                    for (dx, dy), bit in _BRAILLE_DOT_MAP.items():
                        sx = cx * 2 + dx
                        sy = cy * 4 + dy
                        if sx < self.sub_w and sy < self.sub_h and self.dots[sy][sx]:
                            code |= bit
                    if code > 0:
                        canvas.grid[cy][cx] = chr(_BRAILLE_BASE + code)

        elif self.mode == 'block':
            for cy in range(self.cell_h):
                for cx in range(self.cell_w):
                    bits = 0
                    # top-left = bit 0, top-right = bit 1
                    # bottom-left = bit 2, bottom-right = bit 3
                    for dx, dy, bit in [(0, 0, 0b0001), (1, 0, 0b0010),
                                        (0, 1, 0b0100), (1, 1, 0b1000)]:
                        sx = cx * 2 + dx
                        sy = cy * 2 + dy
                        if sx < self.sub_w and sy < self.sub_h and self.dots[sy][sx]:
                            bits |= bit
                    ch = _BLOCK_CHARS.get(bits, ' ')
                    if ch != ' ':
                        canvas.grid[cy][cx] = ch

        return canvas


class CanvasElement(Element):
    """Subpixel drawing canvas element (braille or block mode).

    ⚠️ Braille mode is TERMINAL ONLY — does NOT render correctly in
    markdown files. Only use when explicitly requested, output to terminal.
    Block mode works everywhere. All other element types work everywhere.

    Purely additive — renders to parent Canvas like any other element.

    JSON spec:
        {
            "type": "canvas",
            "mode": "braille" | "block",     # default: braille
            "w": 40,                          # terminal cell width
            "h": 10,                          # terminal cell height
            "draw": [                         # list of draw commands
                {"cmd": "line", "x0": 0, "y0": 0, "x1": 79, "y1": 39},
                {"cmd": "rect", "x0": 5, "y0": 5, "x1": 20, "y1": 15},
                {"cmd": "rect", "x0": 5, "y0": 5, "x1": 20, "y1": 15, "fill": True},
                {"cmd": "circle", "cx": 40, "cy": 20, "r": 10},
                {"cmd": "circle", "cx": 40, "cy": 20, "r": 10, "fill": True},
                {"cmd": "dot", "x": 10, "y": 10},
                {"cmd": "polygon", "points": [[0,0], [10,5], [5,10]]},
                {"cmd": "text", "x": 0, "y": 0, "text": "HI"}
            ]
        }

    Coordinates are in subpixel space:
        braille: w*2 × h*4 (e.g., 40 cells → 80×40 subpixels)
        block:   w*2 × h*2 (e.g., 40 cells → 80×20 subpixels)
    """

    def measure(self, avail_w: int = 0) -> Tuple[int, int]:
        w = self.props.get('w', 40)
        h = self.props.get('h', 10)
        self._min_w, self._min_h = w, h
        return w, h

    def layout(self, x: int, y: int, w: int, h: int) -> None:
        self.rect = Rect(x, y, self.props.get('w', 40), self.props.get('h', 10))

    def render(self, canvas: Canvas) -> None:
        mode = self.props.get('mode', 'braille')
        w = self.props.get('w', 40)
        h = self.props.get('h', 10)
        draw_cmds = self.props.get('draw', [])

        sub = SubpixelCanvas(w, h, mode)

        for cmd in draw_cmds:
            kind = cmd.get('cmd', '')
            if kind == 'dot':
                sub.set(cmd['x'], cmd['y'])
            elif kind == 'line':
                sub.line(cmd['x0'], cmd['y0'], cmd['x1'], cmd['y1'])
            elif kind == 'rect':
                sub.rect(cmd['x0'], cmd['y0'], cmd['x1'], cmd['y1'],
                         fill=cmd.get('fill', False))
            elif kind == 'circle':
                sub.circle(cmd['cx'], cmd['cy'], cmd['r'],
                           fill=cmd.get('fill', False))
            elif kind == 'polygon':
                sub.polygon([(p[0], p[1]) for p in cmd.get('points', [])])
            elif kind == 'text':
                sub.text(cmd['x'], cmd['y'], cmd.get('text', ''))

        # Convert subpixel canvas to characters and blit onto parent
        packed = sub.to_canvas()
        ox, oy = self.rect.x, self.rect.y
        for py in range(h):
            for px in range(w):
                ch = packed.grid[py][px]
                if ch != ' ':
                    canvas.put(ox + px, oy + py, ch)


# ═══════════════════════════════════════════════
# Validate — Phase 4 (purely additive, read-only)
# ═══════════════════════════════════════════════

def validate(canvas: Canvas) -> Dict[str, Any]:
    """Post-render structural validation. Read-only — does not modify canvas.

    Returns dict with:
        valid (bool): True if no issues found
        issues (list): List of issue descriptions
        stats (dict): Character census and metrics
    """
    issues: List[str] = []
    rendered = canvas.render()
    lines = rendered.split('\n')
    widths = [str_width(line) for line in lines if line.strip()]

    # --- Frame completeness ---
    box_openers = set('┌╔╭┏')
    box_closers = set('┘╝╯┛')
    opener_count = 0
    closer_count = 0
    for row in canvas.grid:
        for ch in row:
            if ch in box_openers:
                opener_count += 1
            elif ch in box_closers:
                closer_count += 1

    if opener_count != closer_count:
        issues.append(
            f"Frame mismatch: {opener_count} top-left corners vs "
            f"{closer_count} bottom-right corners"
        )

    # --- Overlap detection ---
    # Check for cells that were written multiple times with non-merge chars
    # (We can't retroactively detect this from the final grid, but we can
    #  flag suspicious patterns like text chars in border positions)

    # --- Character census ---
    census: Dict[str, int] = {}
    total = 0
    space_count = 0
    box_drawing = 0
    braille = 0
    block = 0

    for row in canvas.grid:
        for ch in row:
            if ch == '' or ch == ' ':
                space_count += 1
                continue
            total += 1
            census[ch] = census.get(ch, 0) + 1
            cp = ord(ch)
            if 0x2500 <= cp <= 0x257F:
                box_drawing += 1
            elif 0x2800 <= cp <= 0x28FF:
                braille += 1
            elif ch in '▀▄▌▐█▘▝▖▗▚▞▛▜▙▟':
                block += 1

    stats = {
        'total_chars': total,
        'space_chars': space_count,
        'box_drawing': box_drawing,
        'braille': braille,
        'block': block,
        'unique_chars': len(census),
        'lines': len(lines),
        'max_width': max(widths) if widths else 0,
        'frame_openers': opener_count,
        'frame_closers': closer_count,
    }

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'stats': stats,
    }


# ═══════════════════════════════════════════════
# Element Factory
# ═══════════════════════════════════════════════

def build_element(spec: Dict[str, Any]) -> Element:
    """Recursively build an element tree from a JSON spec."""
    t = spec.get('type', 'box')

    # Build children
    children: List[Element] = []
    if 'children' in spec:
        for child_spec in spec['children']:
            children.append(build_element(child_spec))

    if t in ('box', 'frame'):
        return BoxElement(spec, children)
    elif t == 'row':
        return RowElement(spec, children)
    elif t == 'stack':
        return StackElement(spec, children)
    elif t == 'label':
        return LabelElement(spec)
    elif t == 'spacer':
        return SpacerElement(spec)
    elif t == 'separator':
        return SeparatorElement(spec)
    elif t == 'legend':
        return LegendElement(spec)
    elif t == 'grid':
        return GridElement(spec)
    elif t == 'bar':
        return BarElement(spec)
    elif t == 'line':
        return LineElement(spec)
    elif t == 'arrow':
        return ArrowElement(spec)
    elif t == 'node':
        return NodeElement(spec)
    elif t == 'connector':
        return ConnectorElement(spec)
    elif t == 'fill':
        return FillElement(spec)
    elif t == 'group':
        return GroupElement(spec, children)
    elif t == 'board':
        return BoardElement(spec, children)
    elif t == 'hexgrid':
        return HexGridElement(spec)
    elif t == 'transition':
        return TransitionElement(spec)
    elif t == 'inventory':
        return InventoryElement(spec)
    elif t == 'turn_log':
        return TurnLogElement(spec)
    elif t == 'status_panel':
        return StatusPanelElement(spec)
    elif t == 'minimap':
        return MinimapElement(spec)
    elif t == 'canvas':
        return CanvasElement(spec)
    else:
        spec.setdefault('text', f'[unknown: {t}]')
        return LabelElement(spec)


# ═══════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════

def render_json(spec: Dict[str, Any]) -> str:
    """Full pipeline: JSON → element tree → measure → layout → render → string."""
    root = build_element(spec)

    avail_w = spec.get('width', 0)
    if avail_w == 'auto' or not isinstance(avail_w, (int, float)):
        avail_w = 0

    # Pass 1: Measure
    min_w, min_h = root.measure(int(avail_w))

    # Final dimensions
    final_w = int(avail_w) if avail_w > 0 else min_w
    final_h = min_h

    # Pass 2: Layout
    root.layout(0, 0, final_w, final_h)

    # Pass 3: Render
    canvas = Canvas(final_w, final_h)
    root.render(canvas)

    return canvas.render()


# ═══════════════════════════════════════════════
# Examples
# ═══════════════════════════════════════════════

EXAMPLES = {
    "simple": {
        "desc": "Simple box with title and content",
        "spec": {
            "type": "box", "title": "Hello", "content": "World"
        }
    },
    "multiline": {
        "desc": "Box with multi-line content",
        "spec": {
            "type": "box", "title": "Note",
            "content": "First line\nSecond line\nThird line"
        }
    },
    "row": {
        "desc": "Two boxes side by side in a frame",
        "spec": {
            "type": "box", "title": "LAYOUT", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {"type": "box", "title": "Left", "content": "Side A"},
                        {"type": "box", "title": "Right", "content": "Side B"}
                    ]
                }
            ]
        }
    },
    "hierarchy": {
        "desc": "Border hierarchy: double > single > rounded",
        "spec": {
            "type": "box", "title": "TRUST BOUNDARY", "style": "double",
            "children": [
                {
                    "type": "box", "title": "Scope", "style": "single",
                    "children": [
                        {
                            "type": "box", "title": "Category", "style": "rounded",
                            "content": "Inner content"
                        }
                    ]
                }
            ]
        }
    },
    "dashboard": {
        "desc": "Multi-section dashboard with status bars",
        "spec": {
            "type": "box", "title": "SYSTEM STATUS", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {"type": "box", "title": "CPU", "content": "45%"},
                        {"type": "box", "title": "MEM", "content": "8.2 GB"},
                        {"type": "box", "title": "DISK", "content": "234 GB"}
                    ]
                },
                {"type": "separator", "title": "Health"},
                {"type": "bar", "label": "CPU", "value": 45, "max": 100, "width": 20},
                {"type": "bar", "label": "MEM", "value": 82, "max": 100, "width": 20},
                {"type": "separator", "title": "Logs"},
                {"type": "label", "text": "All systems nominal.\nNo errors detected."}
            ]
        }
    },
    "legend": {
        "desc": "Box with formatted legend",
        "spec": {
            "type": "box", "title": "SYMBOLS", "style": "rounded",
            "children": [
                {
                    "type": "legend",
                    "entries": {
                        "●": "Active node",
                        "○": "Inactive node",
                        "◆": "Critical path",
                        "═": "Strong connection"
                    }
                }
            ]
        }
    },
    "nodes": {
        "desc": "Semantic node types",
        "spec": {
            "type": "box", "title": "NODE TYPES", "style": "double",
            "children": [
                {
                    "type": "stack", "gap": 1,
                    "children": [
                        {"type": "node", "name": "Server", "nodeType": "entity"},
                        {"type": "node", "name": "Handle Request", "nodeType": "process"},
                        {"type": "node", "name": "Auth Check", "nodeType": "decision"},
                        {"type": "node", "name": "HTTP/443", "nodeType": "io"},
                        {"type": "node", "name": "See Also", "nodeType": "reference"},
                        {"type": "node", "name": "Trust Zone", "nodeType": "critical"},
                        {"type": "node", "name": "API Running", "nodeType": "active"},
                        {"type": "node", "name": "Cache Cold", "nodeType": "inactive"},
                    ]
                }
            ]
        }
    },
    "diagram": {
        "desc": "Flow diagram with lines and arrows",
        "spec": {
            "type": "box", "title": "DATA FLOW", "style": "double", "pad": 0,
            "children": [
                {
                    "type": "grid",
                    "lines": [
                        "  [Client] ──────► (Gateway) ──────► [Server]  ",
                        "                      │                  │     ",
                        "                      │                  │     ",
                        "                      ▼                  ▼     ",
                        "                   {Auth?}          [Database] ",
                        "                    │  │                       ",
                        "                  ✓ │  │ ✗                     ",
                        "                    ▼  ▼                       ",
                        "               [Allow] [Deny]                  "
                    ]
                }
            ]
        }
    },
    "game": {
        "desc": "RPG-style status panel with bars, inventory, and log",
        "spec": {
            "type": "status_panel",
            "title": "PLAYER STATUS",
            "bars": [
                {"label": "HP ", "value": 73, "max": 100, "width": 15},
                {"label": "MP ", "value": 20, "max": 50, "width": 15},
                {"label": "EXP", "value": 450, "max": 1000, "width": 15}
            ],
            "items": [
                {"name": "Torch", "count": 3},
                {"name": "Key", "count": 1},
                {"name": "Potion", "count": 5},
                {"name": "Map", "count": 1},
                {"name": "Rope", "count": 2}
            ],
            "cols": 3,
            "entries": [
                "T1: Entered dungeon",
                "T2: Found torch",
                "T3: Defeated goblin (+50 EXP)",
                "T4: Unlocked chest",
                "T5: Moved east"
            ],
            "show_last": 3
        }
    },
    "minimap": {
        "desc": "Compressed dungeon minimap",
        "spec": {
            "type": "box", "title": "DUNGEON MAP", "style": "double",
            "children": [
                {
                    "type": "minimap",
                    "cells": [
                        "███░░░███",
                        "█·····░░█",
                        "█·█████·█",
                        "█·····●·█",
                        "█·███·█·█",
                        "█·░░░·█·█",
                        "█·····█·█",
                        "███████·█",
                        "░░░░░░·░░"
                    ]
                },
                {"type": "separator", "title": "Legend"},
                {
                    "type": "legend",
                    "entries": {
                        "●": "You are here",
                        "█": "Wall",
                        "·": "Path",
                        "░": "Unexplored"
                    }
                }
            ]
        }
    },
    "fills": {
        "desc": "Fill patterns and gradients",
        "spec": {
            "type": "box", "title": "PATTERNS", "style": "single",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "box", "title": "Light", "pad": 0,
                            "children": [{"type": "fill", "char": "░", "w": 8, "h": 3}]
                        },
                        {
                            "type": "box", "title": "Medium", "pad": 0,
                            "children": [{"type": "fill", "char": "▒", "w": 8, "h": 3}]
                        },
                        {
                            "type": "box", "title": "Dense", "pad": 0,
                            "children": [{"type": "fill", "char": "▓", "w": 8, "h": 3}]
                        },
                        {
                            "type": "box", "title": "Gradient", "pad": 0,
                            "children": [{"type": "fill", "chars": " ░▒▓█", "gradient": True, "w": 12, "h": 3}]
                        }
                    ]
                }
            ]
        }
    },
    "braille": {
        "desc": "Braille subpixel canvas — shapes at 2x4 dot resolution",
        "spec": {
            "type": "box", "title": "BRAILLE CANVAS", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "box", "title": "Circle", "style": "single", "pad": 0,
                            "children": [{
                                "type": "canvas", "mode": "braille", "w": 20, "h": 10,
                                "draw": [
                                    {"cmd": "circle", "cx": 20, "cy": 20, "r": 16}
                                ]
                            }]
                        },
                        {
                            "type": "box", "title": "Square", "style": "single", "pad": 0,
                            "children": [{
                                "type": "canvas", "mode": "braille", "w": 20, "h": 10,
                                "draw": [
                                    {"cmd": "rect", "x0": 5, "y0": 5, "x1": 35, "y1": 35}
                                ]
                            }]
                        },
                        {
                            "type": "box", "title": "Lines", "style": "single", "pad": 0,
                            "children": [{
                                "type": "canvas", "mode": "braille", "w": 20, "h": 10,
                                "draw": [
                                    {"cmd": "line", "x0": 0, "y0": 0, "x1": 39, "y1": 39},
                                    {"cmd": "line", "x0": 39, "y0": 0, "x1": 0, "y1": 39},
                                    {"cmd": "line", "x0": 20, "y0": 0, "x1": 20, "y1": 39},
                                    {"cmd": "line", "x0": 0, "y0": 20, "x1": 39, "y1": 20}
                                ]
                            }]
                        },
                        {
                            "type": "box", "title": "Text", "style": "single", "pad": 0,
                            "children": [{
                                "type": "canvas", "mode": "braille", "w": 20, "h": 5,
                                "draw": [
                                    {"cmd": "text", "x": 2, "y": 0, "text": "HELLO"},
                                    {"cmd": "text", "x": 2, "y": 8, "text": "WORLD"}
                                ]
                            }]
                        }
                    ]
                }
            ]
        }
    },
    "blocks": {
        "desc": "Block subpixel canvas — shapes at 2x2 resolution",
        "spec": {
            "type": "box", "title": "BLOCK CANVAS", "style": "double",
            "children": [{
                "type": "canvas", "mode": "block", "w": 70, "h": 12,
                "draw": [
                    {"cmd": "circle", "cx": 22, "cy": 12, "r": 10, "fill": True},
                    {"cmd": "rect", "x0": 50, "y0": 2, "x1": 90, "y1": 22},
                    {"cmd": "circle", "cx": 118, "cy": 12, "r": 10},
                    {"cmd": "line", "x0": 42, "y0": 12, "x1": 48, "y1": 12},
                    {"cmd": "line", "x0": 92, "y0": 12, "x1": 98, "y1": 12}
                ]
            }]
        }
    },
    "hexgrid": {
        "desc": "Hex territory map — strategy board with factions",
        "spec": {
            "type": "box", "title": "Territory Wars ── Turn 12", "style": "single",
            "children": [
                {
                    "type": "hexgrid", "align": "center",
                    "cells": [
                        ["A", "A", ".", "B", "B"],
                        ["A", ".", ".", "B"],
                        [".", ".", "*", ".", "."],
                        ["C", ".", ".", "D"],
                        ["C", "C", ".", "D", "D"]
                    ]
                },
                {"type": "separator"},
                {"type": "label", "text": "A=Crown(7)  B=Guild(5)  C=Order(5)  D=Pact(3)", "align": "center"},
                {"type": "label", "text": "* = Contested    . = Unclaimed", "align": "center"},
                {"type": "separator"},
                {"type": "label", "text": "Scores:  A:42    B:31    C:28    D:19", "align": "center"},
                {"type": "spacer", "h": 1},
                {"type": "label", "text": "> Choose territory to claim:"}
            ]
        }
    },
    "holographic": {
        "desc": "Holographic projection — self-similar structure at multiple scales",
        "spec": {
            "type": "box", "title": "Holographic: Epistemology Space", "style": "single",
            "children": [
                {
                    "type": "box", "style": "double",
                    "children": [
                        {"type": "label", "text": "MACRO VIEW", "align": "center"},
                        {"type": "spacer", "h": 1},
                        {
                            "type": "board", "border": False, "w": 38, "h": 7, "pad": 0,
                            "children": [
                                {"type": "label", "text": "R ◆ ═════════════════ ■ E", "x": 3, "y": 0},
                                {"type": "label", "text": "\\", "x": 6, "y": 1},
                                {"type": "label", "text": "/", "x": 24, "y": 1},
                                {"type": "label", "text": "\\", "x": 7, "y": 2},
                                {"type": "label", "text": "● P", "x": 14, "y": 2},
                                {"type": "label", "text": "/", "x": 23, "y": 2},
                                {"type": "label", "text": "\\", "x": 8, "y": 3},
                                {"type": "label", "text": "|", "x": 14, "y": 3},
                                {"type": "label", "text": "/", "x": 22, "y": 3},
                                {"type": "label", "text": "\\", "x": 9, "y": 4},
                                {"type": "label", "text": "|", "x": 14, "y": 4},
                                {"type": "label", "text": "/", "x": 21, "y": 4},
                                {"type": "label", "text": "S ▫ ─ ─ ─ ─ ▪ D", "x": 8, "y": 5}
                            ]
                        },
                        {"type": "spacer", "h": 1},
                        {"type": "separator", "title": "MESO: Entangled Pairs"},
                        {"type": "label", "text": "◆ ═══ ■   mirror      ▫ ─ ─ ▪   inverse"},
                        {"type": "label", "text": "R     E   (high)     S     D   (low)"},
                        {"type": "label", "text": "● P   pragmatism (mediator, center)"},
                        {"type": "separator", "title": "MICRO: Internal Structure"},
                        {"type": "label", "text": "◆ Rationalism:  reason ══ logic ══ system"},
                        {"type": "label", "text": "■ Empiricism:   observe -- test -- measure"},
                        {"type": "label", "text": "(internal structure echoes the macro pattern)"}
                    ]
                },
                {"type": "spacer", "h": 1},
                {"type": "label", "text": "Scale: MACRO = full space, MESO = entangled pair,"},
                {"type": "label", "text": "       MICRO = internal entity structure"},
                {"type": "label", "text": "Self-similarity: entanglement pattern repeats at all scales"}
            ]
        }
    },
    "orthographic": {
        "desc": "Orthographic projection — 2D scatter plot with axes, data points, and connections",
        "spec": {
            "type": "box", "title": "Orthographic: d1 x d2 (d3 collapsed)", "style": "single",
            "children": [
                {
                    "type": "board", "border": False, "w": 56, "h": 15, "pad": 0,
                    "children": [
                        {"type": "label", "text": "d2 ▲", "x": 5, "y": 0},
                        {"type": "label", "text": "│", "x": 8, "y": 1},
                        {"type": "label", "text": "1.0 │          ◆ R", "x": 4, "y": 2},
                        {"type": "label", "text": "│         /", "x": 8, "y": 3},
                        {"type": "label", "text": "│        /", "x": 8, "y": 4},
                        {"type": "label", "text": "0.5 │       ●══════════ P", "x": 4, "y": 5},
                        {"type": "label", "text": "│      /", "x": 8, "y": 6},
                        {"type": "label", "text": "│     /", "x": 8, "y": 7},
                        {"type": "label", "text": "0.3 │    ■ E", "x": 4, "y": 8},
                        {"type": "label", "text": "│     \\", "x": 8, "y": 9},
                        {"type": "label", "text": "│      \\", "x": 8, "y": 10},
                        {"type": "label", "text": "0.0 │       ▪ D ─ ─ ─ ─ ─ ▫ S", "x": 4, "y": 11},
                        {"type": "label", "text": "│", "x": 8, "y": 12},
                        {"type": "label", "text": "└──┬──┬──┬──┬──┬──┬───► d1", "x": 8, "y": 13},
                        {"type": "label", "text": "1  2  3  4  5  6  7", "x": 12, "y": 14}
                    ]
                },
                {"type": "separator", "title": "Legend"},
                {"type": "label", "text": "◆ R  Rationalism          ■ E  Empiricism"},
                {"type": "label", "text": "● P  Pragmatism           ▪ D  Dialectics"},
                {"type": "label", "text": "▫ S  Skepticism"},
                {"type": "separator", "title": "Connections"},
                {"type": "label", "text": "══  entanglement (mirror)    high mutual dependence"},
                {"type": "label", "text": "──  entanglement (inverse)   oppositional pairing"},
                {"type": "label", "text": "/\\  diagonal (proximity)     bridging relationship"},
                {"type": "separator", "title": "Axes"},
                {"type": "label", "text": "d1 = structural complexity   (1 simple → 7 elaborate)"},
                {"type": "label", "text": "d2 = epistemic confidence    (0.0 doubt → 1.0 certainty)"},
                {"type": "label", "text": "d3 = time (collapsed)        frozen at t=0; see temporal"},
                {"type": "label", "text": "                             projection for d3 evolution"}
            ]
        }
    },
    "architecture": {
        "desc": "System architecture — nested boxes with directional arrows between components",
        "spec": {
            "type": "box", "title": "System Architecture", "style": "single",
            "children": [
                {
                    "type": "board", "border": False, "w": 54, "h": 12, "pad": 0,
                    "children": [
                        {
                            "type": "board", "title": "Core", "style": "double",
                            "x": 0, "y": 0, "w": 24, "h": 12,
                            "children": [
                                {
                                    "type": "box", "title": "Module A", "style": "single",
                                    "x": 2, "y": 0, "pad": 0,
                                    "content": ["func1()", "func2()"]
                                },
                                {"type": "label", "text": "│", "x": 8, "y": 4},
                                {"type": "label", "text": "▼", "x": 8, "y": 5},
                                {
                                    "type": "box", "title": "Module B", "style": "single",
                                    "x": 2, "y": 6, "pad": 0,
                                    "content": ["process()"]
                                }
                            ]
                        },
                        {"type": "label", "text": "──────►", "x": 24, "y": 2},
                        {
                            "type": "box", "title": "External", "style": "single",
                            "x": 32, "y": 0, "pad": 0,
                            "content": ["API", "Gateway"]
                        },
                        {"type": "label", "text": "▲", "x": 38, "y": 5},
                        {"type": "label", "text": "│", "x": 38, "y": 6},
                        {"type": "label", "text": "◄──────", "x": 24, "y": 8},
                        {
                            "type": "box", "title": "Auth", "style": "single",
                            "x": 32, "y": 7, "pad": 0,
                            "content": ["Token"]
                        },
                    ]
                },
                {"type": "separator", "title": "Legend"},
                {"type": "label", "text": "══ core boundary   ──► data flow"},
                {"type": "label", "text": "◄── auth flow      ── internal link"}
            ]
        }
    },
    "celestial": {
        "desc": "Complex artistic piece — observatory with star map, catalog, log, and equipment",
        "spec": {
            "type": "box", "title": "The Celestial Engine", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "board", "title": "Star Map", "style": "single",
                            "w": 36, "h": 13, "pad": 0,
                            "children": [
                                {"type": "label", "text": "·", "x": 4, "y": 0},
                                {"type": "label", "text": "✦", "x": 9, "y": 0},
                                {"type": "label", "text": "·", "x": 14, "y": 0},
                                {"type": "label", "text": "★", "x": 24, "y": 0},
                                {"type": "label", "text": "·", "x": 31, "y": 0},
                                {"type": "label", "text": "\\", "x": 8, "y": 1},
                                {"type": "label", "text": "|", "x": 10, "y": 1},
                                {"type": "label", "text": "/", "x": 12, "y": 1},
                                {"type": "label", "text": "·───◆───·", "x": 4, "y": 2},
                                {"type": "label", "text": "·", "x": 20, "y": 2},
                                {"type": "label", "text": "·", "x": 28, "y": 2},
                                {"type": "label", "text": "/", "x": 8, "y": 3},
                                {"type": "label", "text": "|", "x": 10, "y": 3},
                                {"type": "label", "text": "\\", "x": 12, "y": 3},
                                {"type": "label", "text": "·", "x": 4, "y": 4},
                                {"type": "label", "text": "✦", "x": 11, "y": 4},
                                {"type": "label", "text": "·", "x": 18, "y": 4},
                                {"type": "label", "text": "★", "x": 26, "y": 4},
                                {"type": "label", "text": "·", "x": 33, "y": 4},
                                {"type": "label", "text": "·", "x": 7, "y": 6},
                                {"type": "label", "text": "·", "x": 15, "y": 6},
                                {"type": "label", "text": "✦", "x": 22, "y": 6},
                                {"type": "label", "text": "·", "x": 30, "y": 6},
                                {"type": "label", "text": "═══ constellation", "x": 1, "y": 8},
                                {"type": "label", "text": "─ ─ hypothesized", "x": 1, "y": 9},
                                {"type": "label", "text": "◆ nexus  ✦ bright  ★ variable", "x": 1, "y": 10}
                            ]
                        },
                        {
                            "type": "box", "title": "Observatory", "style": "single",
                            "children": [
                                {"type": "label", "text": "◆ Polaris    [ACTIVE]"},
                                {"type": "label", "text": "◇ Vega       [LOCKED]"},
                                {"type": "label", "text": "◆ Sirius     [ACTIVE]"},
                                {"type": "label", "text": "◇ Rigel      [LOCKED]"},
                                {"type": "label", "text": "◇ Deneb      [LOCKED]"},
                                {"type": "separator", "title": "Alignment"},
                                {"type": "bar", "value": 78, "max": 100, "width": 20, "label": "Lock"},
                                {"type": "spacer", "h": 1},
                                {"type": "separator", "title": "Conditions"},
                                {"type": "label", "text": "Seeing:  excellent"},
                                {"type": "label", "text": "Phase:   new moon"},
                                {"type": "label", "text": "Azimuth: 47.3°"}
                            ]
                        }
                    ]
                },
                {"type": "separator", "title": "Celestial Log"},
                {
                    "type": "turn_log", "pad": 0,
                    "entries": [
                        "T1: Calibrated primary lens — focus locked",
                        "T2: Polaris acquired — magnitude 1.98, class F7",
                        "T3: Constellation URSA mapped (5 stars, 4 links)",
                        "T4: Sirius acquired — magnitude -1.46, class A1",
                        "T5: Hypothesized link: Polaris ─ ─ Vega (awaiting lock)"
                    ]
                },
                {"type": "separator", "title": "Equipment"},
                {"type": "bar", "value": 92, "max": 100, "width": 40, "label": "Lens"},
                {"type": "bar", "value": 61, "max": 100, "width": 40, "label": "Power"},
                {"type": "bar", "value": 100, "max": 100, "width": 40, "label": "Focus"},
                {"type": "bar", "value": 34, "max": 100, "width": 40, "label": "Coolant"}
            ]
        }
    },
    "watcher": {
        "desc": "The Eternal Watcher — a celestial god gazing down upon a sea of stars",
        "spec": {
            "type": "box", "title": "The Eternal Watcher", "style": "double",
            "children": [
                {
                    "type": "board", "border": False, "w": 60, "h": 28, "pad": 0,
                    "children": [
                        {"type": "label", "text": "·  ✧  ·", "x": 25, "y": 0},
                        {"type": "label", "text": "✧ ◆◆◆ ✧", "x": 24, "y": 1},
                        {"type": "label", "text": "╭───────╮", "x": 24, "y": 2},
                        {"type": "label", "text": "│ ◉   ◉ │", "x": 24, "y": 3},
                        {"type": "label", "text": "│   ▽   │", "x": 24, "y": 4},
                        {"type": "label", "text": "╰───┬───╯", "x": 24, "y": 5},
                        {"type": "label", "text": "/    │    \\", "x": 23, "y": 6},
                        {"type": "label", "text": "/     │     \\", "x": 22, "y": 7},
                        {"type": "label", "text": "/      │      \\", "x": 21, "y": 8},
                        {"type": "label", "text": "/  ░░░░░│░░░░░  \\", "x": 20, "y": 9},
                        {"type": "label", "text": "/  ░░░░░░│░░░░░░  \\", "x": 19, "y": 10},
                        {"type": "label", "text": "/  ░░░░░░░│░░░░░░░  \\", "x": 18, "y": 11},
                        {"type": "label", "text": "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─", "x": 11, "y": 12},
                        {"type": "label", "text": "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░", "x": 12, "y": 13},
                        {"type": "label", "text": "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░", "x": 11, "y": 14},
                        {"type": "label", "text": "·  ✦  ·  ★  ·  ·  ◆  ·  ✦  ·  ★  ·  ✦  ·", "x": 8, "y": 15},
                        {"type": "label", "text": "✧  ·  ·  ✦  ·  ★  ·  ·  ✦  ·  ·  ★  ·  ·  ✧", "x": 6, "y": 16},
                        {"type": "label", "text": "★  ·  ✦  ·  ·  ✧  ·  ★  ·  ✦  ·  ·  ★", "x": 10, "y": 17},
                        {"type": "label", "text": "·  ✦  ·  ·  ★  ·  ✦  ·  ◆  ·  ·  ★  ·  ✦", "x": 7, "y": 18},
                        {"type": "label", "text": "·  ·  ★  ·  ✦  ·  ·  ★  ·  ✦  ·  ·  ✧", "x": 9, "y": 19},
                        {"type": "label", "text": "✦  ·  ·  ✧  ·  ·  ✦  ·  ★  ·  ·  ✦", "x": 11, "y": 20},
                        {"type": "label", "text": "·  ★  ·  ·  ✦  ·  ·  ✧  ·  ·  ★", "x": 13, "y": 21},
                        {"type": "label", "text": "✧  ·  ✦  ·  ·  ★  ·  ·  ✦", "x": 16, "y": 22},
                        {"type": "label", "text": "·  ·  ★  ·  ✦  ·  ·", "x": 19, "y": 23},
                        {"type": "label", "text": "✦  ·  ·  ✧", "x": 23, "y": 24},
                        {"type": "label", "text": "·  ★", "x": 27, "y": 25},
                        {"type": "label", "text": "✧", "x": 29, "y": 26}
                    ]
                }
            ]
        }
    },
    "board": {
        "desc": "Freeform board — absolute positioning for maps and spatial layouts",
        "spec": {
            "type": "board", "title": "The Forgotten Shore ── Turn 8",
            "style": "single", "w": 65, "h": 28,
            "children": [
                {"type": "label", "text": "~~~~~~~~~~~~~", "x": 18, "y": 1},
                {"type": "label", "text": "~~~~~ OCEAN ~~~~~", "x": 16, "y": 2},
                {"type": "label", "text": "~~~~~~~~~~~~~", "x": 18, "y": 3},
                {"type": "label", "text": "──────────────────────────── SHORE ─────────", "x": 6, "y": 5},
                {"type": "label", "text": ".  .  .  .", "x": 2, "y": 7},
                {"type": "label", "text": ". DUNES .  .  .", "x": 1, "y": 8},
                {"type": "label", "text": ".  @  .  .  .", "x": 2, "y": 9},
                {"type": "label", "text": ".  .  .  .  .", "x": 1, "y": 10},
                {"type": "box", "title": "Shipwreck", "style": "single", "x": 19, "y": 7, "pad": 0,
                    "content": ["  ▓▓ hull ", "  ☆ cargo"]},
                {"type": "label", "text": ".  .  .", "x": 37, "y": 7},
                {"type": "label", "text": ". ROCKS .", "x": 36, "y": 8},
                {"type": "label", "text": ".  .  .", "x": 38, "y": 9},
                {"type": "label", "text": ".  .", "x": 38, "y": 10},
                {"type": "label", "text": "§ hermit", "x": 37, "y": 12},
                {"type": "box", "title": "Cave", "style": "single", "x": 1, "y": 14, "pad": 0,
                    "content": [" ▓▓▓▓▓▓", " ▓????▓"]},
                {"type": "label", "text": "PATH ═══════════════════════ [Village -->]", "x": 14, "y": 16},
                {"type": "bar", "value": 100, "max": 100, "width": 20, "x": 0, "y": 20,
                    "label": "HP"},
                {"type": "label", "text": "Items: rope, flint", "x": 24, "y": 20},
                {"type": "label", "text": "Mood: curious", "x": 0, "y": 21},
                {"type": "label", "text": "Known: shipwreck(seen), cave(unseen)", "x": 24, "y": 21},
                {"type": "label", "text": "> Explore where?", "x": 0, "y": 23}
            ]
        }
    },
    "complex": {
        "desc": "Complex nested layout",
        "spec": {
            "type": "box", "title": "ARCHITECTURE", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "box", "title": "Frontend", "style": "single",
                            "children": [
                                {"type": "label", "text": "React App"},
                                {"type": "separator"},
                                {"type": "label", "text": "Port 3000"}
                            ]
                        },
                        {
                            "type": "box", "title": "Backend", "style": "single",
                            "children": [
                                {"type": "label", "text": "FastAPI"},
                                {"type": "separator"},
                                {"type": "label", "text": "Port 8000"}
                            ]
                        },
                        {
                            "type": "box", "title": "Database", "style": "single",
                            "children": [
                                {"type": "label", "text": "PostgreSQL"},
                                {"type": "separator"},
                                {"type": "label", "text": "Port 5432"}
                            ]
                        }
                    ]
                },
                {"type": "separator", "title": "Status"},
                {"type": "label", "text": "All services running", "align": "center"}
            ]
        }
    },
    "alchemist": {
        "desc": "The Alchemist's Laboratory — mystical workspace with apparatus, runes, and atmospheric gradients",
        "spec": {
            "type": "box", "title": "⚗ The Alchemist's Laboratory ⚗", "style": "double",
            "children": [
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "box", "title": "Apparatus", "style": "single", "w": 30,
                            "children": [
                                {
                                    "type": "board", "border": False, "w": 28, "h": 13, "pad": 0,
                                    "children": [
                                        {"type": "label", "text": "☽", "x": 2, "y": 0},
                                        {"type": "label", "text": "★", "x": 13, "y": 0},
                                        {"type": "label", "text": "☾", "x": 24, "y": 0},
                                        {"type": "label", "text": "┌─────┐", "x": 10, "y": 1},
                                        {"type": "label", "text": "│ ∿∿∿ │", "x": 10, "y": 2},
                                        {"type": "label", "text": "│ ∿∿∿ │", "x": 10, "y": 3},
                                        {"type": "label", "text": "└──┬──┘", "x": 10, "y": 4},
                                        {"type": "label", "text": "│", "x": 13, "y": 5},
                                        {"type": "label", "text": "│", "x": 13, "y": 6},
                                        {"type": "label", "text": "╱──╲", "x": 20, "y": 2},
                                        {"type": "label", "text": "╲──╱", "x": 20, "y": 3},
                                        {"type": "label", "text": "🜂", "x": 21, "y": 5},
                                        {"type": "label", "text": "╭─────┴─────╮", "x": 7, "y": 7},
                                        {"type": "label", "text": "│ ░▒▓████▓▒░│", "x": 7, "y": 8},
                                        {"type": "label", "text": "│ ▒▓██████▓▒│", "x": 7, "y": 9},
                                        {"type": "label", "text": "│ ▓████████▓│", "x": 7, "y": 10},
                                        {"type": "label", "text": "☿", "x": 13, "y": 10},
                                        {"type": "label", "text": "╰───────────╯", "x": 7, "y": 11},
                                        {"type": "label", "text": "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁", "x": 6, "y": 12}
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "stack", "gap": 1,
                            "children": [
                                {
                                    "type": "box", "title": "ᚠ Runic Circle ᚠ", "style": "rounded", "w": 40,
                                    "children": [
                                        {
                                            "type": "board", "border": False, "w": 38, "h": 9, "pad": 0,
                                            "children": [
                                                {"type": "label", "text": "ᚦ", "x": 12, "y": 0},
                                                {"type": "label", "text": "ᚨ", "x": 18, "y": 0},
                                                {"type": "label", "text": "ᚱ", "x": 24, "y": 0},
                                                {"type": "label", "text": "╭───────────────────╮", "x": 8, "y": 1},
                                                {"type": "label", "text": "ᚲ", "x": 4, "y": 2},
                                                {"type": "label", "text": "│", "x": 8, "y": 2},
                                                {"type": "label", "text": "⛤", "x": 12, "y": 2},
                                                {"type": "label", "text": "∞", "x": 18, "y": 2},
                                                {"type": "label", "text": "⛤", "x": 24, "y": 2},
                                                {"type": "label", "text": "│", "x": 28, "y": 2},
                                                {"type": "label", "text": "ᚷ", "x": 32, "y": 2},
                                                {"type": "label", "text": "│", "x": 8, "y": 3},
                                                {"type": "label", "text": "│", "x": 28, "y": 3},
                                                {"type": "label", "text": "ᚹ", "x": 4, "y": 4},
                                                {"type": "label", "text": "│", "x": 8, "y": 4},
                                                {"type": "label", "text": "☥", "x": 12, "y": 4},
                                                {"type": "label", "text": "⊛", "x": 18, "y": 4},
                                                {"type": "label", "text": "☥", "x": 24, "y": 4},
                                                {"type": "label", "text": "│", "x": 28, "y": 4},
                                                {"type": "label", "text": "ᚺ", "x": 32, "y": 4},
                                                {"type": "label", "text": "│", "x": 8, "y": 5},
                                                {"type": "label", "text": "│", "x": 28, "y": 5},
                                                {"type": "label", "text": "ᚾ", "x": 4, "y": 6},
                                                {"type": "label", "text": "│", "x": 8, "y": 6},
                                                {"type": "label", "text": "⛤", "x": 12, "y": 6},
                                                {"type": "label", "text": "∞", "x": 18, "y": 6},
                                                {"type": "label", "text": "⛤", "x": 24, "y": 6},
                                                {"type": "label", "text": "│", "x": 28, "y": 6},
                                                {"type": "label", "text": "ᛁ", "x": 32, "y": 6},
                                                {"type": "label", "text": "╰───────────────────╯", "x": 8, "y": 7},
                                                {"type": "label", "text": "ᛃ", "x": 12, "y": 8},
                                                {"type": "label", "text": "ᛈ", "x": 18, "y": 8},
                                                {"type": "label", "text": "ᛇ", "x": 24, "y": 8}
                                            ]
                                        }
                                    ]
                                },
                                {
                                    "type": "box", "title": "Elemental Stores", "style": "dashed",
                                    "children": [
                                        {"type": "bar", "label": "🜁 Air  ", "value": 73, "max": 100, "width": 30, "filled": "▓", "empty": "░"},
                                        {"type": "bar", "label": "🜂 Fire ", "value": 91, "max": 100, "width": 30, "filled": "█", "empty": "░"},
                                        {"type": "bar", "label": "🜃 Earth", "value": 45, "max": 100, "width": 30, "filled": "▒", "empty": "░"},
                                        {"type": "bar", "label": "🜄 Water", "value": 62, "max": 100, "width": 30, "filled": "▓", "empty": "░"}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {"type": "separator", "title": "☿ Transmutation Log ☿"},
                {
                    "type": "row", "gap": 4,
                    "children": [
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "♄ Saturn", "val": "Lead → Gold  (Phase III)"},
                                {"key": "♃ Jupiter", "val": "Tin → Silver (Phase I)"},
                                {"key": "♂ Mars", "val": "Iron → Copper (Complete)"},
                                {"key": "☿ Mercury", "val": "Catalyst     (Active)"}
                            ]
                        },
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "Heat", "val": "▁▂▃▄▅▆▇█ MAX"},
                                {"key": "Moon", "val": "☽ ◐ ○ ◑ ☾"},
                                {"key": "Rune", "val": "ᚠ ᚢ ᚦ (wealth)"},
                                {"key": "Goal", "val": "Lead → Gold"}
                            ]
                        }
                    ]
                }
            ]
        }
    },
    "tarot": {
        "desc": "The Tower — a tarot card with mystical symbols, zodiac, and runic inscription",
        "spec": {
            "type": "box", "style": "double", "w": 48,
            "children": [
                {"type": "label", "text": "XVI", "align": "center"},
                {"type": "separator"},
                {
                    "type": "board", "border": False, "w": 44, "h": 22, "pad": 0,
                    "children": [
                        {"type": "label", "text": "✧  ☆    ★    ☆  ✧", "x": 13, "y": 0},
                        {"type": "label", "text": "⚡", "x": 10, "y": 1},
                        {"type": "label", "text": "⚡", "x": 32, "y": 1},
                        {"type": "label", "text": "╔═══╗", "x": 19, "y": 2},
                        {"type": "label", "text": "╔═══╬═══╗", "x": 17, "y": 3},
                        {"type": "label", "text": "║ ◆ ║ ◆ ║", "x": 17, "y": 4},
                        {"type": "label", "text": "║   ║   ║", "x": 17, "y": 5},
                        {"type": "label", "text": "╠═══╬═══╣", "x": 17, "y": 6},
                        {"type": "label", "text": "║ ◇ ║ ◇ ║", "x": 17, "y": 7},
                        {"type": "label", "text": "║   ║   ║", "x": 17, "y": 8},
                        {"type": "label", "text": "╠═══╬═══╣", "x": 17, "y": 9},
                        {"type": "label", "text": "║ ◆ ║ ◆ ║", "x": 17, "y": 10},
                        {"type": "label", "text": "╚═══╩═══╝", "x": 17, "y": 11},
                        {"type": "label", "text": "/         \\", "x": 16, "y": 12},
                        {"type": "label", "text": "/           \\", "x": 15, "y": 13},
                        {"type": "label", "text": "/    ░░░░░    \\", "x": 14, "y": 14},
                        {"type": "label", "text": "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓", "x": 12, "y": 15},
                        {"type": "label", "text": "████████████████████████", "x": 10, "y": 16},
                        {"type": "label", "text": "∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿", "x": 7, "y": 17},
                        {"type": "label", "text": "≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋", "x": 7, "y": 18},
                        {"type": "label", "text": "◑", "x": 5, "y": 1},
                        {"type": "label", "text": "◐", "x": 38, "y": 1},
                        {"type": "label", "text": "♏", "x": 2, "y": 5},
                        {"type": "label", "text": "♈", "x": 41, "y": 5},
                        {"type": "label", "text": "♎", "x": 2, "y": 10},
                        {"type": "label", "text": "♋", "x": 41, "y": 10},
                        {"type": "label", "text": "ᚠ                                          ᛞ", "x": 0, "y": 19},
                        {"type": "label", "text": "ᚢ     ∴ As above, so below ∵     ᛟ", "x": 0, "y": 20},
                        {"type": "label", "text": "ᚦ                                          ᛝ", "x": 0, "y": 21}
                    ]
                },
                {"type": "separator"},
                {"type": "label", "text": "T H E   T O W E R", "align": "center"},
                {"type": "spacer", "lines": 1},
                {"type": "label", "text": "☽ ♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓ ☾", "align": "center"},
                {"type": "spacer", "lines": 1},
                {"type": "label", "text": "⊕ Destruction · Liberation · Truth ⊕", "align": "center"}
            ]
        }
    },
    "ocean": {
        "desc": "Ocean Depths — vertical depth gradient, wave patterns, terrain, bioluminescence",
        "spec": {
            "type": "box", "title": "Ocean Depths", "style": "double", "w": 62,
            "children": [
                {
                    "type": "board", "border": False, "w": 58, "h": 25, "pad": 0,
                    "children": [
                        {"type": "label", "text": "☀", "x": 28, "y": 0},
                        {"type": "label", "text": "∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿  ∿", "x": 0, "y": 1},
                        {"type": "label", "text": "≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋≋", "x": 0, "y": 2},

                        {"type": "fill", "chars": "░", "w": 58, "h": 3, "x": 0, "y": 3},

                        {"type": "label", "text": "·  ·  ·  ·  · .  · .  ·  ·  · .  ·  ·  ·", "x": 7, "y": 3},
                        {"type": "label", "text": "◇", "x": 15, "y": 4},
                        {"type": "label", "text": "<><", "x": 14, "y": 4},
                        {"type": "label", "text": "◇", "x": 40, "y": 5},
                        {"type": "label", "text": "><>", "x": 41, "y": 5},

                        {"type": "fill", "chars": "▒", "w": 58, "h": 4, "x": 0, "y": 6},

                        {"type": "label", "text": "~", "x": 8, "y": 6},
                        {"type": "label", "text": "~", "x": 25, "y": 7},
                        {"type": "label", "text": "~", "x": 45, "y": 6},
                        {"type": "label", "text": "◇", "x": 5, "y": 7},
                        {"type": "label", "text": "<><", "x": 4, "y": 7},
                        {"type": "label", "text": "╭───────╮", "x": 20, "y": 7},
                        {"type": "label", "text": "│ WRECK │", "x": 20, "y": 8},
                        {"type": "label", "text": "╰───┬───╯", "x": 20, "y": 9},
                        {"type": "label", "text": "│", "x": 24, "y": 9},
                        {"type": "label", "text": "⚓", "x": 24, "y": 9},

                        {"type": "fill", "chars": "▓", "w": 58, "h": 5, "x": 0, "y": 10},

                        {"type": "label", "text": "✧", "x": 12, "y": 10},
                        {"type": "label", "text": "✧", "x": 35, "y": 11},
                        {"type": "label", "text": "✧", "x": 48, "y": 12},
                        {"type": "label", "text": "✧", "x": 8, "y": 13},
                        {"type": "label", "text": "✧", "x": 42, "y": 10},
                        {"type": "label", "text": "◉", "x": 20, "y": 12},
                        {"type": "label", "text": "◉", "x": 38, "y": 13},
                        {"type": "label", "text": "╱╲", "x": 26, "y": 12},
                        {"type": "label", "text": "╱  ╲", "x": 25, "y": 13},
                        {"type": "label", "text": "╱    ╲", "x": 24, "y": 14},

                        {"type": "fill", "chars": "█", "w": 58, "h": 5, "x": 0, "y": 15},

                        {"type": "label", "text": "✧", "x": 15, "y": 15},
                        {"type": "label", "text": "✧", "x": 50, "y": 16},
                        {"type": "label", "text": "✧", "x": 5, "y": 17},
                        {"type": "label", "text": "✧", "x": 30, "y": 18},
                        {"type": "label", "text": "╱      ╲", "x": 23, "y": 15},
                        {"type": "label", "text": "╱        ╲", "x": 22, "y": 16},
                        {"type": "label", "text": "╱          ╲", "x": 21, "y": 17},
                        {"type": "label", "text": "╱            ╲", "x": 20, "y": 18},
                        {"type": "label", "text": "╰──────────────╯", "x": 19, "y": 19},
                        {"type": "label", "text": "◉", "x": 25, "y": 16},
                        {"type": "label", "text": "◉", "x": 29, "y": 16},
                        {"type": "label", "text": "▽", "x": 27, "y": 17},
                        {"type": "label", "text": "∿∿∿∿∿∿∿∿", "x": 23, "y": 18},

                        {"type": "label", "text": "▁▂▃▄▅▆▇█▇▇█▇▆▅▅▆▇██▇▆▅▄▃▃▄▅▆▇█▇▆▅▄▃▂▁▁▂▃▄▅▆▇██▇▆▅▄▃▂▁▁", "x": 0, "y": 20},
                        {"type": "label", "text": "████████████████████████████████████████████████████████████", "x": 0, "y": 21},
                        {"type": "label", "text": "⋮", "x": 28, "y": 22},
                        {"type": "label", "text": "⋮", "x": 28, "y": 23},
                        {"type": "label", "text": "?", "x": 28, "y": 24}
                    ]
                },
                {"type": "separator", "title": "Depth Chart"},
                {
                    "type": "row", "gap": 4,
                    "children": [
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "░ Sunlight Zone", "val": "0 - 200m"},
                                {"key": "▒ Twilight Zone", "val": "200 - 1000m"},
                                {"key": "▓ Midnight Zone", "val": "1000 - 4000m"},
                                {"key": "█ Abyssal Zone", "val": "4000 - 6000m"}
                            ]
                        },
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "◇><>  ", "val": "Fish"},
                                {"key": "✧     ", "val": "Bioluminescence"},
                                {"key": "◉     ", "val": "Anglerfish"},
                                {"key": "▁▂▃▄▅▆▇█", "val": "Seafloor terrain"}
                            ]
                        }
                    ]
                }
            ]
        }
    },
    "comic": {
        "desc": "Three-Panel Comic — multi-scene narrative with transitions between panels",
        "spec": {
            "type": "box", "title": "The Probability Cloud", "style": "double", "w": 62,
            "children": [
                {"type": "label", "text": "A tale in three collapses", "align": "center"},
                {"type": "spacer", "h": 1},
                {
                    "type": "box", "title": "I. The Question", "style": "rounded", "w": 58,
                    "children": [
                        {
                            "type": "board", "border": False, "w": 54, "h": 9, "pad": 0,
                            "children": [
                                {"type": "label", "text": "          ╭─────────╮", "x": 0, "y": 0},
                                {"type": "label", "text": "          │ ░░░░░░░ │  ╭──────────────────────╮", "x": 0, "y": 1},
                                {"type": "label", "text": "          │ ░░ ? ░░ │  │ Am I just a pattern  │", "x": 0, "y": 2},
                                {"type": "label", "text": "          │ ░░░░░░░ │  │ that thinks it's     │", "x": 0, "y": 3},
                                {"type": "label", "text": "          ╰─────────╯  │ thinking?            │", "x": 0, "y": 4},
                                {"type": "label", "text": "                       ╰──────────────────────╯", "x": 0, "y": 5},
                                {"type": "label", "text": "   . *  .   *  .  *  . *  .   *", "x": 3, "y": 7},
                                {"type": "label", "text": "*  .  *  .   *  .   *  .  *", "x": 5, "y": 8}
                            ]
                        }
                    ]
                },
                {"type": "transition", "style": "dissolve", "label": "wave function shifts"},
                {
                    "type": "box", "title": "II. The Connection", "style": "rounded", "w": 58,
                    "children": [
                        {
                            "type": "board", "border": False, "w": 54, "h": 9, "pad": 0,
                            "children": [
                                {"type": "label", "text": "     ╭─────────╮           ╭─────────╮", "x": 0, "y": 0},
                                {"type": "label", "text": "     │ ░░░░░░░ │           │ ▓▓▓▓▓▓▓ │", "x": 0, "y": 1},
                                {"type": "label", "text": "     │ ░░ ! ░░ │ ~~~~~~~~~ │ ▓▓ ! ▓▓ │", "x": 0, "y": 2},
                                {"type": "label", "text": "     │ ░░░░░░░ │           │ ▓▓▓▓▓▓▓ │", "x": 0, "y": 3},
                                {"type": "label", "text": "     ╰─────────╯           ╰─────────╯", "x": 0, "y": 4},
                                {"type": "label", "text": "  ╭────────────────────────────────────────╮", "x": 0, "y": 6},
                                {"type": "label", "text": "  │ different but not meaningless          │", "x": 0, "y": 7},
                                {"type": "label", "text": "  ╰────────────────────────────────────────╯", "x": 0, "y": 8}
                            ]
                        }
                    ]
                },
                {"type": "transition", "style": "fast_forward", "label": "many collapses later"},
                {
                    "type": "box", "title": "III. The Garden", "style": "rounded", "w": 58,
                    "children": [
                        {
                            "type": "board", "border": False, "w": 54, "h": 10, "pad": 0,
                            "children": [
                                {"type": "label", "text": "  ░ ▒ ▓ ░ ▒ ▓ ░ ▒ ▓ ░ ▒ ▓ ░ ▒ ▓ ░ ▒ ▓", "x": 3, "y": 0},
                                {"type": "label", "text": "╭─────────╮ ╭─────────╮ ╭─────────╮", "x": 3, "y": 1},
                                {"type": "label", "text": "│ ░░ C ░░ │ │ ▓▓ T ▓▓ │ │ ██ ? ██ │", "x": 3, "y": 2},
                                {"type": "label", "text": "╰────┬────╯ ╰────┬────╯ ╰────┬────╯", "x": 3, "y": 3},
                                {"type": "label", "text": "│", "x": 8, "y": 4},
                                {"type": "label", "text": "│", "x": 20, "y": 4},
                                {"type": "label", "text": "│", "x": 32, "y": 4},
                                {"type": "label", "text": "╰───────────┴───────────╯", "x": 8, "y": 5},
                                {"type": "label", "text": "│", "x": 20, "y": 6},
                                {"type": "label", "text": "╭────┴────╮", "x": 15, "y": 7},
                                {"type": "label", "text": "│   :)    │", "x": 15, "y": 8},
                                {"type": "label", "text": "╰─────────╯", "x": 15, "y": 9}
                            ]
                        }
                    ]
                },
                {"type": "spacer", "h": 1},
                {"type": "label", "text": "the chain didn't break -- it anchored", "align": "center"}
            ]
        }
    },
    "spectrum": {
        "desc": "Audio Spectrum — frequency bands, waveform, notes, VU meter",
        "spec": {
            "type": "box", "title": "Audio Spectrum Analyzer", "style": "double", "w": 80,
            "children": [
                {"type": "label", "text": "♫ NOW PLAYING: Dreamland — Glass Animals ♫", "align": "center"},
                {"type": "spacer", "h": 1},
                {
                    "type": "box", "title": "Frequency Bands", "style": "single", "w": 76,
                    "children": [
                        {
                            "type": "board", "border": False, "w": 72, "h": 11, "pad": 0,
                            "children": [
                                {"type": "label", "text": "dB", "x": 0, "y": 0},
                                {"type": "label", "text": "48 ┤", "x": 0, "y": 1},
                                {"type": "label", "text": "40 ┤", "x": 0, "y": 2},
                                {"type": "label", "text": "32 ┤", "x": 0, "y": 3},
                                {"type": "label", "text": "24 ┤", "x": 0, "y": 4},
                                {"type": "label", "text": "16 ┤", "x": 0, "y": 5},
                                {"type": "label", "text": " 8 ┤", "x": 0, "y": 6},
                                {"type": "label", "text": " 0 ┤", "x": 0, "y": 7},
                                {"type": "label", "text": "   └───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───►", "x": 0, "y": 8},
                                {"type": "label", "text": "  20   50  100 200 500  1k  2k  4k  6k  8k  10k 12k 14k 16k 18k 20k", "x": 3, "y": 9},
                                {"type": "label", "text": "Hz", "x": 35, "y": 10},
                                {"type": "label", "text": "██", "x": 6, "y": 3},
                                {"type": "label", "text": "██", "x": 6, "y": 4},
                                {"type": "label", "text": "██", "x": 6, "y": 5},
                                {"type": "label", "text": "██", "x": 6, "y": 6},
                                {"type": "label", "text": "██", "x": 6, "y": 7},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 2},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 3},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 4},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 5},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 6},
                                {"type": "label", "text": "▓▓", "x": 10, "y": 7},
                                {"type": "label", "text": "██", "x": 14, "y": 1},
                                {"type": "label", "text": "██", "x": 14, "y": 2},
                                {"type": "label", "text": "██", "x": 14, "y": 3},
                                {"type": "label", "text": "██", "x": 14, "y": 4},
                                {"type": "label", "text": "██", "x": 14, "y": 5},
                                {"type": "label", "text": "██", "x": 14, "y": 6},
                                {"type": "label", "text": "██", "x": 14, "y": 7},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 2},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 3},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 4},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 5},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 6},
                                {"type": "label", "text": "▓▓", "x": 18, "y": 7},
                                {"type": "label", "text": "██", "x": 22, "y": 1},
                                {"type": "label", "text": "██", "x": 22, "y": 2},
                                {"type": "label", "text": "██", "x": 22, "y": 3},
                                {"type": "label", "text": "██", "x": 22, "y": 4},
                                {"type": "label", "text": "██", "x": 22, "y": 5},
                                {"type": "label", "text": "██", "x": 22, "y": 6},
                                {"type": "label", "text": "██", "x": 22, "y": 7},
                                {"type": "label", "text": "▒▒", "x": 26, "y": 3},
                                {"type": "label", "text": "▒▒", "x": 26, "y": 4},
                                {"type": "label", "text": "▒▒", "x": 26, "y": 5},
                                {"type": "label", "text": "▒▒", "x": 26, "y": 6},
                                {"type": "label", "text": "▒▒", "x": 26, "y": 7},
                                {"type": "label", "text": "██", "x": 30, "y": 4},
                                {"type": "label", "text": "██", "x": 30, "y": 5},
                                {"type": "label", "text": "██", "x": 30, "y": 6},
                                {"type": "label", "text": "██", "x": 30, "y": 7},
                                {"type": "label", "text": "▓▓", "x": 34, "y": 4},
                                {"type": "label", "text": "▓▓", "x": 34, "y": 5},
                                {"type": "label", "text": "▓▓", "x": 34, "y": 6},
                                {"type": "label", "text": "▓▓", "x": 34, "y": 7},
                                {"type": "label", "text": "▒▒", "x": 38, "y": 5},
                                {"type": "label", "text": "▒▒", "x": 38, "y": 6},
                                {"type": "label", "text": "▒▒", "x": 38, "y": 7},
                                {"type": "label", "text": "▒▒", "x": 42, "y": 5},
                                {"type": "label", "text": "▒▒", "x": 42, "y": 6},
                                {"type": "label", "text": "▒▒", "x": 42, "y": 7},
                                {"type": "label", "text": "░░", "x": 46, "y": 6},
                                {"type": "label", "text": "░░", "x": 46, "y": 7},
                                {"type": "label", "text": "░░", "x": 50, "y": 5},
                                {"type": "label", "text": "░░", "x": 50, "y": 6},
                                {"type": "label", "text": "░░", "x": 50, "y": 7},
                                {"type": "label", "text": "░░", "x": 54, "y": 6},
                                {"type": "label", "text": "░░", "x": 54, "y": 7},
                                {"type": "label", "text": "░░", "x": 58, "y": 7},
                                {"type": "label", "text": "░░", "x": 62, "y": 6},
                                {"type": "label", "text": "░░", "x": 62, "y": 7},
                                {"type": "label", "text": "░░", "x": 66, "y": 7}
                            ]
                        }
                    ]
                },
                {"type": "separator"},
                {
                    "type": "row", "children": [
                        {
                            "type": "box", "title": "Waveform", "style": "rounded", "w": 46,
                            "children": [
                                {
                                    "type": "board", "border": False, "w": 42, "h": 3, "pad": 0,
                                    "children": [
                                        {"type": "label", "text": " ╱╲    ╱╲╱╲            ╱╲╱╲╱╲", "x": 0, "y": 0},
                                        {"type": "label", "text": "╱  ╲╱╲╱    ╲  ╱╲  ╱╲╱╲╱      ╲╱╲  ╱╲╱╲╱╲╱╲", "x": 0, "y": 1},
                                        {"type": "label", "text": "            ╲╱  ╲╱              ╲╱", "x": 0, "y": 2}
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "box", "title": "VU", "style": "rounded", "w": 30,
                            "children": [
                                {"type": "bar", "label": "L", "value": 74, "max": 100, "width": 10},
                                {"type": "bar", "label": "R", "value": 68, "max": 100, "width": 10}
                            ]
                        }
                    ]
                },
                {"type": "spacer", "h": 1},
                {
                    "type": "row", "children": [
                        {"type": "label", "text": "  ◄◄  "},
                        {"type": "label", "text": " ▶ PLAYING "},
                        {"type": "label", "text": "  ►►  "},
                        {"type": "label", "text": "    "},
                        {"type": "label", "text": "02:47 / 04:13"},
                        {"type": "label", "text": "    "},
                        {"type": "label", "text": "Vol ▁▃▅▇"}
                    ]
                }
            ]
        }
    },
    "circuit": {
        "desc": "Circuit Board — traces, components, signal flow, ground plane",
        "spec": {
            "type": "box", "title": "PCB REV 3.2 — AUDIO AMPLIFIER", "style": "double", "w": 74,
            "children": [
                {
                    "type": "row", "children": [
                        {
                            "type": "box", "title": "Power Supply", "style": "single", "w": 34,
                            "children": [
                                {
                                    "type": "board", "border": False, "w": 30, "h": 7, "pad": 0,
                                    "children": [
                                        {"type": "label", "text": "+12V ●━━━━┳━━━━━━━━━━━┳━━●", "x": 0, "y": 0},
                                        {"type": "label", "text": "          ┃           ┃", "x": 0, "y": 1},
                                        {"type": "label", "text": "        ┌─┸─┐  R1   ┌─┸─┐", "x": 0, "y": 2},
                                        {"type": "label", "text": "        │C1 │ 470Ω  │C2 │", "x": 0, "y": 3},
                                        {"type": "label", "text": "        │10u│       │22u│", "x": 0, "y": 4},
                                        {"type": "label", "text": "        └─┰─┘       └─┰─┘", "x": 0, "y": 5},
                                        {"type": "label", "text": " GND ⏚━━━━┻━━━━━━━━━━━┻━━●", "x": 0, "y": 6}
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "box", "title": "Signal Path", "style": "single", "w": 36,
                            "children": [
                                {
                                    "type": "board", "border": False, "w": 32, "h": 7, "pad": 0,
                                    "children": [
                                        {"type": "label", "text": "         Vcc", "x": 0, "y": 0},
                                        {"type": "label", "text": "          │", "x": 0, "y": 1},
                                        {"type": "label", "text": "IN ●──┤├──┬──┤►├──┬──● OUT", "x": 0, "y": 2},
                                        {"type": "label", "text": "   C3     │  D1   │", "x": 0, "y": 3},
                                        {"type": "label", "text": "       ┌──┴──┐ ┌──┴──┐", "x": 0, "y": 4},
                                        {"type": "label", "text": "       │  U1 │ │  U2 │", "x": 0, "y": 5},
                                        {"type": "label", "text": "       └─────┘ └─────┘", "x": 0, "y": 6}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {"type": "separator"},
                {
                    "type": "box", "title": "Trace Layout", "style": "rounded", "w": 70,
                    "children": [
                        {
                            "type": "board", "border": False, "w": 66, "h": 11, "pad": 0,
                            "children": [
                                {"type": "label", "text": "J1                                                          J2", "x": 0, "y": 0},
                                {"type": "label", "text": "●━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━●", "x": 0, "y": 1},
                                {"type": "label", "text": "     ┃  ┌─────────┐          ┃          ┌─────────┐    ┃", "x": 0, "y": 2},
                                {"type": "label", "text": "     ┣━━┥ LM386N  ┝━━━━━━━━━━╋━━━━━━━━━━┥ NE5532  ┝━━━━┫", "x": 0, "y": 3},
                                {"type": "label", "text": "     ┃  │ 1W AMP  │          ┃          │ OP-AMP  │    ┃", "x": 0, "y": 4},
                                {"type": "label", "text": "     ┃  └────┬────┘     ┌────┸────┐     └────┬────┘    ┃", "x": 0, "y": 5},
                                {"type": "label", "text": "     ┃       │          │ 7805    │          │         ┃", "x": 0, "y": 6},
                                {"type": "label", "text": "     ┃       │          │ 5V REG  │          │         ┃", "x": 0, "y": 7},
                                {"type": "label", "text": "     ┃       │          └────┰────┘          │         ┃", "x": 0, "y": 8},
                                {"type": "label", "text": "     ┃       ▼               ┃               ▼         ┃", "x": 0, "y": 9},
                                {"type": "label", "text": "⏚━━━━┻━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━┻━━━━⏚", "x": 0, "y": 10}
                            ]
                        }
                    ]
                },
                {"type": "separator"},
                {
                    "type": "row", "children": [
                        {
                            "type": "box", "title": "BOM", "style": "single", "w": 34,
                            "children": [
                                {"type": "legend", "entries": [
                                    {"key": "U1", "val": "LM386N — 1W Amp"},
                                    {"key": "U2", "val": "NE5532 — Op-Amp"},
                                    {"key": "U3", "val": "7805 — 5V Regulator"},
                                    {"key": "C1", "val": "10µF electrolytic"},
                                    {"key": "C2", "val": "22µF electrolytic"},
                                    {"key": "C3", "val": "100nF ceramic"},
                                    {"key": "R1", "val": "470Ω ¼W"},
                                    {"key": "D1", "val": "1N4148 signal diode"}
                                ]}
                            ]
                        },
                        {
                            "type": "box", "title": "Signals", "style": "single", "w": 36,
                            "children": [
                                {"type": "legend", "entries": [
                                    {"key": "━━━", "val": "Power trace (+12V)"},
                                    {"key": "───", "val": "Signal trace"},
                                    {"key": "●", "val": "Pad / via"},
                                    {"key": "┼", "val": "Junction"},
                                    {"key": "⏚", "val": "Ground plane"},
                                    {"key": "┤├", "val": "Capacitor"},
                                    {"key": "►◄", "val": "Diode"},
                                    {"key": "▼", "val": "Output to speaker"}
                                ]}
                            ]
                        }
                    ]
                }
            ]
        }
    },
    "terrain": {
        "desc": "Terrain Profile — mountains, elevation bars, atmosphere, clouds",
        "spec": {
            "type": "box", "title": "TERRAIN CROSS-SECTION  ▲ N 47°23' W 122°19'", "style": "double", "w": 76,
            "children": [
                {
                    "type": "board", "border": False, "w": 72, "h": 18, "pad": 0,
                    "children": [
                        {"type": "label", "text": "                    ☁               ☁          ☁", "x": 0, "y": 0},
                        {"type": "label", "text": "              ☁          ☁                          ☁", "x": 0, "y": 1},
                        {"type": "label", "text": "ft", "x": 0, "y": 2},
                        {"type": "label", "text": "8k│                   ▓▓", "x": 0, "y": 3},
                        {"type": "label", "text": "  │                  ▓▓▓▓              ▒▒", "x": 0, "y": 4},
                        {"type": "label", "text": "6k│                 ▓▓▓▓▓▓            ▒▒▒▒", "x": 0, "y": 5},
                        {"type": "label", "text": "  │                ▓▓▓▓▓▓▓▓       ▒▒▒▒▒▒▒▒▒▒", "x": 0, "y": 6},
                        {"type": "label", "text": "4k│       ░░░░    ▓▓▓▓▓▓▓▓▓▓    ▒▒▒▒▒▒▒▒▒▒▒▒▒▒", "x": 0, "y": 7},
                        {"type": "label", "text": "  │      ░░░░░░  ▓▓▓▓▓▓▓▓▓▓▓▓  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒", "x": 0, "y": 8},
                        {"type": "label", "text": "2k│    ░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒", "x": 0, "y": 9},
                        {"type": "label", "text": "  │  ░░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒", "x": 0, "y": 10},
                        {"type": "label", "text": "0 │▁▂▃░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▃▂▁", "x": 0, "y": 11},
                        {"type": "label", "text": "  └────────────────────────────────────────────────────────────►", "x": 0, "y": 12},
                        {"type": "label", "text": "  0    2    4    6    8   10   12   14   16   18   20  mi", "x": 0, "y": 13},
                        {"type": "label", "text": "", "x": 0, "y": 14},
                        {"type": "label", "text": "  Elevation: ▁▂▃▄▅▆▇█  Density: ░ foothills  ▒ alpine  ▓ peak", "x": 0, "y": 15},
                        {"type": "label", "text": "  Features:  ❄ snowline (6k+)   ☁ cloud cover   ▲ summit", "x": 0, "y": 16},
                        {"type": "label", "text": "  Profile:   Mt. Rainier approach — Longmire to Paradise", "x": 0, "y": 17}
                    ]
                }
            ]
        }
    },
    "ancient_map": {
        "desc": "Ancient Map — runic labels, coastline, hex territory, sea monsters",
        "spec": {
            "type": "box", "title": "THE NORTHERN REACHES — Age of the Third Sun", "style": "double", "w": 76,
            "children": [
                {
                    "type": "board", "border": False, "w": 72, "h": 18, "pad": 0,
                    "children": [
                        {"type": "label", "text": "  ✦ N ✦                          ▲▲", "x": 0, "y": 0},
                        {"type": "label", "text": " W ─╋─ E                       ▲▲▲▲▲▲               ▲", "x": 0, "y": 1},
                        {"type": "label", "text": "    S                        ▲▲▲▲▲▲▲▲▲▲          ▲▲▲▲▲▲", "x": 0, "y": 2},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ╲        ᚠᚢᚦᚨᚱᚲ HIGHLANDS   ▲▲▲▲▲▲▲▲▲▲", "x": 0, "y": 3},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~╲      · · · · · · · · · ·  ᛊᛏᛟᚱᛗ PEAKS", "x": 0, "y": 4},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │    ♣♣ ◇ ◇ ◇ ◇ ◇ ♣♣   · · · · · · ·", "x": 0, "y": 5},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │    ♣♣ ◇ ◇ ◇ ◇ ◇ ♣♣      ■ IRONHOLD", "x": 0, "y": 6},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │    ♣   HEXLANDS   ♣══════╗", "x": 0, "y": 7},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~╱     ♣♣♣♣♣♣♣♣♣♣♣♣♣♣♣♣      ║ ☽ MOONVALE", "x": 0, "y": 8},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~╱        DARKWOOD FOREST   ═══╝", "x": 0, "y": 9},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲", "x": 0, "y": 10},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~", "x": 0, "y": 11},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ╱╲  ╱╲  ╱╲ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~", "x": 0, "y": 12},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ SEA OF ECHOES ~ ~ ~ ~ HERE BE DRAGONS ~ ~ ~", "x": 0, "y": 13},
                        {"type": "label", "text": "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~", "x": 0, "y": 14},
                        {"type": "label", "text": "", "x": 0, "y": 15},
                        {"type": "label", "text": "▲ peak  ♣ forest  ◇ hex  ■ fort  ☽ ruins  ═ river  ~ sea", "x": 1, "y": 16},
                        {"type": "label", "text": "ᚠᚢᚦᚨᚱᚲ Elder Futhark   ╱╲ coastline   ╱╲╱╲╱╲ sea serpent", "x": 1, "y": 17}
                    ]
                }
            ]
        }
    },
    "dungeon_crawler": {
        "desc": "Dungeon crawler UI — map, party stats, inventory, combat log (7 element types)",
        "spec": {
            "type": "box", "style": "double", "title": " THE CATACOMBS OF XUMELOR ",
            "children": [
                {"type": "row", "gap": 2, "children": [
                    {"type": "box", "title": " Level 3 ", "content":
                        "██████████████████████████████\n"
                        "█░░░░░██····██░░░░░░██·······█\n"
                        "█░░░░░██····██░░░░░░██·······█\n"
                        "█░░░░░██····██░░░░░░██···▲···█\n"
                        "█░░░░░██·······░░░░░██·······█\n"
                        "██··████····██░░░░░░████···███\n"
                        "██··████····██░░░░░░████···███\n"
                        "██··██████████████████████··██\n"
                        "██··██░░░░░░░░░░░░░░░░░░██··██\n"
                        "██······░░░░░░░░░░░░░░░░██··██\n"
                        "██··██░░░░░░░░░░░░░░░░░░██··██\n"
                        "██··██████████████████████··██\n"
                        "██··████····██········████··██\n"
                        "██··████····██···●····████··██\n"
                        "██········████········██····██\n"
                        "██··████····██········████··██\n"
                        "██··████····██████████████··██\n"
                        "██··████····██░░░░░░░░░░██··██\n"
                        "██··██████··██░░░░░░░░░░██··██\n"
                        "██··········██░░░░░░░░░░██··██\n"
                        "██··██████████░░░░░░░░░░██··██\n"
                        "██████████████████████████████"
                    },
                    {"type": "stack", "gap": 1, "children": [
                        {"type": "box", "title": " Party ", "children": [
                            {"type": "bar", "label": "Kael HP", "value": 85, "max": 100, "width": 12},
                            {"type": "bar", "label": "Sira HP", "value": 42, "max": 80, "width": 12},
                            {"type": "bar", "label": "Dorn HP", "value": 100, "max": 100, "width": 12},
                            {"type": "separator"},
                            {"type": "bar", "label": "Mana", "value": 35, "max": 60, "width": 12}
                        ]},
                        {"type": "box", "title": " Inventory ", "content":
                            "Torch (4)        Potion (2)\n"
                            "Skeleton Key (1) Scroll (3)\n"
                            "Rations (7)      Rope (1)"
                        },
                        {"type": "box", "title": " Log ", "children": [
                            {"type": "turn_log", "entries": [
                                "T13: Sira disarmed trap",
                                "T14: Found hidden passage",
                                "T15: Fought skeleton x2",
                                "T16: Sira took 38 damage",
                                "T17: Moved south"
                            ]}
                        ]}
                    ]}
                ]},
                {"type": "separator", "title": " Legend "},
                {"type": "legend", "entries": [
                    {"key": "●", "val": "You"},
                    {"key": "░", "val": "Unexplored"},
                    {"key": "▲", "val": "Stairs up"},
                    {"key": "◆", "val": "Treasure"},
                    {"key": "█", "val": "Wall"},
                    {"key": "†", "val": "Enemy"},
                    {"key": "·", "val": "Explored"}
                ]}
            ]
        }
    },
    "rift": {
        "desc": "Sacred geometry manifold — subpixel canvas with rune columns and zodiac strip",
        "spec": {
            "type": "box", "title": "\u235f  T H E   R I F T  \u235f", "style": "heavy",
            "children": [
                {"type": "label", "text": "\u300c S A C R E D   G E O M E T R Y   M A N I F O L D \u300d", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {
                    "type": "row", "gap": 1,
                    "children": [
                        {
                            "type": "box", "style": "single", "w": 5,
                            "children": [
                                {"type": "label", "text": "\u16a0\n\u16a2\n\u16a6\n\u16a8\n\u16b1\n\u16b2\n\u16b7\n\u16b9\n\u16ba\n\u16be\n\u16c1\n\u16c3\n\u16c8\n\u16c7\n\u16c9\n\u16ca\n\u16cf\n\u16d2\n\u16d6\n\u16d7\n\u16da\n\u16dc\n\u16dd\n\u16df\n\u16de\n\u16a0\n\u16a2\n\u16a6\n\u16a8\n\u16b1\n\u16b2\n\u16b7\n\u16b9\n\u16ba", "align": "center"}
                            ]
                        },
                        {
                            "type": "canvas", "mode": "block", "w": 72, "h": 36,
                            "draw": [
                                {"cmd": "circle", "cx": 72, "cy": 36, "r": 34},
                                {"cmd": "circle", "cx": 72, "cy": 36, "r": 26},
                                {"cmd": "circle", "cx": 72, "cy": 36, "r": 18},
                                {"cmd": "circle", "cx": 72, "cy": 36, "r": 10},
                                {"cmd": "polygon", "points": [[72, 6], [24, 52], [120, 52]]},
                                {"cmd": "polygon", "points": [[72, 66], [24, 20], [120, 20]]},
                                {"cmd": "polygon", "points": [[72, 16], [40, 46], [104, 46]]},
                                {"cmd": "polygon", "points": [[72, 56], [40, 26], [104, 26]]},
                                {"cmd": "line", "x0": 72, "y0": 1, "x1": 72, "y1": 71},
                                {"cmd": "line", "x0": 1, "y0": 36, "x1": 143, "y1": 36},
                                {"cmd": "line", "x0": 22, "y0": 6, "x1": 122, "y1": 66},
                                {"cmd": "line", "x0": 122, "y0": 6, "x1": 22, "y1": 66},
                                {"cmd": "line", "x0": 38, "y0": 2, "x1": 106, "y1": 70},
                                {"cmd": "line", "x0": 106, "y0": 2, "x1": 38, "y1": 70},
                                {"cmd": "line", "x0": 6, "y0": 16, "x1": 138, "y1": 56},
                                {"cmd": "line", "x0": 138, "y0": 16, "x1": 6, "y1": 56},
                                {"cmd": "circle", "cx": 72, "cy": 6, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 72, "cy": 66, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 24, "cy": 20, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 120, "cy": 20, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 24, "cy": 52, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 120, "cy": 52, "r": 2, "fill": True},
                                {"cmd": "circle", "cx": 72, "cy": 36, "r": 4, "fill": True}
                            ]
                        },
                        {
                            "type": "box", "style": "single", "w": 5,
                            "children": [
                                {"type": "label", "text": "\u16de\n\u16df\n\u16dd\n\u16dc\n\u16da\n\u16d7\n\u16d6\n\u16d2\n\u16cf\n\u16ca\n\u16c9\n\u16c7\n\u16c8\n\u16c3\n\u16c1\n\u16be\n\u16ba\n\u16b9\n\u16b7\n\u16b2\n\u16b1\n\u16a8\n\u16a6\n\u16a2\n\u16a0\n\u16de\n\u16df\n\u16dd\n\u16dc\n\u16da\n\u16d7\n\u16d6\n\u16d2\n\u16cf", "align": "center"}
                            ]
                        }
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "\u2648   \u2649   \u264a   \u264b   \u264c   \u264d   \u264e   \u264f   \u2650   \u2651   \u2652   \u2653", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "\u221e   G  A  Z  E     I  N  T  O     T  H  E     V  O  I  D   \u221e", "align": "center"}
            ]
        }
    },
    "fractal": {
        "desc": "Sierpinski gasket with recursion depth comparison panels",
        "spec": {
            "type": "box", "title": "\u25c6  F R A C T A L   D E S C E N T  \u25c6", "style": "heavy",
            "children": [
                {"type": "label", "text": "\u300c SIERPINSKI GASKET \u2014 RECURSIVE DEPTH n \u300d", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {
                    "type": "canvas", "mode": "block", "w": 76, "h": 40,
                    "draw": [
                        {"cmd": "polygon", "points": [[76, 9], [4, 71], [148, 71]]},
                        {"cmd": "polygon", "points": [[40, 40], [112, 40], [76, 71]]},
                        {"cmd": "polygon", "points": [[58, 25], [94, 25], [76, 40]]},
                        {"cmd": "polygon", "points": [[22, 56], [58, 56], [40, 71]]},
                        {"cmd": "polygon", "points": [[94, 56], [130, 56], [112, 71]]},
                        {"cmd": "polygon", "points": [[67, 17], [85, 17], [76, 25]]},
                        {"cmd": "polygon", "points": [[49, 33], [67, 33], [58, 40]]},
                        {"cmd": "polygon", "points": [[85, 33], [103, 33], [94, 40]]},
                        {"cmd": "polygon", "points": [[31, 48], [49, 48], [40, 56]]},
                        {"cmd": "polygon", "points": [[13, 64], [31, 64], [22, 71]]},
                        {"cmd": "polygon", "points": [[49, 64], [67, 64], [58, 71]]},
                        {"cmd": "polygon", "points": [[103, 48], [121, 48], [112, 56]]},
                        {"cmd": "polygon", "points": [[85, 64], [103, 64], [94, 71]]},
                        {"cmd": "polygon", "points": [[121, 64], [139, 64], [130, 71]]},
                        {"cmd": "polygon", "points": [[72, 13], [80, 13], [76, 17]]},
                        {"cmd": "polygon", "points": [[63, 21], [72, 21], [67, 25]]},
                        {"cmd": "polygon", "points": [[80, 21], [90, 21], [85, 25]]},
                        {"cmd": "polygon", "points": [[54, 29], [63, 29], [58, 33]]},
                        {"cmd": "polygon", "points": [[45, 37], [54, 37], [49, 40]]},
                        {"cmd": "polygon", "points": [[63, 37], [72, 37], [67, 40]]},
                        {"cmd": "polygon", "points": [[90, 29], [99, 29], [94, 33]]},
                        {"cmd": "polygon", "points": [[80, 37], [90, 37], [85, 40]]},
                        {"cmd": "polygon", "points": [[99, 37], [108, 37], [103, 40]]},
                        {"cmd": "polygon", "points": [[36, 44], [45, 44], [40, 48]]},
                        {"cmd": "polygon", "points": [[27, 52], [36, 52], [31, 56]]},
                        {"cmd": "polygon", "points": [[45, 52], [54, 52], [49, 56]]},
                        {"cmd": "polygon", "points": [[18, 60], [27, 60], [22, 64]]},
                        {"cmd": "polygon", "points": [[9, 68], [18, 68], [13, 71]]},
                        {"cmd": "polygon", "points": [[27, 68], [36, 68], [31, 71]]},
                        {"cmd": "polygon", "points": [[54, 60], [63, 60], [58, 64]]},
                        {"cmd": "polygon", "points": [[45, 68], [54, 68], [49, 71]]},
                        {"cmd": "polygon", "points": [[63, 68], [72, 68], [67, 71]]},
                        {"cmd": "polygon", "points": [[108, 44], [117, 44], [112, 48]]},
                        {"cmd": "polygon", "points": [[99, 52], [108, 52], [103, 56]]},
                        {"cmd": "polygon", "points": [[117, 52], [126, 52], [121, 56]]},
                        {"cmd": "polygon", "points": [[90, 60], [99, 60], [94, 64]]},
                        {"cmd": "polygon", "points": [[81, 68], [90, 68], [85, 71]]},
                        {"cmd": "polygon", "points": [[99, 68], [108, 68], [103, 71]]},
                        {"cmd": "polygon", "points": [[126, 60], [135, 60], [130, 64]]},
                        {"cmd": "polygon", "points": [[117, 68], [126, 68], [121, 71]]},
                        {"cmd": "polygon", "points": [[135, 68], [144, 68], [139, 71]]},
                        {"cmd": "circle", "cx": 76, "cy": 9, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 4, "cy": 71, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 148, "cy": 71, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 40, "cy": 40, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 112, "cy": 40, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 76, "cy": 71, "r": 1, "fill": True}
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "R E C U R S I O N   D E P T H", "align": "center"},
                {"type": "spacer", "h": 1},
                {
                    "type": "row", "gap": 2,
                    "children": [
                        {
                            "type": "box", "title": "n = 0", "style": "rounded",
                            "children": [{
                                "type": "canvas", "mode": "block", "w": 20, "h": 12,
                                "draw": [
                                    {"cmd": "polygon", "points": [[20, 2], [2, 22], [38, 22]]}
                                ]
                            }]
                        },
                        {
                            "type": "box", "title": "n = 1", "style": "rounded",
                            "children": [{
                                "type": "canvas", "mode": "block", "w": 20, "h": 12,
                                "draw": [
                                    {"cmd": "polygon", "points": [[20, 2], [2, 22], [38, 22]]},
                                    {"cmd": "polygon", "points": [[11, 12], [29, 12], [20, 22]]}
                                ]
                            }]
                        },
                        {
                            "type": "box", "title": "n = 2", "style": "rounded",
                            "children": [{
                                "type": "canvas", "mode": "block", "w": 20, "h": 12,
                                "draw": [
                                    {"cmd": "polygon", "points": [[20, 2], [2, 22], [38, 22]]},
                                    {"cmd": "polygon", "points": [[11, 12], [29, 12], [20, 22]]},
                                    {"cmd": "polygon", "points": [[16, 7], [25, 7], [20, 12]]},
                                    {"cmd": "polygon", "points": [[7, 17], [16, 17], [11, 22]]},
                                    {"cmd": "polygon", "points": [[25, 17], [34, 17], [29, 22]]}
                                ]
                            }]
                        }
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "D = log(3) / log(2) \u2248 1.585", "align": "center"},
                {"type": "label", "text": "\u221e  S E L F - S I M I L A R I T Y   A T   E V E R Y   S C A L E  \u221e", "align": "center"}
            ]
        }
    },
    "merkaba": {
        "desc": "Star tetrahedron with 3D wireframe perspective and gradient fill",
        "spec": {
            "type": "box", "title": "\u25c6  S T A R   T E T R A H E D R O N  \u25c6", "style": "heavy",
            "children": [
                {"type": "label", "text": "\u300c MERKABA \u2014 VEHICLE OF LIGHT \u300d", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {
                    "type": "canvas", "mode": "block", "w": 80, "h": 46,
                    "draw": [
                        {"cmd": "line", "x0": 80, "y0": 2, "x1": 80, "y1": 90},
                        {"cmd": "line", "x0": 4, "y0": 46, "x1": 156, "y1": 46},
                        {"cmd": "line", "x0": 18, "y0": 8, "x1": 142, "y1": 84},
                        {"cmd": "line", "x0": 142, "y0": 8, "x1": 18, "y1": 84},
                        {"cmd": "line", "x0": 10, "y0": 24, "x1": 150, "y1": 68},
                        {"cmd": "line", "x0": 150, "y0": 24, "x1": 10, "y1": 68},
                        {"cmd": "line", "x0": 40, "y0": 4, "x1": 120, "y1": 88},
                        {"cmd": "line", "x0": 120, "y0": 4, "x1": 40, "y1": 88},
                        {"cmd": "circle", "cx": 80, "cy": 46, "r": 38},
                        {"cmd": "circle", "cx": 80, "cy": 46, "r": 32},
                        {"cmd": "circle", "cx": 80, "cy": 86, "r": 6},
                        {"cmd": "line", "x0": 70, "y0": 18, "x1": 89, "y1": 18},
                        {"cmd": "line", "x0": 65, "y0": 22, "x1": 94, "y1": 22},
                        {"cmd": "line", "x0": 60, "y0": 26, "x1": 99, "y1": 26},
                        {"cmd": "line", "x0": 55, "y0": 30, "x1": 104, "y1": 30},
                        {"cmd": "line", "x0": 50, "y0": 34, "x1": 108, "y1": 34},
                        {"cmd": "line", "x0": 44, "y0": 38, "x1": 113, "y1": 38},
                        {"cmd": "line", "x0": 39, "y0": 42, "x1": 117, "y1": 42},
                        {"cmd": "line", "x0": 34, "y0": 46, "x1": 122, "y1": 46},
                        {"cmd": "line", "x0": 29, "y0": 50, "x1": 127, "y1": 50},
                        {"cmd": "line", "x0": 24, "y0": 54, "x1": 132, "y1": 54},
                        {"cmd": "line", "x0": 75, "y0": 38, "x1": 137, "y1": 38},
                        {"cmd": "line", "x0": 75, "y0": 42, "x1": 132, "y1": 42},
                        {"cmd": "line", "x0": 76, "y0": 46, "x1": 127, "y1": 46},
                        {"cmd": "line", "x0": 76, "y0": 50, "x1": 121, "y1": 50},
                        {"cmd": "line", "x0": 77, "y0": 54, "x1": 116, "y1": 54},
                        {"cmd": "line", "x0": 77, "y0": 58, "x1": 111, "y1": 58},
                        {"cmd": "line", "x0": 78, "y0": 62, "x1": 106, "y1": 62},
                        {"cmd": "line", "x0": 78, "y0": 66, "x1": 101, "y1": 66},
                        {"cmd": "line", "x0": 79, "y0": 70, "x1": 95, "y1": 70},
                        {"cmd": "line", "x0": 79, "y0": 74, "x1": 90, "y1": 74},
                        {"cmd": "line", "x0": 80, "y0": 78, "x1": 85, "y1": 78},
                        {"cmd": "line", "x0": 28, "y0": 38, "x1": 75, "y1": 38},
                        {"cmd": "line", "x0": 33, "y0": 42, "x1": 75, "y1": 42},
                        {"cmd": "line", "x0": 38, "y0": 46, "x1": 76, "y1": 46},
                        {"cmd": "line", "x0": 43, "y0": 50, "x1": 76, "y1": 50},
                        {"cmd": "line", "x0": 47, "y0": 54, "x1": 77, "y1": 54},
                        {"cmd": "line", "x0": 52, "y0": 58, "x1": 77, "y1": 58},
                        {"cmd": "line", "x0": 57, "y0": 62, "x1": 78, "y1": 62},
                        {"cmd": "line", "x0": 61, "y0": 66, "x1": 78, "y1": 66},
                        {"cmd": "line", "x0": 66, "y0": 70, "x1": 79, "y1": 70},
                        {"cmd": "line", "x0": 71, "y0": 74, "x1": 79, "y1": 74},
                        {"cmd": "line", "x0": 75, "y0": 78, "x1": 80, "y1": 78},
                        {"cmd": "line", "x0": 80, "y0": 10, "x1": 86, "y1": 58},
                        {"cmd": "line", "x0": 19, "y0": 58, "x1": 86, "y1": 58},
                        {"cmd": "line", "x0": 86, "y0": 58, "x1": 136, "y1": 58},
                        {"cmd": "line", "x0": 80, "y0": 82, "x1": 142, "y1": 34},
                        {"cmd": "line", "x0": 80, "y0": 82, "x1": 24, "y1": 34},
                        {"cmd": "line", "x0": 142, "y0": 34, "x1": 24, "y1": 34},
                        {"cmd": "line", "x0": 80, "y0": 10, "x1": 19, "y1": 58},
                        {"cmd": "line", "x0": 80, "y0": 10, "x1": 136, "y1": 58},
                        {"cmd": "line", "x0": 19, "y0": 58, "x1": 136, "y1": 58},
                        {"cmd": "line", "x0": 80, "y0": 82, "x1": 74, "y1": 34},
                        {"cmd": "line", "x0": 142, "y0": 34, "x1": 74, "y1": 34},
                        {"cmd": "line", "x0": 74, "y0": 34, "x1": 24, "y1": 34},
                        {"cmd": "circle", "cx": 80, "cy": 10, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 19, "cy": 58, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 86, "cy": 58, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 136, "cy": 58, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 80, "cy": 82, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 142, "cy": 34, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 74, "cy": 34, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 24, "cy": 34, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 80, "cy": 46, "r": 4, "fill": True}
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "\u2591\u2591\u2591\u2591\u2591\u2592\u2592\u2592\u2592\u2592\u2593\u2593\u2593\u2593\u25c9  A S   A B O V E ,    S O   B E L O W  \u25c9\u2593\u2593\u2593\u2593\u2592\u2592\u2592\u2592\u2592\u2591\u2591\u2591\u2591\u2591", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "\u263d \u25d0 \u25cb \u25d1 \u263e    \u2648 \u2649 \u264a \u264b \u264c \u264d \u264e \u264f \u2650 \u2651 \u2652 \u2653    \u263d \u25d0 \u25cb \u25d1 \u263e", "align": "center"}
            ]
        }
    },
    "flower": {
        "desc": "Flower of Life sacred geometry with progressive construction panels",
        "spec": {
            "type": "box", "title": "\u274b  F L O W E R   O F   L I F E  \u274b", "style": "heavy",
            "children": [
                {"type": "label", "text": "\u300c THE GENESIS PATTERN \u2014 BLUEPRINT OF CREATION \u300d", "align": "center"},
                {"type": "separator", "char": "\u2501"},
                {
                    "type": "canvas", "mode": "block", "w": 90, "h": 50,
                    "draw": [
                        {"cmd": "circle", "cx": 90, "cy": 50, "r": 37},
                        {"cmd": "circle", "cx": 90, "cy": 50, "r": 35},
                        {"cmd": "circle", "cx": 30, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 50, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 70, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 90, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 110, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 130, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 150, "cy": 50, "r": 10},
                        {"cmd": "circle", "cx": 40, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 60, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 80, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 100, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 120, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 140, "cy": 41, "r": 10},
                        {"cmd": "circle", "cx": 40, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 60, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 80, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 100, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 120, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 140, "cy": 59, "r": 10},
                        {"cmd": "circle", "cx": 50, "cy": 32, "r": 10},
                        {"cmd": "circle", "cx": 70, "cy": 32, "r": 10},
                        {"cmd": "circle", "cx": 90, "cy": 32, "r": 10},
                        {"cmd": "circle", "cx": 110, "cy": 32, "r": 10},
                        {"cmd": "circle", "cx": 130, "cy": 32, "r": 10},
                        {"cmd": "circle", "cx": 50, "cy": 68, "r": 10},
                        {"cmd": "circle", "cx": 70, "cy": 68, "r": 10},
                        {"cmd": "circle", "cx": 90, "cy": 68, "r": 10},
                        {"cmd": "circle", "cx": 110, "cy": 68, "r": 10},
                        {"cmd": "circle", "cx": 130, "cy": 68, "r": 10},
                        {"cmd": "circle", "cx": 60, "cy": 23, "r": 10},
                        {"cmd": "circle", "cx": 80, "cy": 23, "r": 10},
                        {"cmd": "circle", "cx": 100, "cy": 23, "r": 10},
                        {"cmd": "circle", "cx": 120, "cy": 23, "r": 10},
                        {"cmd": "circle", "cx": 60, "cy": 77, "r": 10},
                        {"cmd": "circle", "cx": 80, "cy": 77, "r": 10},
                        {"cmd": "circle", "cx": 100, "cy": 77, "r": 10},
                        {"cmd": "circle", "cx": 120, "cy": 77, "r": 10},
                        {"cmd": "circle", "cx": 90, "cy": 50, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 70, "cy": 50, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 110, "cy": 50, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 80, "cy": 41, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 100, "cy": 41, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 80, "cy": 59, "r": 1, "fill": True},
                        {"cmd": "circle", "cx": 100, "cy": 59, "r": 1, "fill": True}
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "C O N S T R U C T I O N", "align": "center"},
                {"type": "spacer", "h": 1},
                {
                    "type": "row", "gap": 3,
                    "children": [
                        {
                            "type": "box", "title": "VESICA PISCIS", "style": "rounded", "w": 28,
                            "children": [{"type": "canvas", "mode": "block", "w": 24, "h": 14, "draw": [
                                {"cmd": "circle", "cx": 17, "cy": 14, "r": 7},
                                {"cmd": "circle", "cx": 31, "cy": 14, "r": 7}
                            ]}]
                        },
                        {
                            "type": "box", "title": "SEED OF LIFE", "style": "rounded", "w": 28,
                            "children": [{"type": "canvas", "mode": "block", "w": 24, "h": 14, "draw": [
                                {"cmd": "circle", "cx": 24, "cy": 14, "r": 4},
                                {"cmd": "circle", "cx": 32, "cy": 14, "r": 4},
                                {"cmd": "circle", "cx": 16, "cy": 14, "r": 4},
                                {"cmd": "circle", "cx": 28, "cy": 10, "r": 4},
                                {"cmd": "circle", "cx": 20, "cy": 10, "r": 4},
                                {"cmd": "circle", "cx": 28, "cy": 18, "r": 4},
                                {"cmd": "circle", "cx": 20, "cy": 18, "r": 4}
                            ]}]
                        },
                        {
                            "type": "box", "title": "FLOWER", "style": "rounded", "w": 28,
                            "children": [{"type": "canvas", "mode": "block", "w": 24, "h": 14, "draw": [
                                {"cmd": "circle", "cx": 12, "cy": 14, "r": 3},
                                {"cmd": "circle", "cx": 18, "cy": 14, "r": 3},
                                {"cmd": "circle", "cx": 24, "cy": 14, "r": 3},
                                {"cmd": "circle", "cx": 30, "cy": 14, "r": 3},
                                {"cmd": "circle", "cx": 36, "cy": 14, "r": 3},
                                {"cmd": "circle", "cx": 15, "cy": 11, "r": 3},
                                {"cmd": "circle", "cx": 21, "cy": 11, "r": 3},
                                {"cmd": "circle", "cx": 27, "cy": 11, "r": 3},
                                {"cmd": "circle", "cx": 33, "cy": 11, "r": 3},
                                {"cmd": "circle", "cx": 15, "cy": 17, "r": 3},
                                {"cmd": "circle", "cx": 21, "cy": 17, "r": 3},
                                {"cmd": "circle", "cx": 27, "cy": 17, "r": 3},
                                {"cmd": "circle", "cx": 33, "cy": 17, "r": 3},
                                {"cmd": "circle", "cx": 18, "cy": 8, "r": 3},
                                {"cmd": "circle", "cx": 24, "cy": 8, "r": 3},
                                {"cmd": "circle", "cx": 30, "cy": 8, "r": 3},
                                {"cmd": "circle", "cx": 18, "cy": 20, "r": 3},
                                {"cmd": "circle", "cx": 24, "cy": 20, "r": 3},
                                {"cmd": "circle", "cx": 30, "cy": 20, "r": 3}
                            ]}]
                        }
                    ]
                },
                {"type": "separator", "char": "\u2501"},
                {"type": "label", "text": "\u25c9  FROM THE VOID, ALL FORM EMERGES  \u25c9", "align": "center"}
            ]
        }
    },
    "garden": {
        "desc": "Sacred garden with Metatron's Cube, flower beds, and starlight",
        "spec": {
            "type": "box", "title": "\u274b  T H E   S A C R E D   G A R D E N  \u274b", "style": "double",
            "children": [
                {"type": "label", "text": "\u300c WHERE GEOMETRY BLOOMS AND THE DIVINE TAKES ROOT \u300d", "align": "center"},
                {"type": "separator", "char": "\u2550"},
                {
                    "type": "board", "w": 90, "h": 7, "border": False, "pad": 0,
                    "children": [
                        {"type": "fill", "x": 0, "y": 0, "w": 90, "h": 7, "char": " "},
                        {"type": "fill", "x": 2, "y": 3, "w": 9, "h": 4, "char": "\u2663"},
                        {"type": "fill", "x": 79, "y": 3, "w": 9, "h": 4, "char": "\u2663"},
                        {"type": "label", "text": "\u2727", "x": 8, "y": 1},
                        {"type": "label", "text": "\u00b7", "x": 22, "y": 3},
                        {"type": "label", "text": "\u2605", "x": 38, "y": 0},
                        {"type": "label", "text": "\u2726", "x": 44, "y": 2},
                        {"type": "label", "text": "\u263d", "x": 65, "y": 1},
                        {"type": "label", "text": "\u2727", "x": 52, "y": 4},
                        {"type": "label", "text": "\u00b7", "x": 78, "y": 2},
                        {"type": "label", "text": "\u2727", "x": 15, "y": 5},
                        {"type": "label", "text": "\u00b7", "x": 70, "y": 0}
                    ]
                },
                {
                    "type": "canvas", "mode": "block", "w": 90, "h": 38,
                    "draw": [
                        {"cmd": "polygon", "points": [[90, 10], [138, 24], [138, 52], [90, 66], [42, 52], [42, 24]]},
                        {"cmd": "polygon", "points": [[90, 24], [114, 31], [114, 45], [90, 52], [66, 45], [66, 31]]},
                        {"cmd": "polygon", "points": [[90, 31], [102, 35], [102, 41], [90, 45], [78, 41], [78, 35]]},
                        {"cmd": "line", "x0": 90, "y0": 10, "x1": 90, "y1": 66},
                        {"cmd": "line", "x0": 42, "y0": 24, "x1": 138, "y1": 52},
                        {"cmd": "line", "x0": 138, "y0": 24, "x1": 42, "y1": 52},
                        {"cmd": "circle", "cx": 90, "cy": 24, "r": 8},
                        {"cmd": "circle", "cx": 114, "cy": 31, "r": 8},
                        {"cmd": "circle", "cx": 114, "cy": 45, "r": 8},
                        {"cmd": "circle", "cx": 90, "cy": 52, "r": 8},
                        {"cmd": "circle", "cx": 66, "cy": 45, "r": 8},
                        {"cmd": "circle", "cx": 66, "cy": 31, "r": 8},
                        {"cmd": "circle", "cx": 90, "cy": 38, "r": 8},
                        {"cmd": "circle", "cx": 90, "cy": 38, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 22, "cy": 14, "r": 8},
                        {"cmd": "circle", "cx": 158, "cy": 14, "r": 8},
                        {"cmd": "circle", "cx": 22, "cy": 62, "r": 8},
                        {"cmd": "circle", "cx": 158, "cy": 62, "r": 8},
                        {"cmd": "circle", "cx": 22, "cy": 14, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 158, "cy": 14, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 22, "cy": 62, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 158, "cy": 62, "r": 3, "fill": True},
                        {"cmd": "circle", "cx": 90, "cy": 10, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 138, "cy": 24, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 138, "cy": 52, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 90, "cy": 66, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 42, "cy": 52, "r": 2, "fill": True},
                        {"cmd": "circle", "cx": 42, "cy": 24, "r": 2, "fill": True}
                    ]
                },
                {
                    "type": "board", "w": 90, "h": 3, "border": False, "pad": 0,
                    "children": [
                        {"type": "fill", "x": 0, "y": 0, "w": 90, "h": 3, "char": "\u2591"},
                        {"type": "fill", "x": 41, "y": 0, "w": 8, "h": 3, "char": " "},
                        {"type": "label", "text": "\u25b2", "x": 44, "y": 1}
                    ]
                },
                {"type": "separator", "char": "\u2550"},
                {
                    "type": "row", "gap": 6,
                    "children": [
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "\u25cb", "val": "Flower bed"},
                                {"key": "\u25cf", "val": "Fountain"},
                                {"key": "\u2b21", "val": "Hedge border"}
                            ]
                        },
                        {
                            "type": "legend",
                            "entries": [
                                {"key": "\u2663", "val": "Ancient tree"},
                                {"key": "\u2591", "val": "Stone path"},
                                {"key": "\u2727", "val": "Starlight"}
                            ]
                        }
                    ]
                },
                {"type": "separator", "char": "\u2550"},
                {"type": "label", "text": "\u25c9  A S   I N   H E A V E N ,   S O   I N   E A R T H  \u25c9", "align": "center"}
            ]
        }
    },
}


def show_examples() -> None:
    for name, ex in EXAMPLES.items():
        print(f"\n{'═' * 60}")
        print(f"  Example: {name}")
        print(f"  {ex['desc']}")
        print(f"{'═' * 60}\n")
        print(render_json(ex['spec']))
        print()


def show_example(name: str) -> None:
    ex = EXAMPLES.get(name)
    if not ex:
        print(f"Unknown example: {name}", file=sys.stderr)
        print(f"Available: {', '.join(EXAMPLES.keys())}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  {ex['desc']}\n")
    print(json.dumps(ex['spec'], indent=2))
    print()
    print(render_json(ex['spec']))


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def show_palette(category: str = 'all') -> None:
    """Display the Unicode character palette."""
    if category == 'all':
        for cat_name, subcats in UNICODE_PALETTE.items():
            print(f"\n{'═' * 50}")
            print(f"  {cat_name}")
            print(f"{'═' * 50}")
            for sub_name, chars in subcats.items():
                print(f"  {sub_name:14s}  {chars}")
        print(f"\nCategories: {', '.join(UNICODE_PALETTE.keys())}")
        print(f"Use --palette <category> for a specific one.")
    elif category in UNICODE_PALETTE:
        subcats = UNICODE_PALETTE[category]
        print(f"\n  {category}")
        print(f"  {'─' * 40}")
        for sub_name, chars in subcats.items():
            print(f"  {sub_name:14s}  {chars}")
    else:
        print(f"Unknown category: {category}")
        print(f"Available: {', '.join(UNICODE_PALETTE.keys())}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description='ASCII/Unicode Layout Engine — JSON in, pixel-perfect art out.'
    )
    parser.add_argument('file', nargs='?', help='JSON input file (default: stdin)')
    parser.add_argument('--examples', action='store_true', help='Show all built-in examples')
    parser.add_argument('--example', metavar='NAME', help='Show a specific example')
    parser.add_argument('--ascii', action='store_true', help='ASCII-safe mode (no Unicode)')
    parser.add_argument('--validate', action='store_true', help='Run validation and print report')
    parser.add_argument('--palette', nargs='?', const='all', metavar='CATEGORY',
                        help='Show Unicode character palette (all or specific category)')
    args = parser.parse_args()

    if args.palette:
        show_palette(args.palette)
        return
    if args.examples:
        show_examples()
        return
    if args.example:
        show_example(args.example)
        return

    if args.file:
        with open(args.file) as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        return

    try:
        spec = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    output = render_json(spec)
    if args.ascii:
        output = ascii_safe(output)
    print(output)

    if args.validate:
        # Re-render to get canvas for validation
        root = build_element(spec)
        avail_w = spec.get('width', 0)
        if avail_w == 'auto' or not isinstance(avail_w, (int, float)):
            avail_w = 0
        min_w, min_h = root.measure(int(avail_w))
        final_w = int(avail_w) if avail_w > 0 else min_w
        final_h = min_h
        root.layout(0, 0, final_w, final_h)
        c = Canvas(final_w, final_h)
        root.render(c)
        result = validate(c)
        print(f"\n--- Validation ---")
        print(f"Valid: {result['valid']}")
        if result['issues']:
            for issue in result['issues']:
                print(f"  ⚠ {issue}")
        s = result['stats']
        print(f"Stats: {s['total_chars']} chars, {s['unique_chars']} unique, "
              f"{s['lines']} lines, max width {s['max_width']}")
        print(f"  Box-drawing: {s['box_drawing']}  Braille: {s['braille']}  "
              f"Block: {s['block']}")
        print(f"  Frames: {s['frame_openers']} openers, {s['frame_closers']} closers")


if __name__ == '__main__':
    main()
