// Host-side tests for firmware.ino: the sketch is compiled unchanged against a
// fake Arduino with a virtual millis() clock, and every button edge is
// recorded with its timestamp.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

#define HIGH 1
#define LOW 0
#define OUTPUT 1

static unsigned long now_ms;
static int pin_level = -1;
struct Edge {
  unsigned long t;
  int level;
};
static std::vector<Edge> edges;

unsigned long millis() { return now_ms; }
void delay(unsigned long ms) { now_ms += ms; }
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t, uint8_t v) {
  if (v != pin_level) edges.push_back({now_ms, v});
  pin_level = v;
}

struct FakeSerial {
  std::deque<char> in;
  std::string out;
  bool connected = true;
  void begin(unsigned long) {}
  explicit operator bool() const { return connected; }
  int available() { return (int)in.size(); }
  int read() {
    char c = in.front();
    in.pop_front();
    return (unsigned char)c;
  }
  void print(const char *s) { out += s; }
  void print(unsigned long v) { out += std::to_string(v); }
  void println(const char *s) { out += s, out += "\n"; }
  void println(unsigned long v) { out += std::to_string(v) + "\n"; }
  void send(const std::string &s) { in.insert(in.end(), s.begin(), s.end()); }
};
static FakeSerial Serial, Serial1;

#include "../firmware/firmware.ino"

#ifdef BUTTON_ACTIVE_HIGH
static const int PRESSED = HIGH, RELEASED = LOW;
#else
static const int PRESSED = LOW, RELEASED = HIGH;
#endif

static int failures;
#define CHECK(cond)                                                      \
  do {                                                                   \
    if (!(cond)) {                                                       \
      std::printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
      failures++;                                                        \
    }                                                                    \
  } while (0)

// Presses since the last reset, as (start, length) pairs.
struct Press {
  unsigned long at, len;
};
static std::vector<Press> presses() {
  std::vector<Press> r;
  for (size_t i = 0; i + 1 < edges.size(); i++)
    if (edges[i].level == PRESSED && edges[i + 1].level == RELEASED)
      r.push_back({edges[i].t, edges[i + 1].t - edges[i].t});
  return r;
}

static void boot(unsigned long start = 0) {
  now_ms = start;
  pin_level = -1;
  edges.clear();
  Serial = FakeSerial();
  Serial1 = FakeSerial();
  armed = false;
  com.len = usb.len = 0;
  com.overlong = usb.overlong = false;
  setup();
  edges.clear();  // only edges after setup matter
}

// Run loop() for `ms` of virtual time in 100 ms steps.
static void run_for(unsigned long ms) {
  unsigned long end = now_ms + ms;
  while ((long)(end - now_ms) > 0) {
    loop();
    now_ms += 100;
  }
}

static void test(const char *name, void (*fn)()) {
  int before = failures;
  fn();
  std::printf("%s %s\n", failures == before ? "ok  " : "FAIL", name);
}

