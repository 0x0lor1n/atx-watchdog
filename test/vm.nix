# module.nix in a VM; the QEMU serial port stands in for JCOM1.
self: _: {
  name = "nas-power-button";

  nodes.nas = {
    imports = [ self.nixosModules.default ];
    services.nas-power-button = {
      enable = true;
      port = "/dev/ttyS0";
      heartbeatInterval = 4;
      probeDirs = [ "/probe" ];
      probeTimeout = 1;
    };
    systemd.tmpfiles.rules = [ "d /probe 0755 root root -" ];
    # Listed before the test driver's own -serial, so this one is ttyS0.
    virtualisation.qemu.options = [
      "-chardev file,id=jcom1,path=jcom1.log,append=on"
      "-serial chardev:jcom1"
    ];
  };

  testScript = ''
    import time

    jcom1 = nas.state_dir / "jcom1.log"
    # console=ttyS0 shares the port, so match whole lines only, like the firmware.
    WORDS = {"ALIVE", "DISARM", "POWEROFF", "REBOOT"}

    def lines():
        return jcom1.read_text(errors="replace").split("\n") if jcom1.exists() else []

    def mark():
        return len(lines())

    def words(start):
        return [l.strip("\r") for l in lines()[start:] if l.strip("\r") in WORDS]

    # allow_reboot: the driver passes -no-reboot otherwise
    nas.start(allow_reboot=True)
    nas.wait_for_unit("nas-power-button-heartbeat.service")

    with subtest("heartbeat sends ALIVE on the port"):
        start = mark()
        time.sleep(10)
        got = words(start)
        assert got.count("ALIVE") >= 2, got

    with subtest("panic sysctls are set"):
        for k in ("panic_on_oops", "softlockup_panic", "hung_task_panic"):
            assert nas.succeed(f"sysctl -n kernel.{k}").strip() == "1", k

    with subtest("an unwritable probe dir withholds ALIVE"):
        nas.succeed("mount -t tmpfs -o ro tmpfs /probe")
        time.sleep(5)
        start = mark()
        time.sleep(10)
        assert "ALIVE" not in words(start), words(start)
        nas.succeed("journalctl -u nas-power-button-heartbeat | grep -q 'write probe failed on /probe'")
        nas.succeed("umount /probe")
        start = mark()
        time.sleep(10)
        assert "ALIVE" in words(start), words(start)

    with subtest("stopping the heartbeat disarms"):
        start = mark()
        nas.succeed("systemctl stop nas-power-button-heartbeat")
        time.sleep(1)
        assert "DISARM" in words(start), words(start)
        nas.succeed("systemctl start nas-power-button-heartbeat")

    with subtest("reboot: DISARM, then REBOOT, then ALIVE from the new boot"):
        start = mark()
        nas.reboot()
        nas.wait_for_unit("nas-power-button-heartbeat.service")
        time.sleep(3)
        got = words(start)
        assert "POWEROFF" not in got, got
        assert got.count("REBOOT") == 1, got
        i = got.index("REBOOT")
        assert "DISARM" in got[:i], got
        assert set(got[i + 1:]) == {"ALIVE"}, got

    with subtest("poweroff: DISARM, then POWEROFF as the last word"):
        start = mark()
        nas.shutdown()
        got = words(start)
        assert got[-1] == "POWEROFF", got
        assert "DISARM" in got, got
        assert "REBOOT" not in got, got
  '';
}
