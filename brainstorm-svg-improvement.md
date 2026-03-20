# Brainstorm: Recursive SVG & Schematic Improvement
Date: 2026-03-17

## Idea: Autoresearch for Graphics
Applying Karpathy's `autoresearch` logic (autonomous experimentation loop) to the `graphic_agent` pipeline. https://github.com/karpathy/autoresearch

### The Loop
1.  **Program/Directive:** "Improve the aesthetic of this schematic to match a high-fidelity 'NotebookLM' 3D-isometric look, while maintaining mathematical precision in alignment."
2.  **Hypotheses:** Agent generates variations of the JSON diagram spec (colors, materials, lighting, layout, camera angles, coordinates).
3.  **Experiment:** Render SVG (using `diagrams.py`) or generate PNG (using `nano-banana-pro`).
4.  **Evaluation (The "Dual Critic"):** 
    *   **Geometric Critic:** Vision model/code linter checks for perfect alignment. Are arrows horizontal? Are gaps identical? Are labels centered?
    *   **Aesthetic Critic:** Vision model scores the output against the target style (1-10 scale). Provides "gradient feedback" on lighting/colors.
5.  **Iteration:** Keep the top-scoring spec and mutate it further.

### Geometric Optimization & Precision
Aesthetic polish without precision is just a "pretty mess." We need a dedicated geometric pass:
*   **Snap-to-Grid:** Automatic rounding of `x, y, w, h` to a consistent 20px or 50px grid.
*   **Alignment Constraints:** Force identical Y-coordinates for elements in the same row; identical X-coordinates for elements in the same column.
*   **Connection Locking:** Arrows must snap to exact centers or midpoints of target boundaries, never just "pointing near" them.

### Hybrid Workflow: The `--pretty` Flag
The `graphic_agent` should support a tiered output:
*   **Precision (Default):** Returns clean, editable SVG. Functional for repos and technical docs.
*   **Aesthetic (`--pretty`):** Uses the SVG spec + descriptive prompt as input for `nano-banana-pro`. Generates a high-fidelity PNG with "Visual Metaphor" styling (isometric, glass-morphism, studio lighting).

### Self-Improvement Integration (Sage)
The **Self-Improvement Agent (`sage`)** should monitor the results over time:
*   **Pattern Detection:** If a certain diagram type consistently has "wonky arrows," `sage` flags the failure.
*   **Recursive Prompt Engineering:** `sage` automatically updates the `SKETCH_PROMPT` in `sketch_interpreter.py` with stricter rules or better examples based on past successes/failures.

### Why it makes sense
*   **Aesthetic is High-Dimensional:** There are thousands of color/spacing/size combinations.
*   **Precision is Rule-Based:** Alignment can be enforced by a "linter" before rendering.
*   **Recursive Feedback:** Combining a "Geometry Critic" with an "Aesthetic Critic" ensures the output is both professional and accurate.

### Next Steps
1.  [x] Prototype a "Geometric Linter" script to snap JSON specs to a grid.
2.  [x] Test the "Pretty" image-to-image workflow using a current SVG as a seed for `nano-banana-pro`.
3.  [x] Create a unified "Critic" prompt that handles both alignment and aesthetic scoring.
4.  [x] Pilot a "5-round sprint" on a standard photonic circuit diagram.
