"""Example: Render LaTeX equations to SVG/PNG via matplotlib mathtext.

Run:  python examples/make_equation.py
Outputs land in ./output/equations/
"""
import os

from techfig.engines.equations import render_equation

OUT_DIR = os.path.join("output", "equations")
os.makedirs(OUT_DIR, exist_ok=True)

# A curated set of common scientific formulas rendered across styles.
EQUATIONS = [
    (r"\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}", "maxwell_gauss", "nature"),
    (r"\nabla \times \mathbf{B} = \mu_0 \mathbf{J} + \mu_0 \varepsilon_0 \frac{\partial \mathbf{E}}{\partial t}", "maxwell_ampere", "nature"),
    (r"e^{i\pi} + 1 = 0", "euler_identity", "science"),
    (r"i\hbar \frac{\partial}{\partial t}\Psi(\mathbf{r},t) = \hat{H}\Psi(\mathbf{r},t)", "schrodinger", "ieee"),
    (r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}", "gaussian_integral", "optica"),
    (r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}", "basel_problem", "minimal"),
    (r"\left(\frac{a}{b}\right)^2 = \frac{a^2}{b^2}", "fraction_square", "presentation"),
]

for latex, name, style in EQUATIONS:
    out = os.path.join(OUT_DIR, f"{name}.svg")
    path = render_equation(latex, out, style_name=style)
    print(f"  {style:<13} {name:<18} -> {path}")

# PNG with explicit DPI override
png_out = os.path.join(OUT_DIR, "euler_identity.png")
path = render_equation(r"e^{i\pi} + 1 = 0", png_out, style_name="dark", dpi=300)
print(f"  {'dark (png)':<13} {'euler_identity':<18} -> {path}")

print(f"\nDone. {len(EQUATIONS) + 1} equations rendered to {OUT_DIR}/")
