"""Lint mutations for the bench sketches. Every one is a real bench mistake.

python3 lint_cases.py <Fritzing binary> <dir with gen.py output>
"""

import sys

from fzgen.linttest import move_wire_end, run, shift_instance
from fzgen.part import P

CASES = [
    (
        "bench-relay",
        "Q1 one column right (C B E shifted)",
        lambda fz: shift_instance(fz, "Q1 BC547", P, 0),
    ),
    (
        "bench-relay",
        "RX wire lands one hole off (TX instead of RX)",
        lambda fz: move_wire_end(fz, "Q1 C to Pro Micro RX", -P, 0),
    ),
    (
        "bench-relay",
        "relay CH1 wire on header pin 35 instead of 37",
        lambda fz: move_wire_end(fz, "Pro Micro 4 to relay CH1", -P, 0),
    ),
    (
        "bench-relay",
        "D1 across the centre gap",
        lambda fz: shift_instance(fz, "D1 1N4148/1N4007", 0, -4 * P),
    ),
    ("bench-relay", "Pro Micro one column right", lambda fz: shift_instance(fz, "Pro Micro", P, 0)),
    (
        "bench-transistor",
        "R4 half a row down (both legs off their holes)",
        lambda fz: shift_instance(fz, "R4 10k", 0, P / 2),
    ),
    (
        "bench-transistor",
        "Q2 emitter wire into the + rail",
        lambda fz: move_wire_end(fz, "Q2 E to -", 0, P),
    ),
]

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(run(*sys.argv[1:], CASES))
