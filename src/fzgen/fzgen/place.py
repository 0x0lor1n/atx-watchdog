"""Fritzing core parts placed by the holes their legs go into."""

import re

RES_ID = "ResistorModuleID"
NPN_ID = "2244EBEC10e"  # transistor_signal_NPN_TO92_CBE: C B E left to right, like BC547


def span(sk, inst, h1, h2):
    """A two-legged part centred between two holes, legs bent into them."""
    a, b = sk.hole(h1), sk.hole(h2)
    inst.pos = ((a[0] + b[0]) / 2 - inst.size[0] / 2, (a[1] + b[1]) / 2 - inst.size[1] / 2)
    sk.leg(inst, "connector0", h1)
    sk.leg(inst, "connector1", h2)
    return inst


def resistor(sk, title, value, h1, h2):
    r = sk.core(RES_ID, "resistor.fzp", title, {"resistance": value, "pin spacing": "400 mil"})
    return span(sk, r, h1, h2)


def npn_to92(sk, title, c_hole, part_number):
    """TO-92 standing in three adjacent holes: C, B, E left to right."""
    col, row = re.fullmatch(r"pin(\d+)([A-J])", c_hole).groups()
    holes = [f"pin{int(col) + k}{row}" for k in range(3)]
    q = sk.core(NPN_ID, "transistor_signal_NPN_TO92_CBE.fzp", title, {"part number": part_number})
    b = sk.hole(holes[1])
    q.pos = (b[0] - q.legs["connector1"][1][0], b[1] - q.legs["connector1"][1][1])
    for conn, h in zip(("connector2", "connector1", "connector0"), holes, strict=True):  # C B E
        sk.leg(q, conn, h)
    return q
