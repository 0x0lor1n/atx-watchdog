{
  description = "Pro Micro as the PC power button, driven from the PC COM port";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    mcu-bench = {
      url = "github:0x0lor1n/mcu-bench";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      mcu-bench,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
      bench = pkgs: mcu-bench.lib pkgs;
      # One interpreter for gen.py/poc.py, the devshell and the checks.
      python = pkgs: (bench pkgs).python (_: [ ]);
    in
    {
      # Import into the host config; see module.nix.
      nixosModules.default = ./module.nix;

      packages = forAll (
        pkgs:
        let
          b = bench pkgs;
          pm = b.boards.promicro;
          mkFirmware =
            name: flags:
            pm.mkFirmware {
              name = "atx-watchdog-${name}";
              ino = ./src/firmware/firmware.ino;
              inherit flags;
            };
        in
        rec {
          firmware-relay = mkFirmware "relay" "";
          firmware-transistor = mkFirmware "transistor" "-DBUTTON_ACTIVE_HIGH";

          flash-relay = pm.mkFlash "flash-relay" firmware-relay;
          flash-transistor = pm.mkFlash "flash-transistor" firmware-transistor;

          # docs/<stage>/bench.fzz (tracked); `nix build .#bench-fzz` regenerates both from gen.py.
          bench-fzz = b.mkBenchFzz {
            name = "atx-watchdog-bench-fzz";
            gen = ./src/fritzing/gen.py;
            python = python pkgs;
          };

          # docs/<stage>/{schematic,wiring}.{svg,png} are tracked; `render-docs` in the
          # devshell copies this output over them. SVG for GitHub, PNG for chats and
          # phones: Telegram's preview drops schemdraw's <use>-glyph text.
          docs =
            pkgs.runCommand "atx-watchdog-docs" { nativeBuildInputs = [ (python pkgs) ] ++ b.renderInputs; }
              ''
                mkdir -p $out/poc $out/final
                ${b.renderSchematic "${./src/schematic}/poc.py" "$out/poc/schematic"}
                ${b.renderD2 "${./docs}/poc/wiring.d2" "$out/poc/wiring"}
                ${b.renderD2 "${./docs}/final/wiring.d2" "$out/final/wiring"}
                ${b.renderD2 "${./docs}/watchdog.d2" "$out/watchdog"}
              '';

          render-docs = b.mkRenderDocs { };

          fizzel-poc = b.mkFizzel "fizzel-poc" "docs/poc/bench.fzz";
          fizzel-final = b.mkFizzel "fizzel-final" "docs/final/bench.fzz";
          default = firmware-relay;
        }
      );

      apps = forAll (
        pkgs:
        let
          pkg = self.packages.${pkgs.stdenv.hostPlatform.system};
          app = name: {
            type = "app";
            program = "${pkg.${name}}/bin/${name}";
          };
        in
        {
          fritzing = {
            type = "app";
            program = "${pkgs.fritzing}/bin/Fritzing";
          };
          fizzel-poc = app "fizzel-poc";
          fizzel-final = app "fizzel-final";
          flash-relay = app "flash-relay";
          flash-transistor = app "flash-transistor";
        }
      );

      devShells = forAll (pkgs: {
        default = (bench pkgs).mkDevShell {
          name = "atx-watchdog";
          packages =
            with self.packages.${pkgs.stdenv.hostPlatform.system};
            [
              flash-relay
              flash-transistor
              fizzel-poc
              fizzel-final
              render-docs
              pkgs.d2
              (python pkgs)
            ]
            ++ (bench pkgs).boards.promicro.devPackages;
          commands = [
            [
              "flash-relay [port]"
              "PoC firmware, relay board   (pin 4 active LOW)"
            ]
            [
              "flash-transistor [port]"
              "final firmware, BC547       (pin 4 active HIGH)"
            ]
            [
              "fizzel-poc"
              "docs/poc/bench.fzz   in Fritzing"
            ]
            [
              "fizzel-final"
              "docs/final/bench.fzz in Fritzing"
            ]
            [
              (bench pkgs).boards.promicro.console
              ""
            ]
            [
              "nix flake check"
              "sim + NixOS VM + Fritzing lint + docs-fresh"
            ]
            [
              "nix build .#bench-fzz"
              "regenerate bench.fzz from src/fritzing/gen.py"
            ]
            [
              "render-docs"
              "regenerate docs/*/{schematic,wiring}.{svg,png} from src/schematic/poc.py and wiring.d2"
            ]
            [
              "lefthook run pre-commit"
              "what the commit hook runs (nixfmt, deadnix, statix, ruff, clang-format, cppcheck)"
            ]
            [
              "lefthook run pre-push"
              "what the push hook runs (nix flake check)"
            ]
          ];
        };
      });

      checks = forAll (
        pkgs:
        let
          b = bench pkgs;
          pkg = self.packages.${pkgs.stdenv.hostPlatform.system};
          sim =
            name: flags:
            b.mkSim {
              name = "sim-${name}";
              firmware = ./src/firmware;
              test = ./test;
              inherit flags;
            };
        in
        {
          sim-relay = sim "relay" "";
          sim-transistor = sim "transistor" "-DBUTTON_ACTIVE_HIGH";
          # PNGs are not compared, resvg output is not byte-stable across versions.
          docs-fresh = b.mkFreshCheck "docs-fresh" pkg.docs ./docs [
            "poc/schematic.svg"
            "poc/wiring.svg"
            "final/wiring.svg"
            "watchdog.svg"
          ];
          vm = pkgs.testers.runNixOSTest (import ./test/vm.nix self);
          bench-lint = b.mkBenchLint {
            fzz = pkg.bench-fzz;
            sketches = [
              "bench-relay"
              "bench-transistor"
            ];
            cases = ./src/fritzing/lint_cases.py;
            python = python pkgs;
          };
        }
      );
    };
}
