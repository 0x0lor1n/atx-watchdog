# NAS side of the Pro Micro power button on JCOM1: POWEROFF/REBOOT from a
# system-shutdown hook, ALIVE from a heartbeat service, DISARM on its stop.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.nas-power-button;
  stty = "${pkgs.coreutils}/bin/stty -F ${cfg.port} 9600 cs8 -cstopb -parenb raw -echo";

  hook = pkgs.writeShellScript "nas-power-button" ''
    case "$1" in
      poweroff) cmd=POWEROFF ;;
      reboot) cmd=REBOOT ;;
      *) exit 0 ;;
    esac
    ${stty} || exit 0
    # The leading newline ends whatever partial line the firmware is holding.
    printf '\n%s\n' "$cmd" > ${cfg.port}
    # the UART needs ~10 ms to drain 10 bytes at 9600 baud
    ${pkgs.coreutils}/bin/sleep 0.2
  '';

  # A probe stuck in D-state hangs this loop; the firmware times out and power-cycles, as intended.
  heartbeat = pkgs.writeShellScript "nas-power-button-heartbeat" ''
    ${stty}
    exec 3> ${cfg.port}
    t=${pkgs.coreutils}/bin/timeout
    healthy() {
      state=$($t ${toString cfg.probeTimeout} ${pkgs.systemd}/bin/systemctl is-system-running) || true
      case "$state" in
        running|degraded) ;;
        *) echo "nas-power-button: withholding ALIVE, system state '$state'" >&2; return 1 ;;
      esac
      ${lib.concatMapStringsSep "\n" (d: ''
        if ! $t ${toString cfg.probeTimeout} ${pkgs.bash}/bin/sh -c \
            'f=${d}/.nas-power-button-probe && echo "$$" > "$f" && sync -f "$f" && rm -f "$f"'; then
          echo "nas-power-button: withholding ALIVE, write probe failed on ${d}" >&2
          return 1
        fi
      '') cfg.probeDirs}
      return 0
    }
    while :; do
      if healthy; then
        printf '\nALIVE\n' >&3
      fi
      ${pkgs.coreutils}/bin/sleep ${toString cfg.heartbeatInterval}
    done
  '';

  disarm = pkgs.writeShellScript "nas-power-button-disarm" ''
    printf '\nDISARM\n' > ${cfg.port}
    ${pkgs.coreutils}/bin/sleep 0.2
  '';
in
{
  options.services.nas-power-button = {
    enable = lib.mkEnableOption "Pro Micro power button on the COM port";
    port = lib.mkOption {
      type = lib.types.str;
      default = "/dev/ttyS0";
      description = "Serial device wired to the Pro Micro's RX.";
    };
    heartbeat = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Send ALIVE so the firmware power-cycles a hung NAS.";
    };
    heartbeatInterval = lib.mkOption {
      type = lib.types.ints.positive;
      default = 60;
      description = "Seconds between ALIVE lines; the firmware gives up after 300.";
    };
    probeDirs = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ ];
      example = [ "/tank" ];
      description = "Directories that must accept a synced write before each ALIVE; use the data pool.";
    };
    probeTimeout = lib.mkOption {
      type = lib.types.ints.positive;
      default = 10;
      description = "Seconds a single probe may take before ALIVE is withheld.";
    };
    panicOnHang = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Turn oopses, soft lockups and hung tasks into a panic. A panicked
        kernel stops the heartbeat, a half-dead one might not.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.heartbeatInterval < 150;
        message = "nas-power-button: heartbeatInterval must leave the firmware's 300 s timeout at least two beats.";
      }
      {
        assertion = cfg.probeTimeout * (1 + builtins.length cfg.probeDirs) < cfg.heartbeatInterval;
        message = "nas-power-button: probes must finish within one heartbeatInterval.";
      }
    ];

    # kernel.panic stays 0: the PCH cannot reboot, and a silent kernel is what the firmware acts on.
    boot.kernel.sysctl = lib.mkIf cfg.panicOnHang {
      "kernel.panic_on_oops" = 1;
      "kernel.softlockup_panic" = 1;
      "kernel.hung_task_panic" = 1;
      "kernel.hung_task_timeout_secs" = lib.mkDefault 120;
    };

    # NixOS systemd: SYSTEM_SHUTDOWN_PATH=/etc/systemd/system-shutdown
    systemd.shutdownRamfs.contents."/etc/systemd/system-shutdown/nas-power-button".source = hook;

    systemd.services.nas-power-button-heartbeat = lib.mkIf cfg.heartbeat {
      description = "Heartbeat to the Pro Micro power button";
      wantedBy = [ "multi-user.target" ];
      # A NAS stuck in early boot never arms the watchdog.
      after = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = heartbeat;
        ExecStopPost = disarm;
        Restart = "always";
        RestartSec = 5;
      };
    };
  };
}
