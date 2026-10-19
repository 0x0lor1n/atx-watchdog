"""Generate the bench sketches (Fritzing .fzz) for BENCH.md stages A and B.

  python3 gen.py <fritzing-parts-dir> <out-dir>

Placement, net checks and the .fzz writer are in mcubench.fritzing. Parts Fritzing does
not ship (Waveshare RPi Relay Board, MSI JFP1/JCOM1, the ATX plug, the case
button) are generated here and embedded in the .fzz.
"""

import functools
import os
import sys

from mcubench.fritzing import part as fzpart
from mcubench.fritzing import promicro
from mcubench.fritzing.part import MM, P, text
from mcubench.fritzing.place import RES_ID, npn_to92, resistor, span
from mcubench.fritzing.sketch import BLACK, BLUE, GREEN, ORANGE, RED, YELLOW, Sketch

DIODE_ID = "SparkFun-DiscreteSemi-DIODE-1N4148_v2"
PM_ID = "atx-watchdog-sfe-pro-micro-5v"
RELAY_ID = "atx-watchdog-waveshare-rpi-relay-board"
JFP1_ID = "atx-watchdog-msi-jfp1"
JCOM1_ID = "atx-watchdog-msi-jcom1"
ATX_ID = "atx-watchdog-atx24"
BUTTON_ID = "atx-watchdog-case-button"

GenPart = functools.partial(fzpart.GenPart, author="atx-watchdog/src/fritzing/gen.py", tag="atx-watchdog")


def relay_board():
    """Waveshare RPi Relay Board, top view, HAT outline 65 x 56.5 mm.

    Connector i (0..39) = header pin i + 1, Pi numbering: odd pins on the
    inner row, even pins on the board edge. Then 3 per channel, in the
    Waveshare schematic's P1..P3 order: NC, COM, NO. Physical order, header
    edge up, checked on the board: channels CH3, CH2, CH1 left to right,
    terminals NO, COM, NC left to right. Neither is in the vendor docs.
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
        a.append(text(x, y, str(n), 5.5, "#ffe24d", weight="bold"))
    jx, jy = 55.5 * MM, 9.5 * MM
    a.append(f'<rect x="{jx:.2f}" y="{jy:.2f}" width="{6 * MM:.2f}" height="{8 * MM:.2f}" fill="#f2c400"/>')
    a.append(text(jx + 3 * MM, jy + 4.6 * MM, "JMP", 4.5, "#000000"))
    for ch in range(3):
        cx = (14.5 + (2 - ch) * 18) * MM
        a.append(
            f'<rect x="{cx - 7.5 * MM:.2f}" y="{18 * MM:.2f}" width="{15 * MM:.2f}" '
            f'height="{18 * MM:.2f}" rx="2" fill="#151515"/>'
        )
        a.append(text(cx, 26 * MM, "HLS8L", 6, "#bbbbbb"))
        a.append(text(cx, 29 * MM, "DC5V", 6, "#bbbbbb"))
        a.append(f'<circle cx="{cx - 5 * MM:.2f}" cy="{14 * MM:.2f}" r="3" fill="#ff3b3b"/>')
        a.append(text(cx - 3 * MM, 15 * MM, f"LED{ch + 1}", 5, "#ffffff", "start"))
        a.append(text(cx, 41 * MM, f"CH{ch + 1}", 7, "#ffffff", weight="bold"))
        a.append(
            f'<rect x="{cx - 7.5 * MM:.2f}" y="{43 * MM:.2f}" width="{15 * MM:.2f}" '
            f'height="{9 * MM:.2f}" fill="#2f9e4f"/>'
        )
        for t, nm in enumerate(("NC", "COM", "NO")):
            x = cx + (1 - t) * 5 * MM
            a.append(f'<circle cx="{x:.2f}" cy="{46.5 * MM:.2f}" r="{1.7 * MM:.2f}" fill="#9aa4ad"/>')
            a.append(text(x, 51 * MM, nm, 4.5, "#ffffff"))
            p.pin(f"CH{ch + 1} {nm}", x, 46.5 * MM, "R")
    a.append(text(w / 2, 38.2 * MM, "RPi Relay Board", 5.5, "#ffffff"))
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
        a.append(text(x, y - 6.5 if top else y + 10.5, str(n), 5, "#ffffff" if n < 10 else "#888888"))
        if n == 10:
            a.append(f'<rect x="{x - 2:.2f}" y="{y - 2:.2f}" width="4" height="4" fill="#555555"/>')
        else:
            p.pin(f"{n} {names[n]}", x, y, "L" if n % 2 else "R")
    a.append(text(w / 2, h - 3, title, 6.5, "#ffffff", weight="bold"))
    return p


ATX24 = {
    1: "3.3V",
    2: "3.3V",
    3: "GND",
    4: "5V",
    5: "GND",
    6: "5V",
    7: "GND",
    8: "PWR_OK",
    9: "5VSB",
    10: "12V",
    11: "12V",
    12: "3.3V",
    13: "3.3V",
    14: "-12V",
    15: "GND",
    16: "PS_ON",
    17: "GND",
    18: "GND",
    19: "GND",
    20: "NC",
    21: "5V",
    22: "5V",
    23: "5V",
    24: "GND",
}


def atx24():
    """PSU 24-pin plug, mating face, latch up: 13..24 on top, 1..12 below.

    Pin 9 is found by continuity, not colour (sleeved cables): 3.3 V sits in
    three corners (1, 12, 13), the odd corner is 24 (GND), and 3, 5, 7 are the
    only grounds in the lower row. Connector i = pin i + 1.
    """
    w, h = 11 * P + 30, 50.0
    p = GenPart(ATX_ID, "ATX 24-pin", "ATX", "power connector", "PSU 24-pin plug, mating face", w, h, "female")
    a = p.art
    x0, y_top, y_bot = 15.0, 20.0, 20.0 + P
    a.append(f'<rect x="0" y="6" width="{w}" height="{h - 6}" rx="2" fill="#e8e4d8" stroke="#8a8578"/>')
    a.append(f'<rect x="{w / 2 - 10}" y="0" width="20" height="7" fill="#e8e4d8" stroke="#8a8578"/>')
    a.append(text(w / 2, 5.5, "latch", 4, "#555555"))
    for n in range(1, 25):
        x = x0 + ((n - 13) if n > 12 else (n - 1)) * P
        y = y_top if n > 12 else y_bot
        hot = n in (7, 9)
        a.append(text(x, y - 5.5 if n > 12 else y + 9.5, str(n), 4.5, "#c00000" if hot else "#333333"))
        p.pin(f"{n} {ATX24[n]}", x, y, "L" if n <= 12 else "R")
    a.append(text(w / 2, h - 3, "ATX 24-pin (PSU plug)", 5.5, "#000000", weight="bold"))
    return p


def case_button():
    """The case's power button lead: a 2-pin housing, no polarity."""
    w, h = P + 30, 40.0
    p = GenPart(BUTTON_ID, "Case PWR SW", "SW", "switch", "Case power button (front panel lead)", w, h, "female")
    a = p.art
    a.append(f'<rect x="10" y="4" width="{P + 10}" height="12" fill="#111111"/>')
    a.append(f'<circle cx="{w / 2}" cy="28" r="7" fill="#9aa4ad" stroke="#333333"/>')
    a.append(text(w / 2, h - 1, "case PWR SW", 4.5, "#000000"))
    p.pin("1", 15.0, 10.0, "L")
    p.pin("2", 15.0 + P, 10.0, "R")
    return p


