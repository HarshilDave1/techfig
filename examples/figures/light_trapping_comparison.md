# Light Trapping in Photonic Crystal Solar Cells: Figure Generation Comparison

## Side-by-Side: techfig SVG pipeline vs Venice gpt-image-2

### techfig (SVG pipeline → PNG)

![techfig light trapping](light_trapping_pc_solar_cell_fig1_techfig.png)

### Venice gpt-image-2

![Venice gpt-image-2 light trapping](light_trapping_pc_solar_cell_fig1_venice_gpt_image_2.png)

---

## Comparison

| Dimension | techfig (SVG pipeline) | Venice gpt-image-2 |
|---|---|---|
| **Method** | Hand-authored JSON spec → deterministic SVG render → geo linter → critique → cairosvg PNG | Single text prompt → diffusion model → raster PNG |
| **Generation time** | ~2 seconds (render + convert) | ~90 seconds (API call) |
| **Output format** | SVG (vector, infinitely scalable) + PNG | PNG only (raster, fixed resolution) |
| **File size** | 11 KB SVG / 73 KB PNG | 963 KB PNG |
| **Text legibility** | Clean, crisp — every label placed by coordinate | Clean, crisp — gpt-image-2 handled text well |
| **Text accuracy** | Exact — labels are authored in the spec | Mostly accurate — no garbled text, but model invented extra labels ("Periodic in x,y,z", diffraction orders, legend) |
| **Formula correctness** | Correct: `4n²·d` (path length limit), `A_PC/A_planar >> 1` | **Conceptual error**: wrote `A_Lambertian,max = 4n²d/d = 4n²` — equates absorptance (must be ≤1) to the path length enhancement factor (dimensionless ~51.8 for Si). The `d/d` cancellation is also nonsensical. |
| **Scientific accuracy** | Ray paths don't perfectly terminate inside absorber (conceptual limitation of simple spec) — but core physics is correct | More visually detailed (diffraction orders, internal reflections, 3D unit cell) but introduced a real physics error in the Lambertian formula |
| **Visual polish** | Functional, clean schematic — adequate for technical documentation | Highly polished, journal-quality visual style with gradients, 3D effects, professional layout |
| **Editability** | Change one JSON coordinate → re-render. Full control over every element. | Must re-generate from scratch; cannot edit individual elements |
| **Determinism** | Same spec → identical output, every time | Same prompt → different output each time |
| **Compute cost** | ~1 LLM call (if using LLM spec gen) + milliseconds CPU | Heavy GPU diffusion (~90 seconds) |
| **Development cost** | High (pipeline must be built and maintained) | Zero (API call) |

---

## Key Observations

### What gpt-image-2 does better
- **Visual polish**: The diffusion model produces a journal-quality figure with gradients, 3D sphere rendering, professional typography, and a sophisticated layout that looks like it came from *Nature Photonics*. The techfig output is functional but visually plain by comparison.
- **Richness of detail**: The model added useful scientific details not in the prompt — diffraction order labels (m=0,±1,±2), a 3D unit cell diagram with lattice constant Λ, a legend defining arrow styles, and a definitions box for variables. These enrich the figure without being asked.

### What gpt-image-2 does worse
- **Scientific correctness**: The model made a real physics error in the Lambertian limit formula. It wrote `A_Lambertian,max = 4n²d/d = 4n²`, which conflates absorptance (a ratio ≤1) with the optical path length enhancement factor (dimensionless, ~51.8 for silicon). The `d/d` cancellation is also mathematically nonsensical as written. This is the kind of error that would be caught in peer review but could mislead students.
- **Controllability**: You cannot fix this error by editing the image. The only option is to re-generate with a modified prompt and hope the model doesn't introduce a different error. With techfig, you change one string in the JSON and re-render.
- **Cost**: 963 KB raster vs 11 KB vector. 90 seconds vs 2 seconds. No edit path vs full editability.

### What techfig does better
- **Precision and correctness**: The formulas say exactly what you wrote. No model hallucination. No conflation of absorptance with path length enhancement.
- **Editability**: The spec is a reusable, version-controllable artifact. Anyone can modify it, and the output is deterministic.
- **Lightweight**: 11 KB SVG that scales to any resolution. 2 seconds to render. No GPU needed.

### The fundamental tradeoff
gpt-image-2 produces **more beautiful but less trustworthy** figures. techfig produces **less beautiful but exactly correct** figures. For a textbook illustration where visual impact matters most, gpt-image-2 wins. For a technical document where every label and formula must be verifiably correct and editable, techfig wins.

The ideal pipeline would combine both: use diffusion models for visual styling and layout inspiration, then author the final figure as a precise, editable SVG spec. Or: use gpt-image-2 for first drafts, then verify and correct via a deterministic pipeline.
