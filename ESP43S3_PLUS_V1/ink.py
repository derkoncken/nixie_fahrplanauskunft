# ink.py — Waveshare 2.9" V2 (296x128) am ESP32-S3 (MicroPython)
from machine import Pin, SPI
import time
import framebuf

# GPIOs (XIAO ESP32S3)
BUSY = 1   # D0
RST  = 2   # D1
DC   = 3   # D2
CS   = 4   # D3
SCK  = 7   # D8
MOSI = 9   # D10

spi = SPI(2, baudrate=2_000_000, polarity=0, phase=0,
          sck=Pin(SCK), mosi=Pin(MOSI), miso=None)

cs   = Pin(CS, Pin.OUT, value=1)
dc   = Pin(DC, Pin.OUT, value=0)
rst  = Pin(RST, Pin.OUT, value=1)

# Bei dir hat es funktioniert: busy "active HIGH" -> 1=busy, 0=idle
busy = Pin(BUSY, Pin.IN, Pin.PULL_UP)


class EPD29V2:
    W, H = 128, 296  # native Auflösung (Portrait)

    def __init__(self):
        self.buf = bytearray(self.W * self.H // 8)
        self.fb = framebuf.FrameBuffer(self.buf, self.W, self.H, framebuf.MONO_HLSB)
        time.sleep_ms(200)
        self.reset()
        self.init()

    def _cmd(self, c):
        dc.value(0); cs.value(0)
        spi.write(bytes([c & 0xFF]))
        cs.value(1)

    def _data(self, b):
        dc.value(1); cs.value(0)
        spi.write(b)
        cs.value(1)

    def reset(self):
        cs.value(1)
        dc.value(0)
        rst.value(0); time.sleep_ms(200)
        rst.value(1); time.sleep_ms(200)

    def wait_idle(self, timeout_ms=20000):
        t0 = time.ticks_ms()
        while busy.value() == 1:  # 1 = busy
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                raise RuntimeError("BUSY timeout: bleibt HIGH (busy).")
            time.sleep_ms(20)

    def init(self):
        self.wait_idle()
        self._cmd(0x12)  # SWRESET
        self.wait_idle()

        self._cmd(0x01)  # Driver output control
        self._data(bytes([0x27, 0x01, 0x00]))

        self._cmd(0x11)  # Data entry mode
        self._data(bytes([0x03]))

        # Window full
        self._cmd(0x44)  # X: 0..15
        self._data(bytes([0x00, (self.W // 8) - 1]))

        self._cmd(0x45)  # Y: 0..295
        self._data(bytes([0x00, 0x00, (self.H - 1) & 0xFF, ((self.H - 1) >> 8) & 0xFF]))

        # Border (bewährter Wert bei dir)
        self._cmd(0x3C)
        self._data(bytes([0x05]))

        # Cursor
        self._cmd(0x4E); self._data(bytes([0x00]))
        self._cmd(0x4F); self._data(bytes([0x00, 0x00]))

        self.wait_idle()

    def display(self):
        self._cmd(0x24)          # WRITE_RAM
        self._data(self.buf)
        self._cmd(0x22)          # UPDATE
        self._data(bytes([0xF7]))
        self._cmd(0x20)          # MASTER_ACTIVATE
        self.wait_idle()

    def clear(self):
        self.fb.fill(1)
        self.display()

    def deep_clear(self):
        # optional gegen Rand-/Rausch-Band
        self.fb.fill(0); self.display(); time.sleep_ms(300)
        self.fb.fill(1); self.display(); time.sleep_ms(300)


def rotated_pixel_90(fb, w, h):
    # (x,y) im Querformat -> (w-1-y, x) im echten Buffer
    def p(x, y, c=None):
        xx = w - 1 - y
        yy = x
        if c is None:
            return fb.pixel(xx, yy)
        fb.pixel(xx, yy, c)
    return p


def print_text(fb, pix, text, x, y, size=2, bold=False, color=0):
    # Text skalieren (8x8 Font) + optional fett
    char_w, char_h = 8, 8
    w = len(text) * char_w
    h = char_h

    tmp_buf = bytearray((w * h + 7) // 8)
    tmp = framebuf.FrameBuffer(tmp_buf, w, h, framebuf.MONO_HLSB)
    tmp.fill(1)
    tmp.text(text, 0, 0, 0)

    offsets = [(0, 0)]
    if bold:
        offsets.append((1, 0))

    for ox, oy in offsets:
        for yy in range(h):
            for xx in range(w):
                if tmp.pixel(xx, yy) == 0:
                    for dy in range(size):
                        for dx in range(size):
                            pix(x + xx*size + dx + ox, y + yy*size + dy + oy, color)
