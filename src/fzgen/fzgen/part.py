"""Parts Fritzing does not ship, generated from breadboard art plus a pin list."""

import html

P = 9.0  # 0.1 in in scene px
MM = 90 / 25.4


def svg(w, h, body):
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w / 90:.4f}in" '
        f'height="{h / 90:.4f}in" viewBox="0 0 {w:.3f} {h:.3f}">\n{body}\n</svg>\n'
    )


def text(x, y, s, size=5.0, fill="#ffffff", anchor="middle", weight="normal"):
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="Droid Sans, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{html.escape(s)}</text>'
    )


class GenPart:
    """A part described by its breadboard art plus a list of pins."""

    def __init__(self, module_id, title, label, family, desc, w, h, pin_type, *, author, tag):
        self.module_id, self.title, self.label = module_id, title, label
        self.family, self.desc, self.w, self.h = family, desc, w, h
        self.pin_type, self.author, self.tag = pin_type, author, tag
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
        return svg(self.w, self.h, f'<g id="breadboard">\n{"".join(self.art)}\n{pins}\n</g>')

    def schematic_svg(self):
        left = [i for i, p in enumerate(self.pins) if p[3] == "L"]
        right = [i for i, p in enumerate(self.pins) if p[3] == "R"]
        rows = max(len(left), len(right))
        bw, lead = 9 * 12, 18.0
        W, H = bw + 2 * lead, (rows + 2) * P + 9
        out = [
            f'<rect x="{lead}" y="4.5" width="{bw}" height="{H - 9}" fill="#ffffff" '
            f'stroke="#000000" stroke-width="1"/>',
            text(W / 2, H - 9, self.title, 6, "#000000"),
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
                out.append(text(lx, y + 2, self.pins[i][0], 5, "#000000", "start" if col == 0 else "end"))
        return svg(W, H, '<g id="schematic">\n' + "\n".join(out) + "\n</g>")

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
        return svg(self.w, self.h, f'{silk}\n<g id="copper1"><g id="copper0">\n{pads}\n</g></g>')

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
 <author>{self.author}</author>
 <description>{html.escape(self.desc)}</description>
 <tags><tag>{self.tag}</tag></tags>
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
