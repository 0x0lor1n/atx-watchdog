"""Lint a bench sketch against its schematic, using only what Fritzing drew.

  fzgen-lint <sketch.fzz> <sketch_breadboard.svg> <sketch.nets.json>

The SVG is Fritzing's own export (Fritzing -svg). Fritzing trusts the
<connects> saved in a .fzz and does not re-derive them from geometry, so
this reads geometry only: which pin or leg end sits in which hole, where each
wire ends. From that it builds the nets through the breadboard strips and
compares them with the expected nets that Sketch.save wrote. Exit 1 on any finding.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET

from . import svgpins as sp

TOL = 0.03 * sp.SCENE_DPI  # a pin is "in" a hole within 0.03 in
SVG = "{http://www.w3.org/2000/svg}"


def tag(e):
    return e.tag.split("}")[-1]


def centre(e, m):
    b = sp._bbox(e, m)
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) if b else None


def parts_from_svg(path):
    """{part_id: {"pins": {svgId: xy}, "legs": [(start, end)], "wire": (a, b) | None}}"""
    root = ET.parse(path).getroot()
    vb = [float(v) for v in re.findall(sp.NUM, root.get("viewBox"))]
    sx = sp._units_to_in(root.get("width")) * sp.SCENE_DPI / vb[2]
    sy = sp._units_to_in(root.get("height")) * sp.SCENE_DPI / vb[3]
    base = (sx, 0, 0, sy, -vb[0] * sx, -vb[1] * sy)
    out = {}
    rec = None
    for g in root:
        pid = g.get("partID")
        if pid is None:
            # Bent legs are drawn as root-level paths right after their part.
            if rec is not None and tag(g) == "path":
                leg = _leg(g, base)
                if leg:
                    rec["legs"].append(leg)
            continue
        rec = out[int(pid)] = {"pins": {}, "legs": [], "wire": None}

        def walk(e, m, rec=rec):
            m2 = sp._mul(m, sp._transform(e.get("transform")))
            i = e.get("id") or ""
            if re.fullmatch(r"connector\d+pin|pin\d+[A-Z]", i):
                rec["pins"][i] = centre(e, m)
            if tag(e) == "line" and rec["wire"] is None and not rec["pins"]:
                x1, y1, x2, y2 = (float(e.get(k)) for k in ("x1", "y1", "x2", "y2"))
                rec["wire"] = (sp._apply(m2, x1, y1), sp._apply(m2, x2, y2))
            for c in e:
                walk(c, m2)

        walk(g, base)
    return out


def _leg(e, m):
    """An opaque two-point path (the leg itself, not its translucent
    green/red connection highlight), as (start, end) in scene px."""
    if e.get("opacity", "1") != "1" or e.get("stroke", "").lower() in (
        "#00ff00",
        "#ff0000",
        "none",
        "",
    ):
        return None
    pts = sp._path_points(e.get("d", ""))
    pts = [p for k, p in enumerate(pts) if k == 0 or p != pts[k - 1]]
    if len(pts) != 2:
        return None
    m2 = sp._mul(m, sp._transform(e.get("transform")))
    return sp._apply(m2, *pts[0]), sp._apply(m2, *pts[1])


def instances(fzz):
    import zipfile

    z = zipfile.ZipFile(fzz)
    fz = z.read(next(n for n in z.namelist() if n.endswith(".fz"))).decode()
    res = {}
    for m in re.finditer(
        r'<instance moduleIdRef="([^"]+)" modelIndex="(\d+)"[^>]*>.*?<title>([^<]*)</title>',
        fz,
        re.S,
    ):
        res[int(m[2])] = (m[1], m[3])
    return res


def near(p, q):
    return abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL


def main(fzz, svg, nets_json):
    with open(nets_json) as f:
        exp = json.load(f)
    inst = instances(fzz)
    drawn = parts_from_svg(svg)
    findings = []

    # Fritzing's item id is modelIndex * 10.
    title = {pid: inst[pid // 10][1] for pid in drawn if pid // 10 in inst}
    kind = {pid: inst[pid // 10][0] for pid in drawn if pid // 10 in inst}
    bb_pid = next(p for p, k in kind.items() if k.endswith("BreadboardModuleID"))
    bb = title[bb_pid]
    holes = {i: xy for i, xy in drawn[bb_pid]["pins"].items() if re.fullmatch(r"pin\d+[A-Z]", i)}
    svgid_to_conn = exp["svgids"]  # title -> {svgId: connectorId}

    def hole_at(p):
        hs = [h for h, xy in holes.items() if near(p, xy)]
        return hs[0] if len(hs) == 1 else None

    ends = {}  # (title, connector) -> xy
    for pid, rec in drawn.items():
        if pid == bb_pid or kind.get(pid) in (None, "WireModuleID", "NoteModuleID"):
            continue
        t = title[pid]
        conn_of = svgid_to_conn.get(t, {})
        pins = {conn_of.get(s, s): xy for s, xy in rec["pins"].items() if xy}
        legged = set()
        for a, b in rec["legs"]:
            c = min(pins, key=lambda k: (pins[k][0] - a[0]) ** 2 + (pins[k][1] - a[1]) ** 2)
            if c in legged:
                findings.append(f"{t}: two legs match {c}")
            legged.add(c)
            ends[(t, c)] = b
        for c, xy in pins.items():
            if c not in legged:
                ends[(t, c)] = xy

    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    plugged = {}
    for key, xy in ends.items():
        h = hole_at(xy)
        find(key)
        if h:
            union(key, (bb, h))
            plugged[key] = h

    for pid, rec in drawn.items():
        if kind.get(pid) != "WireModuleID" or not rec["wire"]:
            continue
        t = title[pid]
        for k, p in enumerate(rec["wire"]):
            hits = [("hole", h) for h, xy in holes.items() if near(p, xy)]
            hits += [("pin", key) for key, xy in ends.items() if near(p, xy)]
            if not hits:
                findings.append(f'wire "{t}" end {k} at ({p[0]:.1f},{p[1]:.1f}) touches nothing')
            for what, x in hits:
                union((t, k), (bb, x) if what == "hole" else x)
        union((t, 0), (t, 1))

    for bus in exp["buses"]:
        for h in bus[1:]:
            union((bb, bus[0]), (bb, h))

    for pid, rec in drawn.items():
        for _, b in rec["legs"]:
            if not hole_at(b):
                findings.append(f"{title.get(pid, pid)}: leg ends at ({b[0]:.1f},{b[1]:.1f}), not in a hole")

    seen = {}
    for name, members in exp["nets"].items():
        roots = {}
        for t, c in members:
            if (t, c) not in ends:
                findings.append(f"net {name}: {t} {c} not found in the drawing")
                continue
            roots.setdefault(find((t, c)), []).append(
                f"{t} {c}" + (f" ({plugged[(t, c)]})" if (t, c) in plugged else "")
            )
        if len(roots) > 1:
            findings.append(f"net {name} is split: " + " | ".join(", ".join(v) for v in roots.values()))
        for r in roots:
            if r in seen and seen[r] != name:
                findings.append(f"nets {seen[r]} and {name} are shorted")
            seen[r] = name

    for f in findings:
        print(f"{fzz}: {f}")
    if not findings:
        print(f"{fzz}: {len(exp['nets'])} nets OK, {len(plugged)} pins/legs in holes")
    return 1 if findings else 0


def cli():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
