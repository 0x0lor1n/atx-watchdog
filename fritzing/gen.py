"""Generate the bench sketches (Fritzing .fzz) for BENCH.md stages A and B.

  python3 gen.py <fritzing-parts-dir> <out-dir>

Placement is "this pin goes into that hole": hole and pin coordinates come
from the parts' own SVGs (svgpins.py), and every plug is checked to land on
its hole. The nets are then traced through the breadboard strips and compared
with the schematic, so a misplaced wire fails the build instead of the bench.
Parts Fritzing does not ship (Waveshare RPi Relay Board, MSI JFP1/JCOM1) are
generated here and embedded in the .fzz.
"""

import html
import io
import json
import os
import re
import sys
import zipfile

import svgpins

HERE = os.path.dirname(os.path.abspath(__file__))

BB_ID = "0152b316-ca6e-11ee-a6fa-8be78db221f8BreadboardModuleID"  # Half_breadboard_v2
NPN_ID = "2244EBEC10e"  # transistor_signal_NPN_TO92_CBE: C B E left to right, like BC547
RES_ID = "ResistorModuleID"
DIODE_ID = "SparkFun-DiscreteSemi-DIODE-1N4148_v2"
PM_ID = "nas-power-button-sfe-pro-micro-5v"
RELAY_ID = "nas-power-button-waveshare-rpi-relay-board"
JFP1_ID = "nas-power-button-msi-jfp1"
JCOM1_ID = "nas-power-button-msi-jcom1"

RED, BLACK, YELLOW, GREEN, ORANGE, BLUE = (
    "#cc1414",
    "#404040",
    "#ffe24d",
    "#47cc79",
    "#ef6100",
    "#418dd9",
)

P = 9.0  # 0.1 in in scene px
MM = 90 / 25.4


def _svg(w, h, body):
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w / 90:.4f}in" '
        f'height="{h / 90:.4f}in" viewBox="0 0 {w:.3f} {h:.3f}">\n{body}\n</svg>\n'
    )


def _text(x, y, s, size=5.0, fill="#ffffff", anchor="middle", weight="normal"):
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="Droid Sans, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{html.escape(s)}</text>'
    )


