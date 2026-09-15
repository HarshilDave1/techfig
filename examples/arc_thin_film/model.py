# ruff: noqa: F821
def R(n0, n1, n2, d, lam):
    r01 = (n0 - n1) / (n0 + n1)
    r12 = (n1 - n2) / (n1 + n2)
    delta = 2 * math.pi * n1 * d / lam
    cosc = math.cos(2 * delta)
    num = r01**2 + r12**2 + 2 * r01 * r12 * cosc
    den = 1 + r01**2 * r12**2 + 2 * r01 * r12 * cosc
    return num / den


def sweep(n1, d, lam_min, lam_max, n):
    xs = []
    ys = []
    step = (lam_max - lam_min) / (n - 1)
    for i in range(n):
        wl = lam_min + i * step
        xs.append(wl)
        ys.append(R(1.0, n1, 1.5, d, wl))
    return [xs, ys]


def R_arc(n1, d, lam):
    return R(1.0, n1, 1.5, d, lam)
