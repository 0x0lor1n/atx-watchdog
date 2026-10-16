"""PoC schematic: JCOM1 -> BC547 inverter -> Pro Micro -> Waveshare relay -> JFP1.

Signal flows left to right. Pin numbers follow docs/poc/wiring.d2 and
docs/BENCH.md; change them there first.

Usage: poc.py OUT.svg
"""
import sys

import schemdraw
import schemdraw.elements as elm

schemdraw.use("svg")

OUT = sys.argv[1]
IC = dict(edgepadW=0.8, edgepadH=0.6, pinspacing=1.8, leadlen=0.8)


def terminal(drawing, label, loc):
    drawing += elm.Dot(open=True).label(label, loc=loc, ofst=0.25)


with schemdraw.Drawing(file=OUT, show=False) as d:
    d.config(unit=2.5, fontsize=10)

    # ---- NAS COM1 header (only the two pins we use) ----
    d.here = (0, 0)
    terminal(d, "JCOM1 pin 3\nSOUT  ±12 V", "left")
    d.here = (0, -5.0)
    terminal(d, "JCOM1 pin 5\nGND", "left")
    d += elm.Line().at((0, -5.0)).right(1.0)
    d += elm.Ground()

    # ---- inverter: RS-232 -> TTL, idle high ----
    d += elm.Resistor().at((0, 0)).right().label("R1 10k", loc="top")
    base = d.here
    d += elm.Dot()
    # D1 is offset left so its label clears Q1's emitter lead.
    d += elm.Line().at(base).down(1.2)
    d += elm.Line().left(1.2)
    d += elm.Diode().down(1.4).reverse().label("D1 1N4148", loc="right", ofst=0.4)
    d += elm.Ground()
    q1 = elm.BjtNpn(circle=True).right().anchor("base").at(base)
    d += q1.label("Q1 BC547", loc="right", ofst=0.5)
    d += elm.Line().at(q1.emitter).down(0.6)
    d += elm.Ground()
    d += elm.Line().at(q1.collector).up(0.6)
    rx = d.here
    d += elm.Dot()
    d += elm.Resistor().up(2.0).label("R2 10k", loc="bottom", ofst=0.3)
    d += elm.Vdd().label("+5 V", loc="top")
    d += elm.Line().at(rx).right(3.0)
    rx_end = d.here

    # ---- Pro Micro ----
    pm = elm.Ic(
        pins=[
            elm.IcPin(name="RX0", pin="0", side="left", slot="2/2"),
            elm.IcPin(name="D4", pin="4", side="right", slot="2/2"),
            elm.IcPin(name="VCC", side="top"),
            elm.IcPin(name="GND", side="bottom"),
        ],
        **IC,
    ).label("Pro Micro\nATmega32U4", loc="center", fontsize=10)
    d += pm.anchor("RX0").at(rx_end)
    d += elm.Line().at(pm.VCC).up(0.6)
    d += elm.Vdd().label("+5 V", loc="top")
    d += elm.Line().at(pm.GND).down(0.6)
    d += elm.Ground()
    d += elm.Label().at((pm.GND[0], pm.GND[1] - 1.9)).label(
        "micro-USB -> NAS internal USB header", fontsize=9)

    # ---- Waveshare relay board ----
    d += elm.Line().at(pm.D4).right(2.0)
    in1 = d.here
    relay = elm.Ic(
        pins=[
            elm.IcPin(name="IN1", pin="hdr 37", side="left", slot="2/2"),
            elm.IcPin(name="COM", side="right", slot="2/2"),
            elm.IcPin(name="NO", side="right", slot="1/2"),
            elm.IcPin(name="5V", pin="hdr 2", side="top"),
            elm.IcPin(name="GND", pin="hdr 6", side="bottom"),
        ],
        **IC,
    ).label("Waveshare\nRPi Relay Board\nCH1, active LOW", loc="center", fontsize=10)
    d += relay.anchor("IN1").at(in1)
    d += elm.Line().at(relay["5V"]).up(0.6)
    d += elm.Vdd().label("+5 V", loc="top")
    d += elm.Line().at(relay["GND"]).down(0.6)
    d += elm.Ground()

    # ---- JFP1 power switch pins, case button stays in parallel ----
    d += elm.Line().at(relay.COM).right(2.5)
    com = d.here
    d += elm.Dot()
    d += elm.Line().right(1.5)
    terminal(d, "JFP1 pin 6\nPWR SW", "right")
    d += elm.Line().at(relay.NO).right(2.5)
    no = d.here
    d += elm.Dot()
    d += elm.Line().right(1.5)
    terminal(d, "JFP1 pin 8\nPWR GND", "right")
    d += elm.Button().at(com).to(no).label("case\nPWR SW", loc="left", ofst=0.3)

    # ---- note ----
    d += elm.Label().at((0, -7.5)).label(
        "All grounds common: ATX pin 7 = JCOM1 pin 5 = Pro Micro GND = relay hdr 6.\n"
        "+5 V = ATX 5VSB (pin 9) through LM2596; on the bench it is USB 5 V.\n"
        "Idle SOUT is -12 V -> Q1 off -> RX0 pulled high by R2. Measured levels: BENCH.md.",
        loc="right", halign="left", valign="top", fontsize=9)

print(OUT)