class GenPart:
    """A part described by its breadboard art plus a list of pins."""

    def __init__(self, module_id, title, label, family, desc, w, h, pin_type):
        self.module_id, self.title, self.label = module_id, title, label
        self.family, self.desc, self.w, self.h = family, desc, w, h
        self.pin_type = pin_type
        self.pins = []  # (name, x, y, schematic side "L"/"R")
        self.art = []

    def pin(self, name, x, y, side="L"):
        self.pins.append((name, x, y, side))

    def breadboard_svg(self):
        pins = "\n".join(
            f'<rect id="connector{i}pin" x="{x - 2.5:.2f}" y="{y - 2.5:.2f}" '
            f'width="5" height="5" fill="#c9a33a" stroke="#6b5413" stroke-width="0.4"/>'
            for i, (_, x, y, _) in enumerate(self.pins)
        )
        return _svg(self.w, self.h, f'<g id="breadboard">\n{"".join(self.art)}\n{pins}\n</g>')

    def schematic_svg(self):
        left = [i for i, p in enumerate(self.pins) if p[3] == "L"]
        right = [i for i, p in enumerate(self.pins) if p[3] == "R"]
        rows = max(len(left), len(right))
        bw, lead = 9 * 12, 18.0
        W, H = bw + 2 * lead, (rows + 2) * P + 9
        out = [
            f'<rect x="{lead}" y="4.5" width="{bw}" height="{H - 9}" fill="#ffffff" '
            f'stroke="#000000" stroke-width="1"/>',
            _text(W / 2, H - 9, self.title, 6, "#000000"),
        ]
        for col, idxs in ((0, left), (1, right)):
            for r, i in enumerate(idxs):
                y = (r + 1) * P + 4.5
                x0, x1 = (0, lead) if col == 0 else (W - lead, W)
                tx = x0 if col == 0 else x1 - 0.1
                out.append(
                    f'<line id="connector{i}pin" x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" '
                    f'stroke="#000000" stroke-width="1"/>'
                )
                out.append(
                    f'<rect id="connector{i}terminal" x="{tx}" y="{y - 0.05}" width="0.1" height="0.1" fill="none"/>'
                )
                lx = x1 + 2 if col == 0 else x0 - 2
                out.append(_text(lx, y + 2, self.pins[i][0], 5, "#000000", "start" if col == 0 else "end"))
        return _svg(W, H, '<g id="schematic">\n' + "\n".join(out) + "\n</g>")

    def pcb_svg(self):
        pads = "\n".join(
            f'<circle id="connector{i}pad" cx="{x:.2f}" cy="{y:.2f}" r="2.6" '
            f'fill="none" stroke="#f7bd13" stroke-width="2"/>'
            for i, (_, x, y, _) in enumerate(self.pins)
        )
        silk = (
            f'<g id="silkscreen"><rect x="0.5" y="0.5" width="{self.w - 1:.2f}" '
            f'height="{self.h - 1:.2f}" fill="none" stroke="#ffffff" stroke-width="1"/></g>'
        )
        return _svg(self.w, self.h, f'{silk}\n<g id="copper1"><g id="copper0">\n{pads}\n</g></g>')

    def fzp(self):
        conns = "\n".join(
            f'''  <connector id="connector{i}" name="{html.escape(n)}" type="{self.pin_type}">
   <description>{html.escape(n)}</description>
   <views>
    <breadboardView><p layer="breadboard" svgId="connector{i}pin"/></breadboardView>
    <schematicView><p layer="schematic" svgId="connector{i}pin" terminalId="connector{i}terminal"/></schematicView>
    <pcbView><p layer="copper0" svgId="connector{i}pad"/><p layer="copper1" svgId="connector{i}pad"/></pcbView>
   </views>
  </connector>'''
            for i, (n, _, _, _) in enumerate(self.pins)
        )
        m = self.module_id
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<module fritzingVersion="1.0.6" moduleId="{m}">
 <version>1</version>
 <title>{html.escape(self.title)}</title>
 <label>{self.label}</label>
 <author>nas-power-button/fritzing/gen.py</author>
 <description>{html.escape(self.desc)}</description>
 <tags><tag>nas-power-button</tag></tags>
 <properties><property name="family">{html.escape(self.family)}</property></properties>
 <views>
  <iconView><layers image="breadboard/{m}_breadboard.svg"><layer layerId="icon"/></layers></iconView>
  <breadboardView><layers image="breadboard/{m}_breadboard.svg"><layer layerId="breadboard"/></layers></breadboardView>
  <schematicView><layers image="schematic/{m}_schematic.svg"><layer layerId="schematic"/></layers></schematicView>
  <pcbView><layers image="pcb/{m}_pcb.svg"><layer layerId="copper0"/><layer layerId="silkscreen"/><layer layerId="copper1"/></layers></pcbView>
 </views>
 <connectors>
{conns}
 </connectors>