int main() {
  test("idle level after setup is released", [] {
    boot();
    CHECK(pin_level == RELEASED);
  });

  test("boot noise and partial words never press", [] {
    boot();
    Serial1.send("\x00\xff garbage\nPOWER\nPOWEROF\npoweroff\n POWEROFF\nREBOOTX\n");
    run_for(30000);
    CHECK(presses().empty());
  });

  test("overlong line containing POWEROFF is dropped", [] {
    boot();
    Serial1.send("xxxxxxxxxxxxxxxxxxxxPOWEROFF\n");
    run_for(30000);
    CHECK(presses().empty());
    CHECK(Serial.out.find("(overlong, dropped)") != std::string::npos);
  });

  test("a half line before the hook's leading newline is flushed", [] {
    boot();
    Serial1.send("junk-from-boot");      // no newline
    Serial1.send("\nPOWEROFF\n");        // what module.nix writes
    run_for(20000);
    CHECK(presses().size() == 1);
  });

  test("PRESS = one 300 ms press", [] {
    boot();
    Serial.send("PRESS\r\n");            // picocom --omap crlf
    run_for(2000);
    auto p = presses();
    CHECK(p.size() == 1);
    CHECK(p.size() == 1 && p[0].len == PRESS_MS);
  });

  test("POWEROFF: 3 s settle, then 6 s hold, nothing else", [] {
    boot(1000);
    Serial1.send("\nPOWEROFF\n");
    run_for(60000);
    auto p = presses();
    CHECK(p.size() == 1);
    CHECK(p.size() == 1 && p[0].at == 1000 + SETTLE_MS && p[0].len == HOLD_MS);
  });

  test("REBOOT: settle, 6 s hold, 3 s gap, 300 ms press", [] {
    boot(1000);
    Serial1.send("\nREBOOT\n");
    run_for(60000);
    auto p = presses();
    CHECK(p.size() == 2);
    if (p.size() == 2) {
      CHECK(p[0].at == 1000 + SETTLE_MS && p[0].len == HOLD_MS);
      CHECK(p[1].at == p[0].at + HOLD_MS + OFF_GAP_MS && p[1].len == PRESS_MS);
    }
  });

  test("watchdog stays disarmed without ALIVE (BIOS, powered off)", [] {
    boot();
    run_for(3 * WATCHDOG_MS);
    CHECK(presses().empty());
  });

  test("steady ALIVE every minute never fires", [] {
    boot();
    for (int i = 0; i < 60; i++) {
      Serial1.send("ALIVE\n");
      run_for(60000);
    }
    CHECK(presses().empty());
  });

  test("silence after ALIVE power-cycles once at WATCHDOG_MS", [] {
    boot();
    Serial1.send("ALIVE\n");
    run_for(100);
    unsigned long alive_at = now_ms - 100;
    run_for(4 * WATCHDOG_MS);
    auto p = presses();
    CHECK(p.size() == 2);  // hold + power-on, and no second cycle
    if (p.size() == 2) {
      CHECK(p[0].len == HOLD_MS && p[1].len == PRESS_MS);
      CHECK(p[0].at - alive_at >= WATCHDOG_MS);
      CHECK(p[0].at - alive_at < WATCHDOG_MS + 200);
    }
  });

  test("watchdog re-arms after the NAS boots and sends ALIVE again", [] {
    boot();
    Serial1.send("ALIVE\n");
    run_for(WATCHDOG_MS + 20000);       // first fire
    Serial1.send("ALIVE\n");            // NAS came back
    run_for(WATCHDOG_MS + 20000);       // hung again
    CHECK(presses().size() == 4);
  });

  test("DISARM stops the watchdog", [] {
    boot();
    Serial1.send("ALIVE\n");
    run_for(60000);
    Serial1.send("DISARM\n");
    run_for(3 * WATCHDOG_MS);
    CHECK(presses().empty());
  });

  test("POWEROFF disarms: a powered-off NAS is not switched back on", [] {
    boot();
    Serial1.send("ALIVE\n");
    run_for(60000);
    Serial1.send("\nPOWEROFF\n");
    run_for(3 * WATCHDOG_MS);
    CHECK(presses().size() == 1);
  });

  test("watchdog survives the 49-day millis() wrap", [] {
    boot(0xFFFFFFFFUL - 90000);         // 90 s before the wrap
    for (int i = 0; i < 4; i++) {       // ALIVE across the wrap
      Serial1.send("ALIVE\n");
      run_for(60000);
    }
    CHECK(presses().empty());
    run_for(WATCHDOG_MS);
    CHECK(presses().size() == 2);
  });

  test("USB commands work without a USB host attached", [] {
    boot();
    Serial.connected = false;           // standalone on 5VSB
    Serial1.send("\nPOWEROFF\n");
    run_for(20000);
    CHECK(presses().size() == 1);
    CHECK(Serial.out.empty());
  });

  test("STATUS and PING answer and touch nothing", [] {
    boot();
    Serial.send("PING\nSTATUS\n");
    run_for(200);
    Serial1.send("ALIVE\n");
    run_for(30000);
    Serial.send("STATUS\n");
    run_for(200);
    CHECK(presses().empty());
    CHECK(Serial.out.find("pong") != std::string::npos);
    CHECK(Serial.out.find("watchdog: disarmed") != std::string::npos);
    CHECK(Serial.out.find("watchdog: armed, last ALIVE s ago: 30") != std::string::npos);
  });

  std::printf(failures ? "\n%d check(s) failed\n" : "\nall passed\n", failures);
  return failures != 0;
}
