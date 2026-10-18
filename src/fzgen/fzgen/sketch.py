"""A breadboard sketch: placement, net tracing and the .fzz writer."""

import html
import io
import json
import os
import re
import zipfile

from . import svgpins

BB_ID = "0152b316-ca6e-11ee-a6fa-8be78db221f8BreadboardModuleID"  # Half_breadboard_v2

RED, BLACK, YELLOW, GREEN, ORANGE, BLUE = (
    "#cc1414",
    "#404040",
    "#ffe24d",
    "#47cc79",
    "#ef6100",
    "#418dd9",
)


class Inst:
    def __init__(self, sk, module_id, title, path, size, pins, legs=None, props=None):
        self.module_id, self.title, self.path = module_id, title, path
        self.idx = sk.next_index()
        self.size, self.pins, self.legs = size, pins, legs or {}
        self.props = props or {}
        self.pos, self.rot = (0.0, 0.0), 0
        self.leg_end = {}  # connector -> scene point
        self.conns = {}  # connector -> [(other, other_connector, layer)]
        self.z = 2.5
        self.sch = self.pcb = (0, 0)
        self.ends, self.color = [], None  # wires only
        sk.insts.append(self)

    def local_to_scene(self, pt):
        x, y = pt
        if self.rot == -90:  # Qt rotation about the item's centre
            cx, cy = self.size[0] / 2, self.size[1] / 2
            x, y = y + cx - cy, -x + cx + cy
        return self.pos[0] + x, self.pos[1] + y

    def pin_scene(self, c):
        return self.leg_end.get(c) or self.local_to_scene(self.pins[c])

    def place(self, c, target, rot=0):
        """Move so that connector c's centre is at target (scene)."""
        self.rot, self.pos = rot, (0.0, 0.0)
        sx, sy = self.local_to_scene(self.pins[c])
        self.pos = (target[0] - sx, target[1] - sy)

    def connect(self, c, other, oc, layer):
        self.conns.setdefault(c, []).append((other, oc, layer))


