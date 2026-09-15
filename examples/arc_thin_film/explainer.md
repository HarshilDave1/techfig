---
title: Anti-Reflective Coatings: Physics and Parametric Design
status: Established
refs: [{"n": 1, "doi": "10.xxxx/todo.arc.principles", "text": "TODO: Rayleigh, L. On the Reflection of Light from Certain Surfaces. Proc. Roy. Soc. 1886."}, {"n": 2, "doi": "10.xxxx/todo.optical.thinfilms", "text": "TODO: Heavens, O. S. Optical Properties of Thin Solid Films. Dover Publications, 1991."}]
---

# Principle of Thin-Film Interference
> status: Established

When light propagates from air into a dielectric substrate such as optical glass, a fraction of the incident power is reflected at the boundary. An anti-reflective coating (ARC) introduces an intermediate thin film of refractive index $n_1$ and physical thickness $d$ between air ($n_0 = 1.0$) and glass ($n_2 = 1.5$). Reflections from the upper (air–film) and lower (film–substrate) interfaces interfere destructively when the round-trip phase shift equals $\pi$, canceling reflection at the design wavelength [^1].

```techfig
file: spec.json
```
Caption: Figure 1. Static cross-section and baseline reflectance of a single-layer dielectric film on glass.

# Spectral Response and Airy Formula
> status: Established

At normal incidence, the total power reflectance $R$ of a single non-absorbing film is governed by the Airy formula:

$$R = \frac{r_{01}^2 + r_{12}^2 + 2 r_{01} r_{12} \cos(2\delta)}{1 + r_{01}^2 r_{12}^2 + 2 r_{01} r_{12} \cos(2\delta)}$$

where $r_{01} = (n_0 - n_1)/(n_0 + n_1)$, $r_{12} = (n_1 - n_2)/(n_1 + n_2)$, and the optical phase thickness is $\delta = 2\pi n_1 d / \lambda$. Because the phase shift $\delta$ depends inversely on wavelength $\lambda$, single-layer coatings exhibit a characteristic minimum in reflectance near the design wavelength $\lambda_0 = 4 n_1 d$.

```techfig interactive
file: spec.json
```
Caption: Figure 2. Interactive ARC explorer: adjust refractive index $n_1$, thickness $d$, wavelength $\lambda$, or toggle coating state.

# Optimization and Physical Limitations
> status: Established

Zero reflectance at the design wavelength requires both ideal destructive phase ($\delta = \pi/2$, or $d = \lambda_0 / 4n_1$) and amplitude matching ($r_{01} = r_{12}$), yielding the classic condition $n_1 = \sqrt{n_0 n_2} \approx 1.225$ for crown glass [^2]. In practice, robust low-index optical materials such as magnesium fluoride ($\text{MgF}_2$, $n_1 \approx 1.38$) achieve residual reflectance below $1.5\%$ across the visible band.
