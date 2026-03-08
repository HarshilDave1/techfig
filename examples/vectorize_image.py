"""Example: Convert a raster image to an editable SVG."""
from techfig.engines.vectorize import vectorize_image, vectorize_with_preset

# --- Using a preset (easiest) ---
# Presets: "detailed", "simplified", "sketch", "logo"

# For a hand-drawn sketch → clean black & white SVG:
# output = vectorize_with_preset("my_sketch.png", "output/sketch.svg", preset="sketch")

# For a full-color photo → high-fidelity vector:
# output = vectorize_with_preset("photo.jpg", "output/photo.svg", preset="detailed")

# For a logo/icon → bold, simplified shapes:
# output = vectorize_with_preset("logo.png", "output/logo.svg", preset="logo")


# --- Fine-grained control ---
# output = vectorize_image(
#     "input.png",
#     "output/result.svg",
#     color_mode="color",       # "color" or "binary" (B&W)
#     color_precision=6,        # 1-8, fewer = simpler SVG
#     filter_speckle=4,         # remove noise speckles
#     mode="spline",            # "polygon" or "spline" (smooth curves)
# )


# --- Quick demo (generates a test image first) ---
if __name__ == "__main__":
    # Create a small test PNG using matplotlib
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(4, 4))
    theta = np.linspace(0, 2 * np.pi, 100)
    ax.plot(np.cos(theta), np.sin(theta), "b-", linewidth=3)
    ax.set_aspect("equal")
    ax.set_title("Circle")
    fig.savefig("/tmp/test_circle.png", dpi=150)
    plt.close()

    output = vectorize_with_preset("/tmp/test_circle.png", "output/circle_vector.svg", preset="simplified")
    print(f"Vectorized image saved to {output}")
