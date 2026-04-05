# Projector

!!! ON GREETING, ALWAYS READ PROJECTOR-GUIDE.md FIRST AND DEEPLY INGEST THE COMPOSITION MINDSET'S PRINCIPLES !!!

Three-pass ASCII/Unicode layout engine. Models describe structure in JSON, the engine guarantees pixel-perfect alignment.

```
JSON spec  -->  Measure (bottom-up)  -->  Layout (top-down)  -->  Render (to canvas)
```

## In this repo

- **Engine:** `projector.py` (~3,200 lines). All 23 element types, the three-pass pipeline, validation, and CLI live here.
- **Docs:** `PROJECTOR-GUIDE.md` (full composition guide), `SHOWCASE.md` (rendered gallery), `README.md` (public-facing)
- **Examples:** `examples/` (JSON specs) + 35 built-in examples via `--example NAME`
- **Tests/scratch:** `tmp/` (gitignored)

### Running

```bash
python3 projector.py spec.json              # render
python3 projector.py --validate spec.json   # structural checks
python3 projector.py --example dashboard    # built-in examples
```

### When editing the engine

- The layout contract: `measure()` sets `_min_w`/`_min_h` (bottom-up), `layout()` receives allocated space from parent (top-down), `render()` draws to canvas.
- Elements with explicit declared dimensions (`w`/`h` props) must honor them in `layout()`, using their own sizes over parent-allocated ones. `CanvasElement` and `BoardElement` already do this. If you add a new element with explicit sizing, follow the same pattern.
- Run the built-in examples after changes: `python3 -c "import json; from projector import render_json; [render_json(json.load(open(f))) for f in ['examples/alchemist.json', 'examples/tarot.json']]"`

## Composition mindset

Every element in a spec exists in relationship to every other element. Before placing anything, consider how it interacts with its neighbors: does it give them room, does it fill the space purposefully, does it complement their visual weight? The goal is harmony: elements that breathe together, reinforce each other's purpose, and produce a result that feels intentional at every level.

Practically, this means:
- **Size elements relative to their context.** A fill that covers the entire board interior, a bar whose width matches the column it sits in, a title whose length fits its border — these choices signal craft. Mismatched sizes signal accidents.
- **Respect the space.** Padding, gaps, and empty rows serve a purpose: they separate ideas and give the eye room to parse structure. Dense boards read as noise; well-considered boards read as intentional design.
- **Layer with intent.** Fills create atmosphere. Labels create meaning. Borders create containment. When all three serve the same composition, the piece elevates. Each layer must respect the others: fills stay inside borders, labels occupy clear space.
- **Work with the engine.** The engine handles borders, alignment, and compositing. Lean into what it guarantees: perfect borders, smart merging, z-order rendering. Let the pipeline do the counting.

## Hard-won lessons

### Board inner dimensions — do the math every time

Content placed past the inner boundary renders past the border.

```
bordered board (default pad=1):  inner_w = w - 4,  inner_h = h - 4
borderless board (pad=0):        inner_w = w,      inner_h = h
```

Verify every child fits: `x + child_w <= inner_w` and `y + child_h <= inner_h`. A full-interior fill for a `"w": 40, "h": 20` bordered board is `"w": 36, "h": 16`.

### Render order is z-order

In boards, later children render on top. Place fills BEFORE labels so text appears on shading.

### Double-width Unicode

Mystical/emoji/CJK characters render 2 cells wide. One symbol per label on boards. The engine measures correctly via `unicodedata.east_asian_width()` — trust it, but give each wide character its own label.

### Waveforms

Use ONLY `╱` and `╲`. Keep `─` separate: it connects at a different height within a cell.

### Legend uses `entries`

The field is `entries` (easily confused with `items`).

### Mirrored gradients need explicit characters

Fill gradients use `int()` to map chars across the width, which floors the index. The first character always gets more columns than the last. Two fills with reversed chars (`" ░▒▓"` and `"▓▒░ "`) produce different density distributions, each biased toward its own first character. For symmetric gradients, use a single label with hand-typed characters.

### Spaces inside centered labels break centering

`align: center` centers the full string including leading/trailing whitespace. A label with 4 leading spaces and 0 trailing spaces will appear shifted. Keep decorative text symmetric or omit padding characters entirely and let the natural gap between the border and the first visible character serve as the fade.

### Canvas circles need 2× radius margin in x

The engine's circle aspect correction stretches circles horizontally so they look circular on screen. A circle with radius `r` extends ~`2r` subpixels in x but only `r` in y. When placing circles near canvas edges, budget margins of `2r` in x and `r` in y from the boundary. Circles at the exact edge will clip on the wider axis.

### Verify coordinates with code

Verify complex board alignment with code:
```python
for j, ch in enumerate(line):
    if ch != ' ':
        print(f"  char '{ch}' at x={j}")
```

## Keeping docs in sync

When you change the engine (new element types, new props, layout behavior), update in order:
1. `PROJECTOR-GUIDE.md` — full reference
2. `SHOWCASE.md` — if output changes visually
3. `README.md` — only if the public pitch changes
