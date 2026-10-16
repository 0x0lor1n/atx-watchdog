"""Mutation test for lint.py: break a sketch's geometry, re-export it with
Fritzing, and require lint.py to fail. <connects> are left as they were, so
the saved connections still claim everything is fine; only the drawing moves.

  python3 lint_test.py <Fritzing binary> <dir with gen.py output>
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
P = 9.0


def shift_instance(fz, title, dx, dy):
    """Move a part's breadboard geometry (x, y) by dx, dy."""
    i = fz.index(f"<title>{title}</title>")
    j = fz.index("<breadboardView", i)
    m = re.compile(r'<geometry z="([^"]+)" x="([^"]+)" y="([^"]+)"').search(fz, j)
    new = f'<geometry z="{m[1]}" x="{float(m[2]) + dx:.4f}" y="{float(m[3]) + dy:.4f}"'
    return fz[: m.start()] + new + fz[m.end() :]


def move_wire_end(fz, title, dx, dy):
    i = fz.index(f"<title>{title}</title>")
    m = re.compile(r'x2="([^"]+)" y2="([^"]+)"').search(fz, i)
    new = f'x2="{float(m[1]) + dx:.4f}" y2="{float(m[2]) + dy:.4f}"'
    return fz[: m.start()] + new + fz[m.end() :]


# (sketch, name, mutation). Every one is a real bench mistake.
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
        lambda fz: shift_instance(fz, "D1 1N4148", 0, -4 * P),
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


def main(fritzing, src):
    work = os.path.join(os.environ.get("TMPDIR", "/tmp"), "lint-mutations")
    shutil.rmtree(work, ignore_errors=True)
    failures = 0
    for k, (sketch, name, mutate) in enumerate(CASES):
        d = os.path.join(work, str(k))
        os.makedirs(d)
        zi = zipfile.ZipFile(os.path.join(src, sketch + ".fzz"))
        with zipfile.ZipFile(os.path.join(d, sketch + ".fzz"), "w") as zo:
            for n in zi.namelist():
                data = zi.read(n)
                if n.endswith(".fz"):
                    before = data.decode()
                    after = mutate(before)
                    assert after != before, name
                    data = after.encode()
                zo.writestr(n, data)
        subprocess.run(
            [fritzing, "-svg", d],
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=True,
        )
        r = subprocess.run(
            [
                sys.executable,
                os.path.join(HERE, "lint.py"),
                os.path.join(d, sketch + ".fzz"),
                os.path.join(d, sketch + "_breadboard.svg"),
                os.path.join(src, sketch + ".nets.json"),
            ],
            capture_output=True,
            text=True,
        )
        caught = r.returncode == 1
        first = (r.stdout.strip().splitlines() or ["(no output)"])[0].split(": ", 1)[-1]
        print(f"{'caught' if caught else 'MISSED'}: {name} -> {first}")
        failures += not caught
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
