# nas-power-button

A hardware watchdog and remote power button for a home NAS, built on a
SparkFun Pro Micro. Personal project.

**Why.** A short on the PSU killed the USB controller of the motherboard and broke the
handling of the power-off signal: the OS halts, the board stays on, and the
only remedy is a finger on the case button. The board still has a working
COM header (JCOM1) and the front-panel PWR SW pins (JFP1), which is enough:
a microcontroller listens on the COM port and presses the button.

**How.** JCOM1 TX goes through a one-transistor RS-232→TTL inverter into
the Pro Micro's `Serial1`. A NixOS module sends `POWEROFF`/`REBOOT` from
shutdown hooks and `ALIVE` once a minute; the firmware shorts PWR SW
(relay board in the proof of concept, a BC547 in the final build) and
power-cycles the box on its own if `ALIVE` stops. See
[docs/poc/schematic.svg](docs/poc/schematic.svg) (schemdraw),
[docs/poc/wiring.svg](docs/poc/wiring.svg) and
[docs/final/wiring.svg](docs/final/wiring.svg) (d2, bench wiring),
[docs/BENCH.md](docs/BENCH.md).

## Install

Nix with flakes enabled, direnv (`use flake` in `.envrc`).

```
nix develop            # or: direnv allow
flash-relay            # PoC firmware   (relay board, pin 4 active LOW)
flash-transistor       # final firmware (BC547,       pin 4 active HIGH)
fizzel-poc             # breadboard layout in Fritzing: docs/poc/bench.fzz
fizzel-final           #                                docs/final/bench.fzz
picocom -b 115200 --omap crlf --echo /dev/ttyACM0
nix flake check        # firmware sim, NixOS VM, Fritzing lint
nix build .#schematic  # regenerate docs/poc/schematic.svg from schematic/poc.py
```

Entering the shell installs the git hooks (lefthook.yml). pre-commit: nixfmt,
deadnix, statix, ruff, clang-format, cppcheck on staged files. pre-push:
`nix flake check`.

NAS side: import `nixosModules.default`, see `module.nix`.

## Two ideas worth stealing

**Generated, linted breadboards.** `fritzing/gen.py` places parts by
"this pin goes into that hole", using hole and pin coordinates from the
parts' own SVGs, and traces the resulting nets through the breadboard
strips against the schematic. Then `fritzing/lint.py` re-reads what
Fritzing actually rendered, so a pin that drifted off its hole or a wire on
the wrong row fails `nix flake check` instead of the bench.

**Tested firmware without hardware.** `test/sim.cpp` compiles the same
`.ino` against a fake Arduino core with a virtual clock and drives the
command parser, button timings and the watchdog state machine.
`test/vm.nix` boots the NixOS module in a VM and checks what reaches the
COM port on `poweroff`, `reboot` and a stopped heartbeat.

## Layout

```
firmware/poc/      sketch (one source, two builds: relay / transistor)
module.nix         NixOS module: heartbeat, shutdown hooks, panic sysctls
docs/poc/          schematic.svg, wiring.d2 + svg, bench.fzz   (Waveshare relay board)
schematic/         schemdraw sources for docs/*/schematic.svg
docs/final/        wiring.d2 + svg, bench.fzz   (BC547)
docs/schemas/      vendor schematics: Pro Micro, RPi Relay Board
docs/BENCH.md      step-by-step bench procedure
fritzing/          gen.py, lint.py, svgpins.py, vendored Pro Micro part
test/              sim.cpp, vm.nix
```

## Mistakes so far

- Trusted a mental model of the relay board instead of its schematic:
  wired header 37 (CH1) and 5 V/GND, got a signal on the pin and no relay.
  The schematic shows header 37 reaches the optocoupler only through the
  `CH1` jumper, and the opto side is fed from header 1 (3V3). Lesson: read
  the vendor schematic before generating the sketch; they now live in
  `docs/schemas/`.
