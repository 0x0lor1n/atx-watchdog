"""SparkFun Pro Micro (DEV-12640) across the centre gap, USB to the left."""

import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Rotated -90: TOP lands on row H, BOTTOM on row D, both from column col0.
# Connector ids from SparkFun's part.
TOP = ["RAW", "GND", "RST", "VCC", "A3", "A2", "A1", "A0", "15", "14", "16", "10"]
BOTTOM = ["TX", "RX", "GND", "GND", "2", "3", "4", "5", "6", "7", "8", "9"]


def conn(pin):
    if pin in TOP:
        return f"connector{28 + TOP.index(pin)}"
    return f"connector{51 - BOTTOM.index(pin)}"


def hole(pin, col0):
    if pin in TOP:
        return f"pin{col0 + TOP.index(pin)}H"
    return f"pin{col0 + BOTTOM.index(pin)}D"


def files(module_id):
    """SparkFun's part, with male pins, the given moduleId and a breadboard layer
    group (its breadboard SVG has none, so Fritzing would draw nothing)."""
    z = zipfile.ZipFile(os.path.join(HERE, "vendor/sparkfun-12640-pro-micro.fzpz"))
    out = {}
    for n in z.namelist():
        data = z.read(n).decode("utf-8")
        if n.startswith("part."):
            data = re.sub(r'moduleId="[^"]+"', f'moduleId="{module_id}"', data, count=1)
            data = data.replace('type="female"', 'type="male"')
            n = f"part.{module_id}.fzp"
        elif n.startswith("svg.breadboard.") and 'id="breadboard"' not in data:
            data = re.sub(r"(<svg\b[^>]*>)", r'\1<g id="breadboard">', data, count=1)
            data = data.replace("</svg>", "</g></svg>")
        out[n] = data
    return out


def place(sk, module_id, title, col0):
    """Embed, place and plug all 24 pins."""
    pm = sk.embed(module_id, title, files(module_id))
    pm.place(conn("RAW"), sk.hole(hole("RAW", col0)), rot=-90)
    pm.z = 2.6
    for pin in TOP + BOTTOM:
        sk.plug(pm, conn(pin), hole(pin, col0))
    return pm
