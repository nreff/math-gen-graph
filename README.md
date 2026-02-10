# math-gen-graph

Beautiful interactive and static visualizations of mathematician advisor-advisee genealogies, powered by data from the [Mathematics Genealogy Project](https://www.mathgenealogy.org/).

## Features

- **Interactive HTML graphs** -- zoom, pan, drag nodes, hover for details, search by name or institution, click legend entries to filter
- **Wikipedia links** -- click any node to see a "View on Wikipedia" link (when available) in the detail panel
- **Country flags** -- historically accurate country flags displayed next to institution names, sourced from Wikidata
- **Generation & century overlays** -- toggleable horizontal bands showing generation levels and century boundary lines
- **Multi-root graphs** -- combine multiple starting mathematicians with automatic tree separation and highlighted common ancestors
- **Static image export** -- high-quality PNG and SVG output via Graphviz (SVG nodes link to Wikipedia)
- **3 built-in themes** -- dark (neon/vibrant), light (clean pastels), and academic (elegant serif)
- **Color coding** -- nodes colored by institution, era, or tree depth
- **Multiple layouts** -- hierarchical (top-down tree), force-directed, or radial
- **Local enrichment cache** -- Wikidata results are cached at `~/.math-gen-graph/cache.json` so subsequent runs are instant

## Installation

Requires Python >= 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd math-gen-graph
uv sync
```

For static image output (PNG/SVG), you also need [Graphviz](https://graphviz.org/download/) installed:

- **Windows:** `winget install graphviz`
- **macOS:** `brew install graphviz`
- **Linux:** `sudo apt install graphviz`

Interactive HTML output works without Graphviz.

## Usage

```bash
# Carl Gauss's advisor lineage, dark theme, interactive HTML
uv run math-gen-graph 18231:a --theme dark -o gauss.html

# Same graph as a static SVG with academic styling
uv run math-gen-graph 18231:a --format svg --theme academic -o gauss.svg

# Euler + Gauss combined, force layout, colored by era
uv run math-gen-graph 18231:a 38586:a --layout force --color-by era -o combined.html

# Skip Wikidata enrichment (faster, no Wikipedia links or flags)
uv run math-gen-graph 18231:a --no-enrich -o gauss_quick.html

# Force a fresh enrichment cache
uv run math-gen-graph 18231:a --clear-cache -o gauss.html
```

### Start Node Format

Each positional argument is `ID:DIRECTION` where:

- `ID` is the mathematician's numeric ID from the [Mathematics Genealogy Project](https://www.mathgenealogy.org/) (found in the URL of their record)
- `DIRECTION` is `a` (advisors), `d` (descendants), or `ad` (both)

### Options

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--format` / `-f` | `html`, `png`, `svg` | `html` | Output format |
| `--theme` / `-t` | `dark`, `light`, `academic` | `light` | Visual theme |
| `--color-by` / `-c` | `institution`, `era`, `depth` | `institution` | Node color coding |
| `--layout` / `-l` | `hierarchical`, `force`, `radial` | `hierarchical` | Graph layout algorithm |
| `--output` / `-o` | file path | `genealogy.{format}` | Output file path |
| `--quiet` / `-q` | | | Suppress progress bar |
| `--no-enrich` | | | Skip Wikidata enrichment (no Wikipedia links or flags) |
| `--clear-cache` | | | Clear the enrichment cache before running |

## Interactive Features

When you open an HTML output file in your browser, you get:

- **Sidebar** with search, color legend, overlay toggles, and a node detail panel
- **Search** -- type to filter nodes by name or institution
- **Legend** -- click any legend entry to highlight nodes in that group
- **Overlays** -- toggle Generation Levels (horizontal bands showing each generation) and Century Lines (dashed horizontal lines marking century boundaries)
- **Node detail panel** -- click any node to see name, institution (with country flag), year, advisor/student counts, MGP link, and Wikipedia link
- **Controls** -- "Fit" to re-center the view, "Toggle Physics" to freeze/unfreeze the layout

### Multi-Root Graphs

When you provide multiple starting IDs, the tool automatically:

1. Identifies which nodes are exclusive to each tree vs. shared common ancestors
2. Separates the distinct branches so they don't overlap
3. Highlights shared ancestors with a colored border

## Themes

**Dark** -- deep navy background with vibrant, neon-accented nodes and glowing edges. Great for presentations.

**Light** -- clean white background with pastel institution colors and modern sans-serif typography. Good default for exploration.

**Academic** -- cream parchment background with muted earth tones and serif fonts. Ideal for papers and formal use.

## How It Works

1. **Fetch** -- Graph data is fetched from the [Geneagrapher](https://github.com/davidalber/geneagrapher) backend service via WebSocket
2. **Enrich** -- Unique person names and institution names are batch-queried against [Wikidata](https://www.wikidata.org/) via SPARQL to find Wikipedia article links, institution countries, and historically accurate flags. Results are cached locally at `~/.math-gen-graph/cache.json`
3. **Build** -- A NetworkX directed graph is constructed with metadata (generation depth, era, institution frequency, tree membership)
4. **Render** -- The graph is rendered with either [vis.js](https://visjs.org/) (interactive HTML) or [Graphviz](https://graphviz.org/) (static images)

## License

MIT
