"""Mutation test for lint: break a sketch's geometry, re-export it with
Fritzing, and require lint to fail. <connects> are left as they were, so
the saved connections still claim everything is fine; only the drawing moves.
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import zipfile

from . import lint


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


def run(fritzing, src, cases):
    """cases: [(sketch, description, mutate(fz) -> fz)]; src holds Sketch.save output."""
    work = os.path.join(os.environ.get("TMPDIR", "/tmp"), "lint-mutations")
    shutil.rmtree(work, ignore_errors=True)
    failures = 0
    for k, (sketch, name, mutate) in enumerate(cases):
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
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = lint.main(
                os.path.join(d, sketch + ".fzz"),
                os.path.join(d, sketch + "_breadboard.svg"),
                os.path.join(src, sketch + ".nets.json"),
            )
        caught = rc == 1
        first = (out.getvalue().strip().splitlines() or ["(no output)"])[0].split(": ", 1)[-1]
        print(f"{'caught' if caught else 'MISSED'}: {name} -> {first}")
        failures += not caught
    return 1 if failures else 0
