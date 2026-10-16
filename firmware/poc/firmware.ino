// Pro Micro (ATmega32U4, 5 V) as the NAS power button.
// The MSI B250M PRO-VD never leaves S0/S5 transitions on its own: the kernel
// prints "reboot: Power down" and the board stays on. A shutdown hook writes
// POWEROFF or REBOOT to the NAS's COM port; we hold PWR SW long enough for the
// PCH's 4 s override, and for REBOOT press it once more to power back on.
// The hardware watchdog's reset goes through the same broken PCH path, so a
// hung OS is caught here instead: a running NAS sends ALIVE every minute and
// silence for WATCHDOG_MS power-cycles it.
//
// RX (pin 0, Serial1) <- JCOM1 SOUT through a BC547 inverter, 9600 8N1.
// Pin 4 -> relay board CH1 IN (active LOW, default build) or a BC547 on
// PWR SW (active HIGH, built with -DBUTTON_ACTIVE_HIGH).
// USB serial: every received line is logged as "com: ..." / "usb: ...".
// Commands from either side:
//   POWEROFF, REBOOT  shutdown hook; also disarm the watchdog
//   ALIVE             heartbeat; arms the watchdog
//   DISARM            heartbeat stopped on purpose
//   PRESS, HOLD       bench tests
//   PING              link test, answers "pong", touches nothing
//   STATUS            watchdog state

// One line buffer per input so USB typing cannot splice into a COM line.
// Overlong lines are dropped whole, so "xxPOWEROFF" garbage never matches.
struct Line {
  const char *name;
  char buf[16];
  uint8_t len;
  bool overlong;
};

const uint8_t BUTTON_PIN = 4;
#ifdef BUTTON_ACTIVE_HIGH
const bool ACTIVE_LOW = false;  // BC547 on PWR SW
#else
const bool ACTIVE_LOW = true;   // Waveshare relay board input
#endif

const unsigned long SETTLE_MS = 3000;  // let the kernel reach its final halt
const unsigned long HOLD_MS = 6000;    // > 4 s PCH power-button override
const unsigned long OFF_GAP_MS = 3000; // board fully off before powering on
const unsigned long PRESS_MS = 300;    // a normal short press
const unsigned long WATCHDOG_MS = 5UL * 60 * 1000;  // five missed heartbeats

// Armed only between the first ALIVE and a shutdown/DISARM/fire, so BIOS,
// boot and a deliberately powered-off NAS are never touched, and a NAS that
// fails to boot is power-cycled once instead of in a loop.
static bool armed = false;
static unsigned long last_alive;

static void button(bool pressed) {
  digitalWrite(BUTTON_PIN, pressed == ACTIVE_LOW ? LOW : HIGH);
}

static void say(const char *msg) {
  if (Serial) Serial.println(msg);
}

static void press(unsigned long ms) {
  button(true);
  delay(ms);
  button(false);
}

static void power_cycle() {
  press(HOLD_MS);
  delay(OFF_GAP_MS);
  press(PRESS_MS);
}

static void run(const char *cmd) {
  if (!strcmp(cmd, "POWEROFF")) {
    armed = false;
    say("poweroff: settle, hold");
    delay(SETTLE_MS);
    press(HOLD_MS);
  } else if (!strcmp(cmd, "REBOOT")) {
    armed = false;
    say("reboot: settle, hold, gap, press");
    delay(SETTLE_MS);
    power_cycle();
  } else if (!strcmp(cmd, "ALIVE")) {
    armed = true;
    last_alive = millis();
    return;  // once a minute: the "com: ALIVE" echo is log enough
  } else if (!strcmp(cmd, "DISARM")) {
    armed = false;
    say("disarmed");
    return;
  } else if (!strcmp(cmd, "PRESS")) {
    say("press");
    press(PRESS_MS);
  } else if (!strcmp(cmd, "HOLD")) {
    say("hold");
    press(HOLD_MS);
  } else if (!strcmp(cmd, "PING")) {
    say("pong");
    return;
  } else if (!strcmp(cmd, "STATUS")) {
    if (!Serial) return;
    if (armed) {
      Serial.print("watchdog: armed, last ALIVE s ago: ");
      Serial.println((millis() - last_alive) / 1000);
    } else {
      Serial.println("watchdog: disarmed");
    }
    return;
  } else {
    return;  // boot noise, kernel console, partial lines: never act
  }
  say("done");
}

static void feed(Line &l, int c) {
  if (c == '\r' || c == '\n') {
    l.buf[l.len] = '\0';
    if (l.len && Serial) {
      Serial.print(l.name);
      Serial.println(l.overlong ? "(overlong, dropped)" : l.buf);
    }
    if (l.len && !l.overlong) run(l.buf);
    l.len = 0;
    l.overlong = false;
  } else if (l.len < sizeof(l.buf) - 1) {
    l.buf[l.len++] = (char)c;
  } else {
    l.overlong = true;
  }
}

static Line com = {"com: "}, usb = {"usb: "};

void setup() {
  button(false);  // set the idle level before the pin starts driving
  pinMode(BUTTON_PIN, OUTPUT);
  button(false);
  Serial.begin(115200);
  Serial1.begin(9600);
}

void loop() {
  while (Serial1.available()) feed(com, Serial1.read());
  while (Serial.available()) feed(usb, Serial.read());
  // Unsigned subtraction stays correct across the 49-day millis() wrap.
  if (armed && millis() - last_alive >= WATCHDOG_MS) {
    armed = false;
    say("watchdog: no ALIVE, hold, gap, press");
    power_cycle();
    say("done");
  }
}
