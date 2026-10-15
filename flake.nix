{
  description = "Pro Micro as the NAS power button, driven from the NAS COM port";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      # Import into the NAS config; see module.nix.
      nixosModules.default = ./module.nix;

      packages = forAll (pkgs:
        let
          core = "${pkgs.arduino-core-unwrapped}/share/arduino";
          # Pro Micro 5 V/16 MHz runs the Leonardo build unchanged (same MCU, Caterina loader).
          mkFirmware = name: extraFlags: pkgs.runCommand "nas-power-button-${name}" { } ''
            mkdir -p build sketch/firmware $out
            cp ${./firmware/firmware.ino} sketch/firmware/firmware.ino
            ${core}/arduino-builder \
              -hardware ${core}/hardware \
              -tools ${core}/tools-builder \
              -tools ${core}/hardware/tools/avr \
              -built-in-libraries ${core}/libraries \
              -fqbn arduino:avr:leonardo \
              -prefs 'compiler.cpp.extra_flags=${extraFlags}' \
              -build-path "$PWD/build" \
              -warnings default \
              sketch/firmware/firmware.ino
            cp build/firmware.ino.hex $out/firmware.hex
          '';
          mkFlash = name: fw: pkgs.writeShellApplication {
            inherit name;
            runtimeInputs = [ pkgs.avrdude ];
            text = ''
              port=''${1:-/dev/ttyACM0}
              echo "Short RST to GND twice, then waiting for the bootloader on $port"
              for _ in $(seq 80); do [ -e "$port" ] && break; sleep 0.1; done
              avrdude -p atmega32u4 -c avr109 -P "$port" -b 57600 -D \
                -U flash:w:${fw}/firmware.hex:i
            '';
          };
        in
        rec {
          # Pin 4 active LOW: Waveshare relay board.
          firmware-relay = mkFirmware "relay" "";
          # Pin 4 active HIGH: BC547 switching PWR SW.
          firmware-transistor = mkFirmware "transistor" "-DBUTTON_ACTIVE_HIGH";

          flash-relay = mkFlash "flash-relay" firmware-relay;
          flash-transistor = mkFlash "flash-transistor" firmware-transistor;

          # Bench layouts for Fritzing (BENCH.md A and B). gen.py fails the build
          # if a pin misses its hole or a net differs from the schematic.
          bench-fzz = pkgs.runCommand "nas-power-button-bench-fzz"
            { nativeBuildInputs = [ pkgs.python3 ]; } ''
            python3 ${./fritzing}/gen.py ${pkgs.fritzing}/share/fritzing/parts $out
          '';

          # Opens the sketches with Fritzing; edits go to a copy, not the store.
          bench = pkgs.writeShellApplication {
            name = "bench";
            text = ''
              dir=''${1:-$PWD/bench}
              mkdir -p "$dir"
              for f in ${bench-fzz}/*.fzz; do
                [ -e "$dir/''${f##*/}" ] || install -m 644 "$f" "$dir/"
              done
              exec ${pkgs.fritzing}/bin/Fritzing "$dir"/bench-*.fzz
            '';
          };

          default = firmware-relay;
        });

      apps = forAll (pkgs: {
        fritzing = {
          type = "app";
          program = "${pkgs.fritzing}/bin/Fritzing";
        };
        bench = {
          type = "app";
          program = "${self.packages.${pkgs.system}.bench}/bin/bench";
        };
        flash-relay = {
          type = "app";
          program = "${self.packages.${pkgs.system}.flash-relay}/bin/flash-relay";
        };
        flash-transistor = {
          type = "app";
          program = "${self.packages.${pkgs.system}.flash-transistor}/bin/flash-transistor";
        };
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.avrdude pkgs.picocom ];
        };
      });

      checks = forAll (pkgs:
        let
          # Firmware logic on the host: same .ino, fake Arduino, virtual clock.
          sim = name: flags: pkgs.runCommandCC "sim-${name}" { } ''
            mkdir test firmware
            cp ${./firmware/firmware.ino} firmware/firmware.ino
            cp ${./test/sim.cpp} test/sim.cpp
            $CXX -std=c++17 -Wall -Werror -Wno-unused-function ${flags} test/sim.cpp -o sim
            ./sim | tee $out
          '';
        in
        {
          sim-relay = sim "relay" "";
          sim-transistor = sim "transistor" "-DBUTTON_ACTIVE_HIGH";
          # NAS side in a real shutdown: what reaches the COM port.
          vm = pkgs.testers.runNixOSTest (import ./test/vm.nix self);
          # Bench sketches as Fritzing draws them (not as gen.py meant them),
          # plus proof that the lint catches pins moved off their holes.
          bench-lint = pkgs.runCommand "bench-lint"
            { nativeBuildInputs = [ pkgs.python3 ]; } ''
            export HOME=$PWD/home QT_QPA_PLATFORM=offscreen
            cp ${self.packages.${pkgs.system}.bench-fzz}/* . && chmod u+w *
            ${pkgs.fritzing}/bin/Fritzing -svg $PWD > /dev/null 2>&1
            for s in bench-relay bench-transistor; do
              python3 ${./fritzing}/lint.py $s.fzz ''${s}_breadboard.svg $s.nets.json
            done
            python3 ${./fritzing}/lint_test.py ${pkgs.fritzing}/bin/Fritzing $PWD | tee $out
          '';
        });
    };
}