class Sketch:
    def __init__(self, parts_dir):
        self.dir = parts_dir
        self.insts, self.notes, self.wires, self._i = [], [], [], 1000
        self.embedded, self.svgids, self.expected = {}, {}, {}
        size, c, _ = svgpins.load(os.path.join(parts_dir, "svg/core/breadboard/Half_breadboard56a.svg"))
        holes = {k: v for k, v in c.items() if re.fullmatch(r"pin\d+[A-JWXYZ]", k)}
        self.bb = Inst(self, BB_ID, "Breadboard1", "core/Half_breadboard_v2.fzp", size, holes)
        self.bb.z = 1.5

    def next_index(self):
        self._i += 1
        return self._i

    def hole(self, name):
        return self.bb.pin_scene(name)

    def core(self, module_id, fzp, title, props=None):
        with open(os.path.join(self.dir, "core", fzp)) as f:
            t = f.read()
        bb = re.search(r"<breadboardView>\s*<layers image=\"([^\"]+)\"", t)[1]
        size, c, lines = svgpins.load(os.path.join(self.dir, "svg/core", bb))
        pins, legs, ids = {}, {}, {}
        for m in re.finditer(r'<connector [^>]*id="([^"]+)".*?<breadboardView>(.*?)</breadboardView>', t, re.S):
            cid, body = m.groups()
            ids[re.search(r'svgId="([^"]+)"', body)[1]] = cid
            pins[cid] = c[re.search(r'svgId="([^"]+)"', body)[1]]
            leg = re.search(r'legId="([^"]+)"', body)
            if leg:
                legs[cid] = lines[leg[1]]
        self.svgids[title] = ids
        return Inst(self, module_id, title, "core/" + fzp, size, pins, legs, props)

    def embed(self, module_id, title, files):
        self.embedded.update(files)
        fzp = next(v for k, v in files.items() if k.startswith("part."))
        bbname = re.search(r"<breadboardView>\s*<layers image=\"breadboard/([^\"]+)\"", fzp)[1]
        size, c, _ = svgpins.load(io.BytesIO(files["svg.breadboard." + bbname].encode()))
        pins, ids = {}, {}
        for m in re.finditer(r'<connector [^>]*id="([^"]+)".*?<breadboardView>(.*?)</breadboardView>', fzp, re.S):
            cid, body = m.groups()
            ids[re.search(r'svgId="([^"]+)"', body)[1]] = cid
            pins[cid] = c[re.search(r'svgId="([^"]+)"', body)[1]]
        self.svgids[title] = ids
        return Inst(self, module_id, title, module_id + ".fzp", size, pins)

    def plug(self, inst, c, hole):
        """inst's connector c sits in a breadboard hole; it must already be there."""
        (x, y), (hx, hy) = inst.pin_scene(c), self.hole(hole)
        if abs(x - hx) > 0.5 or abs(y - hy) > 0.5:
            raise SystemExit(f"{inst.title} {c} at ({x:.1f},{y:.1f}) is not in {hole} ({hx:.1f},{hy:.1f})")
        inst.connect(c, self.bb, hole, "breadboardbreadboard")
        self.bb.connect(hole, inst, c, "breadboard")

    def leg(self, inst, c, hole):
        """Bend a rubber-band leg into a hole."""
        inst.leg_end[c] = self.hole(hole)
        self.plug(inst, c, hole)

    def wire(self, a, b, color, title):
        """a, b: a hole name, or (inst, connector)."""
        ends = []
        for ref in (a, b):
            if isinstance(ref, str):
                ends.append((self.bb, ref, self.hole(ref), "breadboardbreadboard"))
            else:
                ends.append((ref[0], ref[1], ref[0].pin_scene(ref[1]), "breadboard"))
        w = Inst(self, "WireModuleID", title, ":/resources/parts/core/wire.fzp", (0, 0), {})
        w.z, w.ends, w.color = 3.5 + len(self.wires) * 1e-4, ends, color
        for k, (other, oc, _, layer) in enumerate(ends):
            w.connect(f"connector{k}", other, oc, layer)
            other.connect(oc, w, f"connector{k}", "breadboardWire")
        self.wires.append(w)

    def note(self, x, y, w, h, text):
        self.notes.append((self.next_index(), x, y, w, h, text))

    def nets(self):
        """Union-find over plugs, wires and breadboard strips/rails."""
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        for i in self.insts:
            for c, lst in i.conns.items():
                for other, oc, _ in lst:
                    union((i.title, c), (other.title, oc))
            if i.module_id == "WireModuleID":
                union((i.title, "connector0"), (i.title, "connector1"))
        bb = self.bb.title
        with open(os.path.join(self.dir, "core", "Half_breadboard_v2.fzp")) as f:
            fzp = f.read()
        for bus, body in re.findall(r'<bus id="([^"]+)">(.*?)</bus>', fzp, re.S):
            for h in re.findall(r'connectorId="([^"]+)"', body):
                union((bb, h), (bb, bus))
        groups = {}
        for k in list(parent):
            groups.setdefault(find(k), set()).add(k)
        return list(groups.values())

    def check(self, expected):
        """expected: {net name: [(title, connector), ...]}. Each listed net must be
        exactly one electrical net, and different nets must not touch."""
        self.expected = expected
        nets = self.nets()
        where = {}
        for k, n in enumerate(nets):
            for m in n:
                where[m] = k
        seen = {}
        for name, members in expected.items():
            ks = {where.get(m) for m in members}
            if len(ks) != 1 or None in ks:
                raise SystemExit(f"net {name} is split: " + ", ".join(f"{m}->{where.get(m)}" for m in members))
            k = ks.pop()
            if k in seen:
                raise SystemExit(f"nets {seen[k]} and {name} are shorted")
            seen[k] = name

    @staticmethod
    def _connects(inst, c):
        return "".join(
            f'<connect connectorId="{oc}" modelIndex="{o.idx}" layer="{layer}"/>'
            for o, oc, layer in inst.conns.get(c, [])
        )

    def _part_xml(self, i):
        props = "".join(f'<property name="{k}" value="{html.escape(v)}"/>' for k, v in i.props.items())
        tr = ""
        if i.rot == -90:
            cx, cy = i.size[0] / 2, i.size[1] / 2
            tr = (
                f'<transform m11="0" m12="-1" m13="0" m21="1" m22="0" m23="0" '
                f'm31="{cx - cy:.4f}" m32="{cx + cy:.4f}" m33="1"/>'
            )
        conns = []
        for c in sorted(set(i.conns) | set(i.leg_end)):
            if c in i.legs:
                (sx, sy), _ = i.legs[c]
                ex, ey = i.leg_end[c]
                geo = (
                    f'<geometry x="{sx:.4f}" y="{sy:.4f}"/><leg><point x="0" y="0"/><bezier/>'
                    f'<point x="{ex - i.pos[0] - sx:.4f}" y="{ey - i.pos[1] - sy:.4f}"/><bezier/></leg>'
                )
            else:
                lx, ly = i.pins[c]
                geo = f'<geometry x="{lx:.4f}" y="{ly:.4f}"/>'
            conns.append(
                f'<connector connectorId="{c}" layer="breadboard">{geo}'
                f"<connects>{self._connects(i, c)}</connects></connector>"
            )
        layer = "breadboardbreadboard" if i is self.bb else "breadboard"
        other = (
            ""
            if i is self.bb
            else (
                f'<schematicView layer="schematic"><geometry z="2.5" x="{i.sch[0]}" y="{i.sch[1]}"/></schematicView>'
                f'<pcbView layer="copper0"><geometry z="2.5" x="{i.pcb[0]}" y="{i.pcb[1]}"/></pcbView>'
            )
        )
        return (
            f'<instance moduleIdRef="{i.module_id}" modelIndex="{i.idx}" path="{i.path}">'
            f"{props}<title>{html.escape(i.title)}</title><views>"
            f'<breadboardView layer="{layer}"><geometry z="{i.z}" x="{i.pos[0]:.4f}" '
            f'y="{i.pos[1]:.4f}">{tr}</geometry>'
            f"<connectors>{''.join(conns)}</connectors></breadboardView>{other}</views></instance>"
        )

    def _wire_xml(self, w):
        (_, _, a, _), (_, _, b, _) = w.ends
        conns = "".join(
            f'<connector connectorId="connector{k}" layer="breadboardWire"><geometry x="0" y="0"/>'
            f"<connects>{self._connects(w, f'connector{k}')}</connects></connector>"
            for k in range(2)
        )
        return (
            f'<instance moduleIdRef="WireModuleID" modelIndex="{w.idx}" path="{w.path}">'
            f'<title>{html.escape(w.title)}</title><views><breadboardView layer="breadboardWire">'
            f'<geometry z="{w.z:.5f}" x="{a[0]:.4f}" y="{a[1]:.4f}" x1="0" y1="0" '
            f'x2="{b[0] - a[0]:.4f}" y2="{b[1] - a[1]:.4f}" wireFlags="64"/>'
            f'<wireExtras mils="22.2222" color="{w.color}" opacity="1" banded="0"/>'
            f"<connectors>{conns}</connectors></breadboardView></views></instance>"
        )

    @staticmethod
    def _note_xml(n):
        idx, x, y, w, h, text = n
        body = "".join(f"<p>{html.escape(line) or '&#160;'}</p>" for line in text.split("\n"))
        doc = (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">'
            '<html><head><meta name="qrichtext" content="1" /></head>'
            f"<body style=\" font-family:'Droid Sans'; font-size:9pt;\">{body}</body></html>"
        )
        return (
            f'<instance moduleIdRef="NoteModuleID" modelIndex="{idx}" path=":/resources/parts/core/note.fzp">'
            f"<title>Note{idx}</title><text>{html.escape(doc)}</text><views>"
            f'<breadboardView layer="breadboardNote"><geometry z="6.5" x="{x}" y="{y}" '
            f'width="{w}" height="{h}"/></breadboardView></views></instance>'
        )

    def save(self, path, name):
        parts = [i for i in self.insts if i.module_id != "WireModuleID"]
        body = "\n".join(
            [self._part_xml(i) for i in parts]
            + [self._wire_xml(w) for w in self.wires]
            + [self._note_xml(n) for n in self.notes]
        )
        fz = f"""<?xml version="1.0" encoding="UTF-8"?>
<module fritzingVersion="1.0.6">
<views>
<view name="breadboardView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>
<view name="schematicView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>
<view name="pcbView" backgroundColor="#333333" gridSize="0.05in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>
</views>
<instances>
{body}
</instances>
</module>
"""
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(name + ".fz", fz)
            for k, v in sorted(self.embedded.items()):
                z.writestr(k, v)
        with open(os.path.join(self.dir, "core", "Half_breadboard_v2.fzp")) as f:
            fzp = f.read()
        buses = [
            re.findall(r'connectorId="([^"]+)"', body) for body in re.findall(r'<bus id="[^"]+">(.*?)</bus>', fzp, re.S)
        ]
        with open(path[: -len(".fzz")] + ".nets.json", "w") as f:
            json.dump({"nets": self.expected, "buses": buses, "svgids": self.svgids}, f, indent=1)
