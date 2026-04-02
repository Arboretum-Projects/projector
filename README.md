# Projector

**A three-pass ASCII/Unicode layout engine.** Models describe structure in JSON. The engine guarantees pixel-perfect alignment.

Python 3.7+. One file.

## How it works

You describe **what** to draw. The Projector handles **how** it renders.

```
JSON spec  ──►  Measure (bottom-up)  ──►  Layout (top-down)  ──►  Render (to canvas)
```

1. **Measure.** Each element reports how big it needs to be
2. **Layout.** Each element is assigned a position
3. **Render.** Elements draw to a 2D character grid with smart compositing

When box-drawing characters overlap, the engine merges them intelligently (`─` meets `│` = `┼`, `═` meets `║` = `╬`). Text always wins over borders. Emoji and CJK characters render at correct display widths.

## Quick start

```bash
# Render from stdin
echo '{"type":"box","title":"Hello","content":"World"}' | python3 projector.py

# Render from file
python3 projector.py spec.json

# Browse all 35 built-in examples
python3 projector.py --examples

# Show JSON + render for one example
python3 projector.py --example dashboard

# ASCII-safe mode (pure ASCII output)
python3 projector.py --ascii < spec.json

# Post-render validation
python3 projector.py --validate < spec.json
```

## What you can build

- **Dashboards.** Status bars, sections, multi-column layouts
- **Game UIs.** Dungeon maps, party stats, inventory, turn logs
- **Flow diagrams.** Nodes, connectors, decision trees
- **Artistic compositions.** Tarot cards, alchemist workshops, fantasy maps
- **Subpixel drawing.** Circles, polygons, bitmap text at 2x-4x resolution via braille and block canvas modes

## Element types

23 element types (with `frame` as a `box` alias):

| Category | Types |
|----------|-------|
| **Containers** | `box`, `row`, `stack`, `group`, `board` |
| **Content** | `label`, `spacer`, `separator`, `legend`, `grid` |
| **Data** | `bar`, `inventory`, `turn_log`, `status_panel` |
| **Spatial** | `minimap`, `hexgrid`, `fill`, `node`, `connector` |
| **Drawing** | `line`, `arrow`, `transition`, `canvas` |

Five border styles: `single`, `double`, `rounded`, `heavy`, `dashed`. Smart merge handles all intersections automatically.

## Built-in examples

35 built-in examples ship with the engine, from minimal boxes to full RPG screens:

```bash
python3 projector.py --examples                # render all 35
python3 projector.py --example garden          # Metatron's Cube sacred garden
python3 projector.py --example flower          # Flower of Life sacred geometry
python3 projector.py --example merkaba         # 3D star tetrahedron
python3 projector.py --example rift            # sacred geometry manifold
python3 projector.py --example fractal         # Sierpinski gasket
python3 projector.py --example alchemist       # mystical workspace
python3 projector.py --example dungeon_crawler  # full game UI
python3 projector.py --example ocean           # underwater scene
python3 projector.py --example circuit         # PCB layout
```

## Documentation

- **[Composition Guide](PROJECTOR-GUIDE.md).** Element reference, composition patterns, and lessons from building 34 examples
- **[Showcase](SHOWCASE.md).** Rendered output gallery demonstrating every element type

## Support

If Projector is useful to you, consider supporting the work: [ko-fi.com/arkitecc](https://ko-fi.com/arkitecc)

## License

Apache 2.0
