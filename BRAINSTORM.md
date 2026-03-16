# TechFig Brainstorming: "Napkin to Nature"

This document captures the brainstorming session around expanding the **TechFig** (Technical Graphic Agent) project. 

## The Core Problem
Scientists spend too much time fighting with visualization tools—especially for conceptual diagrams, physics schematics, and animated slide visuals. Existing AI tools (like NotebookLM or Gamma) generate flat images or marketing decks. TechFig's "code-first" architecture is uniquely positioned to generate mathematically rigorous, **editable** outputs (SVGs, PPTX native objects, Manim animations).

## The Slogan
**"Napkin to Nature"**
*From a rough whiteboard sketch or text description straight to a publication-ready, fully editable diagram.*

## 1. Concept to Diagram (Static & Animated)
The biggest pain point in science communication is drawing explanatory figures (optical setups, biological pathways, etc.) and then having to painstakingly animate them for presentations.
*   **Static (Paper):** The Engine places SVG components and connects them with arrows and LaTeX labels via `drawsvg` or `schemdraw`. Output: `.svg` or `.tex`.
*   **Dynamic (Presentation):** The exact same setup is passed to `manim`. The Engine writes the Python script to animate a photon pulse, fluid flow, or biological mechanism. Output: `.mp4` or `.gif`.

## 2. The "Holy Trinity" Component Library (Asset Layer)
Currently, going from text to diagram with raw SVG primitives can be clunky (LLMs struggle to calculate precise X/Y coordinates for complex shapes). To fix this, TechFig needs a component library so the LLM acts as an "orchestrator" placing Lego blocks, rather than drawing from scratch.

1. **Standard Library:** Ships with (or pulls) open-source domain libraries (e.g., `schemdraw` for physics/circuits, bio-symbols for biology).
2. **Lab Folder:** Scientists drop their custom lab SVGs/PNGs into a local `~/.techfig/components` folder. The CLI automatically indexes them so the agent can use `--component my_laser`.
3. **Agentic Fallback:** If a requested component ("cryostat") is missing, the LLM writes the SVG code from scratch, saves it to the Lab Folder permanently, and then uses it in the diagram. The library gets smarter over time.

## 3. Interactive Data (Why Python > Mathematica)
We discussed integrating Wolfram/Mathematica for interactive equations, but decided against it to avoid proprietary licensing traps. 
Instead, TechFig should leverage the open-source Python ecosystem:
*   **Interactive HTML:** Output standalone interactive HTML widgets using `Plotly` or `Bokeh` with sliders (e.g., to play with equation variables in the browser).
*   **Accuracy:** Use `SymPy` for mathematically flawless symbolic mathematics and derivations without an external API.

## 4. The Ideal Workflow
Building TechFig as a **CLI/MCP tool for other AI agents** (like Claude Code, Cursor, or OpenClaw) is the smartest architecture. 
The LLM serves as the interface (translating a sketch or prompt), and calls the TechFig CLI to execute the deterministic Python engine.

**Example Agentic Loop:**
1. You provide `whiteboard.jpg` and ask Claude: *"Use techfig to turn this into a Nature-styled SVG of the cell membrane, and put it on a 16:9 PPTX slide."*
2. Claude calls `techfig create --input whiteboard.jpg --style nature --format svg,pptx`.
3. TechFig places the components from the library and generates the files.
4. You open `output.pptx` and the SVG is sitting right there, fully editable.

---
*Saved for later review during the Phase 1 (Diagram Engine) implementation.*