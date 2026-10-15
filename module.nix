# NAS side of the Pro Micro power button on JCOM1.
#
# The board hangs after "reboot: Power down", so the Pro Micro holds PWR SW
# once we are past the point of no return: a hook in the shutdown ramfs, which
# systemd-shutdown runs after every filesystem is unmounted, right before the
# final reboot(2), with argv[1] = poweroff | reboot | halt | kexec. halt and
# kexec are left alone.
#
# The hardware watchdog resets through the same broken PCH path, so hangs are
# caught by the Pro Micro too: a service sends ALIVE every heartbeatInterval
# and the firmware power-cycles the NAS after 5 min of silence. Stopping the
# service sends DISARM, so a manual stop or a slow shutdown is never cut short.
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
    # Leading newline flushes any half line the receiver may hold.
    printf '\n%s\n' "$cmd" > ${cfg.port}
    # 10 bytes at 9600 baud is ~10 ms; give the UART time to drain.
    ${pkgs.coreutils}/bin/sleep 0.2
  '';

  # ALIVE is only sent when the box is actually usable. A probe that blocks
  # (D-state on a dead pool) hangs this loop, which is the right outcome: the
  # firmware times out and power-cycles.
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

    # Reset after panic is left at 0: the PCH cannot reboot anyway, and a
    # panicked kernel is silent on the serial port, which is the whole point.
    boot.kernel.sysctl = lib.mkIf cfg.panicOnHang {
      "kernel.panic_on_oops" = 1;
      "kernel.softlockup_panic" = 1;
      "kernel.hung_task_panic" = 1;
      "kernel.hung_task_timeout_secs" = lib.mkDefault 120;
    };

    # NixOS builds systemd with SYSTEM_SHUTDOWN_PATH=/etc/systemd/system-shutdown.
    systemd.shutdownRamfs.contents."/etc/systemd/system-shutdown/nas-power-button".source = hook;

    systemd.services.nas-power-button-heartbeat = lib.mkIf cfg.heartbeat {
      description = "Heartbeat to the Pro Micro power button";
      wantedBy = [ "multi-user.target" ];
      # Only "up" once the system is: a NAS stuck in early boot stays disarmed.
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
