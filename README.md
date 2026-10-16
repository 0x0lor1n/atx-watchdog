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
[docs/BENCH.md](docs/BENCH.md). Each drawing also has a `.png` next to it
for chats and phones.

## Install

Nix with flakes enabled, direnv (`use flake` in `.envrc`). `nix develop`
prints the available commands and installs the git hooks (lefthook.yml):
linters and formatters on commit, `nix flake check` on push.

NAS side: import `nixosModules.default`, see `module.nix`.

## Two ideas worth stealing

**Generated, linted breadboards.** `src/fritzing/gen.py` places parts by
"this pin goes into that hole", using hole and pin coordinates from the
parts' own SVGs, and traces the resulting nets through the breadboard
strips against the schematic. Then `src/fritzing/lint.py` re-reads what
Fritzing actually rendered, so a pin that drifted off its hole or a wire on
the wrong row fails `nix flake check` instead of the bench.

**Tested firmware without hardware.** `test/sim.cpp` compiles the same
`.ino` against a fake Arduino core with a virtual clock and drives the
command parser, button timings and the watchdog state machine.
`test/vm.nix` boots the NixOS module in a VM and checks what reaches the
COM port on `poweroff`, `reboot` and a stopped heartbeat.

## Mistakes so far

- Trusted a mental model of the relay board instead of its schematic:
  wired header 37 (CH1) and 5 V/GND, got a signal on the pin and no relay.
  The schematic shows header 37 reaches the optocoupler only through the
  `CH1` jumper, and the opto side is fed from header 1 (3V3). Lesson: read
  the vendor schematic before generating the sketch; they now live in
  `docs/schemas/`.
