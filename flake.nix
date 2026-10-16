{
  description = "Pro Micro as the NAS power button, driven from the NAS COM port";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
      # One interpreter for gen.py/lint.py/poc.py, the devshell and the checks.
      python =
        pkgs:
        pkgs.python3.withPackages (p: [
          p.schemdraw
          p.ziamath # schemdraw text="path"
          p.latex2mathml # ziamath imports it unconditionally
        ]);
    in
    {
      # Import into the NAS config; see module.nix.
      nixosModules.default = ./module.nix;

      packages = forAll (
        pkgs:
        let
          core = "${pkgs.arduino-core-unwrapped}/share/arduino";
          # Leonardo build: same MCU and Caterina loader as the Pro Micro 5 V.
          mkFirmware =
            name: extraFlags:
            pkgs.runCommand "nas-power-button-${name}" { } ''
              mkdir -p build sketch/firmware $out
              cp ${./src/firmware/firmware.ino} sketch/firmware/firmware.ino
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
          mkFlash =
            name: fw:
            pkgs.writeShellApplication {
              inherit name;
              runtimeInputs = [
                pkgs.avrdude
                pkgs.coreutils
              ];
              # 1200 bps touch resets Caterina into its loader (8 s window); the loader
              # re-enumerates under the same ttyACM name, so match by USB id instead.
              text = ''
                port=''${1:-/dev/ttyACM0}
                # Leonardo loader, Pro Micro 5V, Pro Micro 3V3
                is_loader() {
                  d=/sys/class/tty/''${1##*/}/device/..
                  [ -r "$d/idVendor" ] || return 1
                  case "$(cat "$d/idVendor"):$(cat "$d/idProduct")" in
                    2341:0036|2a03:0036|1b4f:9205|1b4f:9203) return 0 ;;
                  esac
                  return 1
                }
                find_loader() {
                  for _ in $(seq "$1"); do
                    for p in /dev/ttyACM*; do
                      [ -e "$p" ] && is_loader "$p" && { echo "$p"; return 0; }
                    done
                    sleep 0.1
                  done
                  return 1
                }
                loader=$(find_loader 1 || true)
                if [ -z "$loader" ] && [ -e "$port" ]; then
                  echo "1200 bps touch on $port"
                  stty -F "$port" 1200 || true
                  loader=$(find_loader 50 || true)
                fi
                if [ -z "$loader" ]; then
                  echo "no bootloader: short RST to GND twice now"
                  loader=$(find_loader 150 || true)
                fi
                [ -n "$loader" ] || { echo "no bootloader appeared"; exit 1; }
                echo "bootloader on $loader"
                sleep 0.3
                avrdude -p atmega32u4 -c avr109 -P "$loader" -b 57600 -D \
                  -U flash:w:${fw}/firmware.hex:i
              '';
            };
          # (tracked); `nix build .#bench-fzz` regenerates both from gen.py.
          mkFizzel =
            stage:
            pkgs.writeShellApplication {
              name = "fizzel-${stage}";
              text = ''
                f=''${1:-docs/${stage}/bench.fzz}
                [ -e "$f" ] || { echo "no $f: run from the repo root"; exit 1; }
                exec ${pkgs.fritzing}/bin/Fritzing "$f"
              '';
            };
        in
        rec {
          firmware-relay = mkFirmware "relay" "";
          firmware-transistor = mkFirmware "transistor" "-DBUTTON_ACTIVE_HIGH";

          flash-relay = mkFlash "flash-relay" firmware-relay;
          flash-transistor = mkFlash "flash-transistor" firmware-transistor;

          bench-fzz =
            pkgs.runCommand "nas-power-button-bench-fzz" { nativeBuildInputs = [ pkgs.python3 ]; }
              ''
                python3 ${./src/fritzing}/gen.py ${pkgs.fritzing}/share/fritzing/parts $out
              '';

          # docs/<stage>/{schematic,wiring}.{svg,png} are tracked; `render-docs` in the
          # devshell copies this output over them. SVG for GitHub, PNG for chats and
          # phones: Telegram's preview drops schemdraw's <use>-glyph text, and d2 embeds
          # its font as @font-face, which resvg ignores, so the PNG pass substitutes a
          # real font-family before rasterising.
          docs =
            pkgs.runCommand "nas-power-button-docs"
              {
                nativeBuildInputs = [
                  (python pkgs)
                  pkgs.d2
                  pkgs.resvg
                ];
              }
              ''
                mkdir -p $out/poc $out/final
                python3 ${./src/schematic}/poc.py $out/poc/schematic.svg
                resvg --zoom 3 --background white $out/poc/schematic.svg $out/poc/schematic.png

                for stage in poc final; do
                  d2 ${./docs}/$stage/wiring.d2 $out/$stage/wiring.svg
                  sed -E 's/font-family: "?d2-[0-9]+-font-(bold|italic|regular)"?/font-family: "Source Sans 3"/' \
                    $out/$stage/wiring.svg > wiring-$stage.svg
                  resvg --skip-system-fonts --use-fonts-dir ${pkgs.source-sans}/share/fonts \
                    --font-family "Source Sans 3" wiring-$stage.svg $out/$stage/wiring.png
                done
              '';

          render-docs = pkgs.writeShellApplication {
            name = "render-docs";
            text = ''
              cp -r --no-preserve=mode "$(nix build --no-link --print-out-paths .#docs)"/. docs/
              git -C docs status --short .
            '';
          };

          fizzel-poc = mkFizzel "poc";
          fizzel-final = mkFizzel "final";
          default = firmware-relay;
        }
      );

      apps = forAll (pkgs: {
        fritzing = {
          type = "app";
          program = "${pkgs.fritzing}/bin/Fritzing";
        };
        fizzel-poc = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.fizzel-poc}/bin/fizzel-poc";
        };
        fizzel-final = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.fizzel-final}/bin/fizzel-final";
        };
        flash-relay = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.flash-relay}/bin/flash-relay";
        };
        flash-transistor = {
          type = "app";
          program = "${
            self.packages.${pkgs.stdenv.hostPlatform.system}.flash-transistor
          }/bin/flash-transistor";
        };
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = with self.packages.${pkgs.stdenv.hostPlatform.system}; [
            flash-relay
            flash-transistor
            fizzel-poc
            fizzel-final
            render-docs
            pkgs.avrdude
            pkgs.picocom
            pkgs.d2
            (python pkgs)
            # git hooks; lefthook.yml takes the tools from PATH
            pkgs.lefthook
            pkgs.gitleaks
            pkgs.nixfmt
            pkgs.deadnix
            pkgs.statix
            pkgs.ruff
            pkgs.clang-tools
            pkgs.cppcheck
          ];
          shellHook = ''
            lefthook install >/dev/null || echo "lefthook install failed; git hooks not installed" >&2
            cat <<'HELP'
            nas-power-button devshell
              flash-relay [port]        PoC firmware, relay board   (pin 4 active LOW)
              flash-transistor [port]   final firmware, BC547       (pin 4 active HIGH)
              fizzel-poc                docs/poc/bench.fzz   in Fritzing
              fizzel-final              docs/final/bench.fzz in Fritzing
              picocom -b 115200 --omap crlf --echo /dev/ttyACM0
              nix flake check           sim + NixOS VM + Fritzing lint + docs-fresh
              nix build .#bench-fzz     regenerate bench.fzz from src/fritzing/gen.py
              render-docs               regenerate docs/*/{schematic,wiring}.{svg,png} from src/schematic/poc.py and wiring.d2
              lefthook run pre-commit   what the commit hook runs (nixfmt, deadnix, statix, ruff, clang-format, cppcheck)
              lefthook run pre-push     what the push hook runs (nix flake check)
            HELP
          '';
        };
      });

      checks = forAll (
        pkgs:
        let
          sim =
            name: flags:
            pkgs.runCommandCC "sim-${name}" { } ''
              mkdir -p test src/firmware
              cp ${./src/firmware/firmware.ino} src/firmware/firmware.ino
              cp ${./test/sim.cpp} test/sim.cpp
              $CXX -std=c++17 -Wall -Werror -Wno-unused-function ${flags} test/sim.cpp -o sim
              ./sim | tee $out
            '';
        in
        {
          sim-relay = sim "relay" "";
          sim-transistor = sim "transistor" "-DBUTTON_ACTIVE_HIGH";
          # The tracked SVGs must be what their sources render to; PNGs are not
          # compared, resvg output is not byte-stable across versions.
          docs-fresh = pkgs.runCommand "docs-fresh" { } ''
            for f in poc/schematic.svg poc/wiring.svg final/wiring.svg; do
              cmp -s ${self.packages.${pkgs.stdenv.hostPlatform.system}.docs}/$f ${./docs}/$f \
                || { echo "docs/$f is stale, run render-docs" >&2; exit 1; }
            done
            touch $out
          '';
          vm = pkgs.testers.runNixOSTest (import ./test/vm.nix self);
          # Lints what Fritzing saved, not what gen.py placed: the two differ after a GUI edit.
          bench-lint = pkgs.runCommand "bench-lint" { nativeBuildInputs = [ pkgs.python3 ]; } ''
            export HOME=$PWD/home QT_QPA_PLATFORM=offscreen
            cp ${self.packages.${pkgs.stdenv.hostPlatform.system}.bench-fzz}/* . && chmod u+w *
            ${pkgs.fritzing}/bin/Fritzing -svg $PWD > /dev/null 2>&1
            for s in bench-relay bench-transistor; do
              python3 ${./src/fritzing}/lint.py $s.fzz ''${s}_breadboard.svg $s.nets.json
            done
            python3 ${./src/fritzing}/lint_test.py ${pkgs.fritzing}/bin/Fritzing $PWD | tee $out
          '';
        }
      );
    };
}