def common(sk, jfp_at):
    """Breadboard, Pro Micro and its power, the RS-232 inverter (A2), JCOM1, JFP1.

    Rails: top Y = +5 V (red), top Z = GND (blue); bottom W = +5 V, X = GND.
    """
    pm = promicro.place(sk, PM_ID, "Pro Micro", col0=2)

    sk.wire("pin5J", "pin5Y", RED, "VCC to +")
    sk.wire("pin3J", "pin3Z", BLACK, "GND to -")
    sk.wire("pin28Y", "pin28W", RED, "+ top to + bottom")
    sk.wire("pin27Z", "pin27X", BLACK, "- top to - bottom")

    q1 = npn_to92(sk, "Q1 BC547", "pin20E", "BC547")
    r1 = resistor(sk, "R1 10k", "10kΩ", "pin17D", "pin21D")
    d1 = sk.core(DIODE_ID, "sparkfun-discretesemi-diode-1n4148_v2.fzp", "D1 1N4148/1N4007")
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
        msi_header(JCOM1_ID, "JCOM1", MSI_JCOM1, "MSI serial header", True).files(),
    )
    jc.place("connector0", (130, 235))
    sk.wire("pin17C", (jc, "connector2"), ORANGE, "JCOM1 3 SOUT to R1")
    sk.wire("pin29X", (jc, "connector4"), BLACK, "JCOM1 5 GND to -")

    jf = sk.embed(
        JFP1_ID,
        "JFP1",
        msi_header(JFP1_ID, "JFP1", MSI_JFP1, "MSI front panel header", False).files(),
    )
    jf.place("connector1", jfp_at)

    # 5VSB: a Dupont pushed into the back of the PSU plug next to pin 9's wire.
    # Ground needs no second wire, it is common through JCOM1 5.
    atx = sk.embed(ATX_ID, "ATX 24-pin", atx24().files())
    atx.place("connector0", (130, 320))
    sk.wire("pin13W", (atx, "connector8"), RED, "ATX 9 5VSB to +")

    for k, part in enumerate((pm, q1, r1, d1, r2, jc, jf, atx)):
        part.sch = (k % 4 * 200, k // 4 * 200)
        part.pcb = (k % 4 * 120, k // 4 * 120)

    pmn = lambda pin: ("Pro Micro", promicro.conn(pin))
    nets = {
        "+5V": [pmn("VCC"), ("R2 10k", "connector1"), ("ATX 24-pin", "connector8")],
        "GND": [
            pmn("GND"),
            ("Q1 BC547", "connector0"),
            ("D1 1N4148/1N4007", "connector0"),
            ("JCOM1", "connector4"),
        ],
        "SOUT": [("JCOM1", "connector2"), ("R1 10k", "connector0")],
        "Q1 base": [
            ("R1 10k", "connector1"),
            ("D1 1N4148/1N4007", "connector1"),
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
    btn = sk.embed(BUTTON_ID, "Case PWR SW", case_button().files())
    btn.place("connector0", (520, 330))
    btn.sch, btn.pcb = (800, 200), (480, 120)
    # No polarity; left pin to NO (left screw) so the wires do not cross.
    sk.wire(term(1, "NO"), (btn, "connector0"), GREEN, "case button to CH1 NO")
    sk.wire(term(1, "COM"), (btn, "connector1"), GREEN, "case button to CH1 COM")
    title = lambda c: ("Relay board", c[1])
    nets["+5V"] += [title(hdr(2)), title(hdr(1))]
    nets["GND"].append(title(hdr(6)))
    nets["D4"] = [("Pro Micro", promicro.conn("4")), title(hdr(37))]
    nets["PWR SW 6"] += [title(term(1, "COM")), ("Case PWR SW", "connector1")]
    nets["PWR SW 8"] = [("JFP1", "connector7"), title(term(1, "NO")), ("Case PWR SW", "connector0")]
    sk.check(nets)
    sk.note(
        600,
        0,
        400,
        260,
        "Этап A (BENCH.md A1–A3), прошивка flash-relay.\n"
        "Питание: 5VSB, ATX pin 9 (Dupont сзади штекера).\n"
        "USB только для прошивки, не вместе с 5VSB.\n"
        "Реле-плата: гнёзда 1 (3V3) и 2 (5V) на «+»,\n"
        "6 (GND) на «−», 37 (CH1) на Pro Micro 4.\n"
        "Без гнезда 1 оптопара не питается, реле молчит.\n"
        "Relay_JMP: перемычка на CH1 (IN_CH1–P25)\n"
        "обязательна, без неё 37 ни к чему не подключено.\n"
        "Каналы слева направо CH3, CH2, CH1; винты\n"
        "клеммника NO, COM, NC (COM посередине).\n"
        "Кнопка корпуса — в те же COM и NO, параллельно.\n"
        "JFP1/JCOM1: распиновка по мануалу MSI.",
    )
    return sk


def bench_transistor(parts):
    sk = Sketch(parts)
    _, jf, nets = common(sk, (330, 235))
    npn_to92(sk, "Q2 BC547", "pin24F", "BC547")  # C 24, B 25, E 26
    resistor(sk, "R3 2.2k", "2.2kΩ", "pin21I", "pin25I")
    r4 = sk.core(RES_ID, "resistor.fzp", "R4 10k", {"resistance": "10kΩ", "pin spacing": "400 mil"})
    span(sk, r4, "pin25J", "pin21Z")  # straight into the GND rail
    sk.wire("pin8C", "pin21G", GREEN, "Pro Micro 4 to R3")
    sk.wire("pin26G", "pin25Z", BLACK, "Q2 E to -")
    sk.wire("pin24G", (jf, "connector5"), BLUE, "Q2 C to JFP1 hot pin")
    for k, t in enumerate(("Q2 BC547", "R3 2.2k", "R4 10k")):
        inst = next(i for i in sk.insts if i.title == t)
        inst.sch, inst.pcb = (k * 200, 400), (k * 120, 240)
    nets["GND"] += [("Q2 BC547", "connector0"), ("R4 10k", "connector1")]
    nets["D4"] = [("Pro Micro", promicro.conn("4")), ("R3 2.2k", "connector0")]
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
