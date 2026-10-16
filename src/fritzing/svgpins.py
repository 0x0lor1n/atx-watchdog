"""Connector centres in a Fritzing part SVG, in scene pixels (90 dpi).

Fritzing places a part by its SVG's top-left corner; a connector's position is
the centre of the element whose id is the connector's svgId (or legId).
"""

import math
import re
import xml.etree.ElementTree as ET

SCENE_DPI = 90.0
NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def _units_to_in(v):
    m = re.fullmatch(r"\s*(" + NUM + r")\s*([a-z%]*)\s*", v)
    n, u = float(m.group(1)), m.group(2)
    # Unitless sizes are 90 dpi in Fritzing (Inkscape 0.4x legacy).
    return n * {"in": 1, "mm": 1 / 25.4, "cm": 1 / 2.54, "pt": 1 / 72, "px": 1 / 90, "": 1 / 90}[u]


def _mul(a, b):
    return (
        a[0] * b[0] + a[2] * b[1],
        a[1] * b[0] + a[3] * b[1],
        a[0] * b[2] + a[2] * b[3],
        a[1] * b[2] + a[3] * b[3],
        a[0] * b[4] + a[2] * b[5] + a[4],
        a[1] * b[4] + a[3] * b[5] + a[5],
    )


IDENTITY = (1, 0, 0, 1, 0, 0)


def _transform(s):
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        a = [float(x) for x in re.findall(NUM, args)]
        if name == "translate":
            t = (1, 0, 0, 1, a[0], a[1] if len(a) > 1 else 0)
        elif name == "scale":
            t = (a[0], 0, 0, a[1] if len(a) > 1 else a[0], 0, 0)
        elif name == "matrix":
            t = tuple(a)
        elif name == "rotate":
            r = math.radians(a[0])
            c, s_ = math.cos(r), math.sin(r)
            t = (c, s_, -s_, c, 0, 0)
            if len(a) == 3:
                t = _mul(_mul((1, 0, 0, 1, a[1], a[2]), t), (1, 0, 0, 1, -a[1], -a[2]))
        else:
            raise ValueError(name)
        m = _mul(m, t)
    return m


def _apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _path_points(d):
    toks = re.findall(r"[A-Za-z]|" + NUM, d)
    pts, i, cmd, x, y, sx, sy = [], 0, None, 0.0, 0.0, 0.0, 0.0
    arity = dict(M=2, L=2, T=2, H=1, V=1, C=6, S=4, Q=4, A=7, Z=0)
    while i < len(toks):
        if re.fullmatch("[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                x, y = sx, sy
                continue
        n = arity[cmd.upper()]
        a = [float(t) for t in toks[i : i + n]]
        i += n
        rel = cmd.islower()
        U = cmd.upper()
        if U == "H":
            x = x + a[0] if rel else a[0]
        elif U == "V":
            y = y + a[0] if rel else a[0]
        elif U == "A":
            x, y = (x + a[5], y + a[6]) if rel else (a[5], a[6])
        else:
            for k in range(0, n, 2):
                px, py = (x + a[k], y + a[k + 1]) if rel else (a[k], a[k + 1])
                pts.append((px, py))
            x, y = pts[-1]
        pts.append((x, y))
        if U == "M":
            sx, sy = x, y
            cmd = "l" if rel else "L"
    return pts


def _local_points(e):
    tag = e.tag.split("}")[-1]
    g = lambda k, d=0.0: float(re.match(NUM, e.get(k, str(d))).group(0))
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        return [(x, y), (x + w, y + h), (x + w, y), (x, y + h)]
    if tag == "circle":
        cx, cy, r = g("cx"), g("cy"), g("r")
        return [(cx - r, cy - r), (cx + r, cy + r), (cx + r, cy - r), (cx - r, cy + r)]
    if tag == "ellipse":
        cx, cy, rx, ry = g("cx"), g("cy"), g("rx"), g("ry")
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag == "line":
        return [(g("x1"), g("y1")), (g("x2"), g("y2"))]
    if tag in ("polygon", "polyline"):
        n = [float(v) for v in re.findall(NUM, e.get("points", ""))]
        return list(zip(n[::2], n[1::2], strict=True))
    if tag == "path":
        return _path_points(e.get("d", ""))
    return []


def _bbox(e, m):
    m = _mul(m, _transform(e.get("transform")))
    pts = [_apply(m, *p) for p in _local_points(e)]
    for c in e:
        b = _bbox(c, m)
        if b:
            pts += [(b[0], b[1]), (b[2], b[3])]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def load(path):
    """Return (size_px, {id: (x, y)}, {id: ((x1,y1),(x2,y2))} for legs)."""
    root = ET.parse(path).getroot()
    vb = [float(v) for v in re.findall(NUM, root.get("viewBox"))]
    w_in, h_in = _units_to_in(root.get("width")), _units_to_in(root.get("height"))
    s = (w_in * SCENE_DPI / vb[2], h_in * SCENE_DPI / vb[3])
    base = (s[0], 0, 0, s[1], -vb[0] * s[0], -vb[1] * s[1])
    centres, lines = {}, {}

    def walk(e, m):
        m2 = _mul(m, _transform(e.get("transform")))
        i = e.get("id")
        if i:
            tag = e.tag.split("}")[-1]
            if tag == "line":
                g = lambda k: float(e.get(k))
                lines[i] = (_apply(m2, g("x1"), g("y1")), _apply(m2, g("x2"), g("y2")))
            b = _bbox(e, m)
            if b:
                centres[i] = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        for c in e:
            walk(c, m2)

    walk(root, base)
    return (w_in * SCENE_DPI, h_in * SCENE_DPI), centres, lines
