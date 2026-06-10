# sketchpad-mcp

A visual input tool for AI coding agents. You sketch; the agent reads the sketch.

Most MCP drawing tools go **agent → human** (the agent generates a diagram for you to view). This one goes the other way: **human → agent**. Open a canvas, draw your idea, and the resulting image lands directly in the agent's context.

---

## How it works

1. The agent calls `open_canvas` (or you ask it to: *"open the canvas, I want to sketch this"*)
2. A drawing tab opens in your default browser — powered by [Excalidraw](https://excalidraw.com/)
3. You sketch, paste, or annotate
4. Click **Send to Claude** — the PNG is returned directly to the agent
5. The tab stays open; the agent can call the tool again and your drawing is still there to refine

---

## Requirements

- Python 3.10+
- Claude Code (CLI)

---

## Installation

**1. Clone and install dependencies**

```bash
git clone https://github.com/kennycornellius-collab/sketchpad-mcp.git
cd sketchpad-mcp
pip install -e .
```

**2. Register with Claude Code**

```bash
claude mcp add canvas --transport stdio --scope user -- python -m canvas_mcp
```

Use the `python` from the environment where you ran `pip install` (e.g. the absolute path to your venv's `python`). Alternatively, the install provides a `canvas-mcp` console command you can register instead of `python -m canvas_mcp`.

**3. Verify it's registered**

```bash
claude mcp list
```

You should see `canvas` in the list.

---

## Usage

Once registered, the tools are available in any Claude Code session.

**Let the agent decide** — Claude Code will open the canvas on its own when your description is ambiguous or visual.

**Ask explicitly:**

> "Open the canvas, I want to sketch the layout."

> "Draw me a rough wireframe and send it over."

The canvas tab stays alive across calls in the same session — you can refine the same drawing across multiple back-and-forths without losing your work.

---

## Tools

### `open_canvas`

Opens the Excalidraw canvas and returns the sketch as a PNG image directly into the agent's context.

Use this when the agent can accept images (Claude Code always can).

**Optional parameter:** `hint` — a short reminder shown above the canvas (e.g. *"Sketch the dashboard layout"*).

### `describe_sketch`

Same canvas flow, but returns the PNG **and** a text description of what you drew.

Use this when you want a reusable text representation of the sketch alongside the image — useful for saving the description to a file or passing it to a non-vision step later.

---

## Canvas controls

The canvas is a full Excalidraw instance — shapes, arrows, text, freehand, colors, undo/redo all work. A few things specific to canvas-mcp:

- **Send to Claude** — submits the current canvas state as a PNG
- **Close tab** — closes the browser tab when you're done with the session

---

## License

MIT. See [LICENSE](LICENSE).

Built with assistance from [Claude Code](https://claude.ai/code). Excalidraw embedded via CDN under its [MIT license](https://github.com/excalidraw/excalidraw/blob/master/LICENSE).

---

## Other clients

canvas-mcp uses standard MCP stdio transport, so it should work with Cursor, Zed, Claude Desktop, and any other MCP-compatible coding agent. If you try it on one of those and want to help document the setup, feel free to open an issue or reach out — happy to add verified setup snippets for other clients.