</module>
'''

    def files(self):
        m = self.module_id
        return {
            f"part.{m}.fzp": self.fzp(),
            f"svg.breadboard.{m}_breadboard.svg": self.breadboard_svg(),
            f"svg.schematic.{m}_schematic.svg": self.schematic_svg(),
            f"svg.pcb.{m}_pcb.svg": self.pcb_svg(),
        }


def relay_board():
    """Waveshare RPi Relay Board, top view, HAT outline 65 x 56.5 mm.

    Connector i (0..39) = header pin i + 1, Pi numbering: odd pins on the
    inner row, even pins on the board edge. Then 3 per channel, in the
    Waveshare schematic's P1..P3 order: NC, COM, NO. The left-to-right order
    of channels and terminals on the real board is not documented.
    """
    w, h = 65 * MM, 56.5 * MM
    p = GenPart(
        RELAY_ID,
        "Waveshare RPi Relay Board",
        "K",
        "relay module",
        "3-channel relay HAT. CH1/CH2/CH3 = header pins 37/38/40 (BCM 26/20/21), "
        "active LOW, only through the Relay_JMP jumpers. Powered from header "
        "pins 2 (5V), 1 (3V3, optocoupler side), 6 (GND).",
        w,
        h,
        "female",
    )
    a = p.art
    a.append(f'<rect x="0" y="0" width="{w:.2f}" height="{h:.2f}" rx="10" fill="#1e5aa8"/>')
    for hx, hy in ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)):
        a.append(
            f'<circle cx="{hx * MM:.2f}" cy="{hy * MM:.2f}" r="{3.1 * MM:.2f}" fill="#d7c27a"/>'
            f'<circle cx="{hx * MM:.2f}" cy="{hy * MM:.2f}" r="{1.375 * MM:.2f}" fill="#ffffff"/>'
        )
    x0 = 32.5 * MM - 9.5 * P
    y_even, y_odd = 3.5 * MM, 3.5 * MM + P
    a.append(
        f'<rect x="{x0 - 5.5:.2f}" y="{y_even - 5.5:.2f}" width="{19 * P + 11:.2f}" '
        f'height="{P + 11:.2f}" fill="#111111"/>'
    )
    gnd = {6, 9, 14, 20, 25, 30, 34, 39}
    names = {1: "3V3", 17: "3V3", 2: "5V", 4: "5V", 37: "CH1", 38: "CH2", 40: "CH3"}
    for n in range(1, 41):
        x = x0 + (n - 1) // 2 * P
        name = names.get(n, "GND" if n in gnd else "GPIO")
        p.pin(f"{n} {name}", x, y_odd if n % 2 else y_even, "L" if n % 2 else "R")
    for n in (1, 2, 6, 37, 38, 40):
        x = x0 + (n - 1) // 2 * P
        y = y_odd + 9.5 if n % 2 else y_even - 4.2
        a.append(_text(x, y, str(n), 5.5, "#ffe24d", weight="bold"))
    jx, jy = 55.5 * MM, 9.5 * MM
    a.append(f'<rect x="{jx:.2f}" y="{jy:.2f}" width="{6 * MM:.2f}" height="{8 * MM:.2f}" fill="#f2c400"/>')
    a.append(_text(jx + 3 * MM, jy + 4.6 * MM, "JMP", 4.5, "#000000"))
    for ch in range(3):
        cx = (14.5 + ch * 18) * MM
        a.append(
            f'<rect x="{cx - 7.5 * MM:.2f}" y="{18 * MM:.2f}" width="{15 * MM:.2f}" '
            f'height="{18 * MM:.2f}" rx="2" fill="#151515"/>'
        )
        a.append(_text(cx, 26 * MM, "HLS8L", 6, "#bbbbbb"))
        a.append(_text(cx, 29 * MM, "DC5V", 6, "#bbbbbb"))
        a.append(f'<circle cx="{cx - 5 * MM:.2f}" cy="{14 * MM:.2f}" r="3" fill="#ff3b3b"/>')
        a.append(_text(cx - 3 * MM, 15 * MM, f"LED{ch + 1}", 5, "#ffffff", "start"))
        a.append(_text(cx, 41 * MM, f"CH{ch + 1}", 7, "#ffffff", weight="bold"))
        a.append(
            f'<rect x="{cx - 7.5 * MM:.2f}" y="{43 * MM:.2f}" width="{15 * MM:.2f}" '
            f'height="{9 * MM:.2f}" fill="#2f9e4f"/>'
        )
        for t, nm in enumerate(("NC", "COM", "NO")):
            x = cx + (t - 1) * 5 * MM
            a.append(f'<circle cx="{x:.2f}" cy="{46.5 * MM:.2f}" r="{1.7 * MM:.2f}" fill="#9aa4ad"/>')
            a.append(_text(x, 51 * MM, nm, 4.5, "#ffffff"))
            p.pin(f"CH{ch + 1} {nm}", x, 46.5 * MM, "R")
    a.append(_text(w / 2, 38.2 * MM, "RPi Relay Board", 5.5, "#ffffff"))
    return p


MSI_JFP1 = {
    1: "HDD LED+",
    2: "Power LED+",
    3: "HDD LED-",
    4: "Power LED-",
    5: "Reset SW",
    6: "Power SW",
    7: "Reset SW",
    8: "Power SW",
    9: "Reserved",
}
MSI_JCOM1 = {
    1: "DCD",
    2: "SIN",
    3: "SOUT",
    4: "DTR",
    5: "GND",
    6: "DSR",
    7: "RTS",
    8: "CTS",
    9: "RI",
}


def msi_header(module_id, title, names, desc, odd_on_top):
    """MSI 2x5 header, pin 10 missing (key). Connector i = pin i + 1.

    The row facing the breadboard is drawn on top so wires do not cross the
    header; which row that is on the real board is up to the manual.
    """
    w, h = 4 * P + 30, 46.0
    p = GenPart(module_id, title, title, "motherboard header", desc, w, h, "male")
    a = p.art
    x0, y_top, y_bot = 15.0, 14.0, 14.0 + P
    a.append(f'<rect x="0" y="0" width="{w}" height="{h}" rx="3" fill="#1b4d1b"/>')
    a.append(f'<rect x="{x0 - 5.5}" y="{y_top - 5.5}" width="{4 * P + 11}" height="{P + 11}" fill="#0d0d0d"/>')
    for n in range(1, 11):
        x = x0 + (n - 1) // 2 * P
        top = (n % 2 == 1) == odd_on_top
        y = y_top if top else y_bot
        a.append(_text(x, y - 6.5 if top else y + 10.5, str(n), 5, "#ffffff" if n < 10 else "#888888"))
        if n == 10:
            a.append(f'<rect x="{x - 2:.2f}" y="{y - 2:.2f}" width="4" height="4" fill="#555555"/>')
        else:
            p.pin(f"{n} {names[n]}", x, y, "L" if n % 2 else "R")
    a.append(_text(w / 2, h - 3, title, 6.5, "#ffffff", weight="bold"))
    return p


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


def pro_micro_files():
    """SparkFun's part, with male pins, our moduleId and a breadboard layer group
    (its breadboard SVG has none, so Fritzing would draw nothing)."""
    z = zipfile.ZipFile(os.path.join(HERE, "vendor/sparkfun-12640-pro-micro.fzpz"))
    out = {}
    for n in z.namelist():
        data = z.read(n).decode("utf-8")
        if n.startswith("part."):
            data = re.sub(r'moduleId="[^"]+"', f'moduleId="{PM_ID}"', data, count=1)
            data = data.replace('type="female"', 'type="male"')
            n = f"part.{PM_ID}.fzp"
        elif n.startswith("svg.breadboard.") and 'id="breadboard"' not in data:
            data = re.sub(r"(<svg\b[^>]*>)", r'\1<g id="breadboard">', data, count=1)
            data = data.replace("</svg>", "</g></svg>")
        out[n] = data
    return out


# Pro Micro rotated -90 (USB to the left): RAW..D10 on row H, TXO..D9 on row D,
# columns 2..13. Connector ids from SparkFun's part.
PM_TOP = ["RAW", "GND", "RST", "VCC", "A3", "A2", "A1", "A0", "15", "14", "16", "10"]
PM_BOT = ["TX", "RX", "GND", "GND", "2", "3", "4", "5", "6", "7", "8", "9"]
PM_COL0 = 2


def pm_conn(pin):
    if pin in PM_TOP:
        return f"connector{28 + PM_TOP.index(pin)}"
    return f"connector{51 - PM_BOT.index(pin)}"


def pm_hole(pin):
    if pin in PM_TOP:
        return f"pin{PM_COL0 + PM_TOP.index(pin)}H"
    return f"pin{PM_COL0 + PM_BOT.index(pin)}D"


def resistor(sk, title, value, h1, h2):
    r = sk.core(RES_ID, "resistor.fzp", title, {"resistance": value, "pin spacing": "400 mil"})
    a, b = sk.hole(h1), sk.hole(h2)
    r.pos = ((a[0] + b[0]) / 2 - r.size[0] / 2, (a[1] + b[1]) / 2 - r.size[1] / 2)
    sk.leg(r, "connector0", h1)
    sk.leg(r, "connector1", h2)
    return r


def bc547(sk, title, c_hole):
    """TO-92 standing in three adjacent holes: C, B, E left to right."""
    col, row = re.fullmatch(r"pin(\d+)([A-J])", c_hole).groups()
    holes = [f"pin{int(col) + k}{row}" for k in range(3)]
    q = sk.core(NPN_ID, "transistor_signal_NPN_TO92_CBE.fzp", title, {"part number": "BC547"})
    b = sk.hole(holes[1])
    q.pos = (b[0] - q.legs["connector1"][1][0], b[1] - q.legs["connector1"][1][1])
    for conn, h in zip(("connector2", "connector1", "connector0"), holes, strict=True):  # C B E
        sk.leg(q, conn, h)
    return q


def common(sk, jfp_at):
    """Breadboard, Pro Micro and its power, the RS-232 inverter (A2), JCOM1, JFP1.

    Rails: top Y = +5 V (red), top Z = GND (blue); bottom W = +5 V, X = GND.
    """
    pm = sk.embed(PM_ID, "Pro Micro", pro_micro_files())
    pm.place(pm_conn("RAW"), sk.hole(pm_hole("RAW")), rot=-90)
    pm.z = 2.6
    for pin in PM_TOP + PM_BOT:
        sk.plug(pm, pm_conn(pin), pm_hole(pin))

    sk.wire("pin5J", "pin5Y", RED, "VCC to +")
    sk.wire("pin3J", "pin3Z", BLACK, "GND to -")
    sk.wire("pin28Y", "pin28W", RED, "+ top to + bottom")
    sk.wire("pin27Z", "pin27X", BLACK, "- top to - bottom")

    q1 = bc547(sk, "Q1 BC547", "pin20E")
    r1 = resistor(sk, "R1 10k", "10kΩ", "pin17D", "pin21D")
    d1 = sk.core(DIODE_ID, "sparkfun-discretesemi-diode-1n4148_v2.fzp", "D1 1N4148")
    d1.place("connector1", sk.hole("pin21C"))  # cathode (band) on the base column
    sk.plug(d1, "connector1", "pin21C")
    sk.plug(d1, "connector0", "pin25C")
    r2 = resistor(sk, "R2 10k", "10kΩ", "pin20B", "pin24B")
    sk.wire("pin24A", "pin24W", RED, "R2 to +")
    sk.wire("pin22A", "pin22X", BLACK, "Q1 E to -")
    sk.wire("pin25B", "pin25X", BLACK, "D1 anode to -")
    sk.wire("pin20A", "pin3B", YELLOW, "Q1 C to Pro Micro RX")

    jc = sk.embed(
        JCOM1_ID,
        "JCOM1",
        msi_header(JCOM1_ID, "JCOM1", MSI_JCOM1, "MSI serial header (NAS)", True).files(),
    )
    jc.place("connector0", (130, 235))
    sk.wire("pin17C", (jc, "connector2"), ORANGE, "JCOM1 3 SOUT to R1")
    sk.wire("pin29X", (jc, "connector4"), BLACK, "JCOM1 5 GND to -")

    jf = sk.embed(
        JFP1_ID,
        "JFP1",
        msi_header(JFP1_ID, "JFP1", MSI_JFP1, "MSI front panel header (NAS)", False).files(),
    )
    jf.place("connector1", jfp_at)

    for k, part in enumerate((pm, q1, r1, d1, r2, jc, jf)):
        part.sch = (k % 4 * 200, k // 4 * 200)
        part.pcb = (k % 4 * 120, k // 4 * 120)

    pmn = lambda pin: ("Pro Micro", pm_conn(pin))
    nets = {
        "+5V": [pmn("VCC"), ("R2 10k", "connector1")],
        "GND": [
            pmn("GND"),
            ("Q1 BC547", "connector0"),
            ("D1 1N4148", "connector0"),
            ("JCOM1", "connector4"),
        ],
        "SOUT": [("JCOM1", "connector2"), ("R1 10k", "connector0")],
        "Q1 base": [
            ("R1 10k", "connector1"),
            ("D1 1N4148", "connector1"),
            ("Q1 BC547", "connector1"),
        ],
        "RX": [("Q1 BC547", "connector2"), ("R2 10k", "connector0"), pmn("RX")],
        "PWR SW 6": [("JFP1", "connector5")],
    }
    return pm, jf, nets


def bench_relay(parts):
    sk = Sketch(parts)
    _, jf, nets = common(sk, (420, 235))
    rel = sk.embed(RELAY_ID, "Relay board", relay_board().files())
    rel.place("connector0", (345, 60))
    rel.sch, rel.pcb = (600, 200), (360, 120)
    hdr = lambda n: (rel, f"connector{n - 1}")
    term = lambda ch, t: (rel, f"connector{40 + (ch - 1) * 3 + ('NC', 'COM', 'NO').index(t)}")
    sk.wire("pin31Y", hdr(2), RED, "relay 5V")
    # Header 1 (3V3) feeds the opto LEDs; without it CH1 IN does nothing. 5 V there is fine.
    sk.wire("pin29Y", hdr(1), ORANGE, "relay 3V3 from +5V")
    sk.wire("pin30Z", hdr(6), BLACK, "relay GND")
    sk.wire("pin8C", hdr(37), GREEN, "Pro Micro 4 to relay CH1")
    sk.wire(term(1, "COM"), (jf, "connector5"), BLUE, "CH1 COM to JFP1 6")
    sk.wire(term(1, "NO"), (jf, "connector7"), BLUE, "CH1 NO to JFP1 8")
    title = lambda c: ("Relay board", c[1])
    nets["+5V"] += [title(hdr(2)), title(hdr(1))]
    nets["GND"].append(title(hdr(6)))
    nets["D4"] = [("Pro Micro", pm_conn("4")), title(hdr(37))]
    nets["PWR SW 6"].append(title(term(1, "COM")))
    nets["PWR SW 8"] = [("JFP1", "connector7"), title(term(1, "NO"))]
    sk.check(nets)
    sk.note(
        600,
        0,
        400,
        240,
        "Этап A (BENCH.md A1–A3), прошивка flash-relay.\n"
        "Pro Micro питается по USB от ноутбука.\n"
        "Реле-плата: гнёзда 1 (3V3) и 2 (5V) на «+»,\n"
        "6 (GND) на «−», 37 (CH1) на Pro Micro 4.\n"
        "Без гнезда 1 оптопара не питается, реле молчит.\n"
        "Relay_JMP: перемычка на CH1 (IN_CH1–P25)\n"
        "обязательна, без неё 37 ни к чему не подключено.\n"
        "Порядок CH1–CH3 и NC/COM/NO на картинке\n"
        "условный: сверь с надписями на плате.\n"
        "Кнопку корпуса с JFP1 6/8 на время теста снять.\n"
        "JFP1/JCOM1: распиновка по мануалу MSI.",
    )
    return sk


def bench_transistor(parts):
    sk = Sketch(parts)
    _, jf, nets = common(sk, (330, 235))
    bc547(sk, "Q2 BC547", "pin24F")  # C 24, B 25, E 26
    resistor(sk, "R3 2.2k", "2.2kΩ", "pin21I", "pin25I")
    r4 = sk.core(RES_ID, "resistor.fzp", "R4 10k", {"resistance": "10kΩ", "pin spacing": "400 mil"})
    a, b = sk.hole("pin25J"), sk.hole("pin21Z")
    r4.pos = ((a[0] + b[0]) / 2 - r4.size[0] / 2, (a[1] + b[1]) / 2 - r4.size[1] / 2)
    sk.leg(r4, "connector0", "pin25J")
    sk.leg(r4, "connector1", "pin21Z")  # straight into the GND rail
    sk.wire("pin8C", "pin21G", GREEN, "Pro Micro 4 to R3")
    sk.wire("pin26G", "pin25Z", BLACK, "Q2 E to -")
    sk.wire("pin24G", (jf, "connector5"), BLUE, "Q2 C to JFP1 hot pin")
    for k, t in enumerate(("Q2 BC547", "R3 2.2k", "R4 10k")):
        inst = next(i for i in sk.insts if i.title == t)
        inst.sch, inst.pcb = (k * 200, 400), (k * 120, 240)
    nets["GND"] += [("Q2 BC547", "connector0"), ("R4 10k", "connector1")]
    nets["D4"] = [("Pro Micro", pm_conn("4")), ("R3 2.2k", "connector0")]
    nets["Q2 base"] = [
        ("R3 2.2k", "connector1"),
        ("R4 10k", "connector0"),
        ("Q2 BC547", "connector1"),
    ]
    nets["PWR SW 6"].append(("Q2 BC547", "connector2"))
    sk.check(nets)
    sk.note(
        600,
        0,
        400,
        220,
        "Этап B (BENCH.md B1–B3), прошивка flash-transistor.\n"
        "Q2 C идёт на «горячий» пин PWR SW (≈3,3 V, замер B1).\n"
        "Нарисован JFP1 6; если горячий 8 — перекинь провод.\n"
        "Второй пин PWR SW не подключать: земля общая\n"
        "через JCOM1 5.\n"
        "R4 держит Q2 закрытым, пока Pro Micro\n"
        "прошивается или перезагружается.",
    )
    return sk


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    parts, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    for name, build in (("bench-relay", bench_relay), ("bench-transistor", bench_transistor)):
        build(parts).save(os.path.join(out, name + ".fzz"), name)
        print(os.path.join(out, name + ".fzz"))


if __name__ == "__main__":
    main()
