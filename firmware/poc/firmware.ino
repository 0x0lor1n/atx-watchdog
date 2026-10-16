// Pro Micro as the NAS power button: commands arrive on Serial1 (JCOM1 via a
// BC547 inverter, 9600 8N1) or USB; pin 4 drives the relay / BC547 on PWR SW.
// Commands: POWEROFF REBOOT ALIVE DISARM PRESS HOLD PING STATUS.

// Overlong lines are dropped whole: boot garbage must never match a command.
struct Line {
  const char *name;
  char buf[16];
  uint8_t len;
  bool overlong;
};

const uint8_t BUTTON_PIN = 4;
#ifdef BUTTON_ACTIVE_HIGH
const bool ACTIVE_LOW = false; // BC547 on PWR SW
#else
const bool ACTIVE_LOW = true; // Waveshare relay board input
#endif

const unsigned long SETTLE_MS = 3000;  // let the kernel reach its final halt
const unsigned long HOLD_MS = 6000;    // PCH forces off after 4 s held
const unsigned long OFF_GAP_MS = 3000; // board fully off before powering on
const unsigned long PRESS_MS = 300;    // a normal short press
const unsigned long WATCHDOG_MS =
    5UL * 60 * 1000; // module.nix asserts >= 2 beats fit

// Disarmed after firing: a NAS that cannot boot gets one cycle, not a loop.
static bool armed = false;
static unsigned long last_alive;

static void button(bool pressed) {
  digitalWrite(BUTTON_PIN, pressed == ACTIVE_LOW ? LOW : HIGH);
}

static void say(const char *msg) {
  if (Serial)
    Serial.println(msg);
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
    return;
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
    if (!Serial)
      return;
    if (armed) {
      Serial.print("watchdog: armed, last ALIVE s ago: ");
      Serial.println((millis() - last_alive) / 1000);
    } else {
      Serial.println("watchdog: disarmed");
    }
    return;
  } else {
    return;
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
    if (l.len && !l.overlong)
      run(l.buf);
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
  button(false); // idle level before pinMode, or the relay clicks on boot
  pinMode(BUTTON_PIN, OUTPUT);
  button(false);
  Serial.begin(115200);
  Serial1.begin(9600);
}

void loop() {
  while (Serial1.available())
    feed(com, Serial1.read());
  while (Serial.available())
    feed(usb, Serial.read());
  if (armed && millis() - last_alive >= WATCHDOG_MS) {
    armed = false;
    say("watchdog: no ALIVE, hold, gap, press");
    power_cycle();
    say("done");
  }
}
