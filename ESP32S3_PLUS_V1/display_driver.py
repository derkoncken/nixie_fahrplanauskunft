# display_driver.py — Waveshare 2.9" V2 (296x128) am ESP32-S3 (MicroPython)
from machine import Pin, SPI
import time
import framebuf

# GPIOs (XIAO ESP32S3)
BUSY = 1
RST  = 2
DC   = 3
CS   = 4
SCK  = 7
MOSI = 9

spi = SPI(2, baudrate=2_000_000, polarity=0, phase=0,
          sck=Pin(SCK), mosi=Pin(MOSI), miso=None)

cs   = Pin(CS, Pin.OUT, value=1)
dc   = Pin(DC, Pin.OUT, value=0)
rst  = Pin(RST, Pin.OUT, value=1)
busy = Pin(BUSY, Pin.IN, Pin.PULL_UP)  # 1=busy, 0=idle (wie bei dir)


class EPD29V2:
    W, H = 128, 296  # native Portrait

    # LUT für Waveshare 2.9" BW V2 (GDEM029T94 V2 / SSD1680)
    # Quelle: GxEPD2_290_T94_V2::lut_partial (0x32 Payload) :contentReference[oaicite:1]{index=1}
    LUT_PARTIAL = bytes([
        0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x80, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x40, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

        0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,

        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

        0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x00, 0x00, 0x00,
    ])

    def __init__(self):
        self.buf  = bytearray(self.W * self.H // 8)
        self.prev = bytearray(self.buf)  # vorheriges Bild (für echtes Partial)
        self.fb   = framebuf.FrameBuffer(self.buf, self.W, self.H, framebuf.MONO_HLSB)

        self._power_is_on = False
        self._using_partial_mode = False

        time.sleep_ms(200)
        self.reset()
        self._init_display()

        # Einmal sauber initialisieren + Controller-RAM sync
        self.fb.fill(1)
        self.display_full_and_sync()

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

    # ----------- Init / Power (wie bewährte Sequenz für V2) -----------
    def _set_partial_ram_area(self, x, y, w, h):
        # RAM entry mode
        self._cmd(0x11); self._data(bytes([0x03]))  # x++, y++ normal

        # x in bytes
        self._cmd(0x44)
        self._data(bytes([x // 8, (x + w - 1) // 8]))

        # y in pixels
        self._cmd(0x45)
        self._data(bytes([
            y & 0xFF, (y >> 8) & 0xFF,
            (y + h - 1) & 0xFF, ((y + h - 1) >> 8) & 0xFF
        ]))

        # cursor
        self._cmd(0x4E); self._data(bytes([x // 8]))
        self._cmd(0x4F); self._data(bytes([y & 0xFF, (y >> 8) & 0xFF]))

    def _init_display(self):
        self.wait_idle()
        self._cmd(0x12)  # SWRESET
        time.sleep_ms(10)

        self._cmd(0x01)  # Driver output control
        self._data(bytes([0x27, 0x01, 0x00]))

        self._cmd(0x11)  # Data entry mode
        self._data(bytes([0x03]))

        self._cmd(0x3C)  # BorderWaveform
        self._data(bytes([0x05]))

        # Display update control (wie in GxEPD2 V2)
        self._cmd(0x21)
        self._data(bytes([0x00, 0x80]))

        # Temperature sensor
        self._cmd(0x18)
        self._data(bytes([0x80]))

        # Full area als Default
        self._set_partial_ram_area(0, 0, self.W, self.H)
        self.wait_idle()

    def _power_on(self):
        if not self._power_is_on:
            self._cmd(0x22); self._data(bytes([0xF8]))
            self._cmd(0x20)
            self.wait_idle()
        self._power_is_on = True

    def _power_off(self):
        if self._power_is_on:
            self._cmd(0x22); self._data(bytes([0x83]))
            self._cmd(0x20)
            self.wait_idle()
        self._power_is_on = False
        self._using_partial_mode = False

    def _init_partial_mode(self):
        if not self._using_partial_mode:
            # sicherheitshalber Basis-Init nochmal
            self._init_display()

            # LUT laden
            self._cmd(0x32)
            self._data(self.LUT_PARTIAL)

            self._power_on()
            self._using_partial_mode = True

    # ----------- Full refresh + Sync -----------
    def display_full_and_sync(self):
        # Full muss "sauber" sein: Reset/Init entfernt evtl. Partial-LUT-Status
        self.reset()
        self._init_display()
        self._power_on()

        # current + old = current
        self._cmd(0x24); self._data(self.buf)
        self._cmd(0x26); self._data(self.buf)

        # Full update trigger (wie V2)
        self._cmd(0x22); self._data(bytes([0xF4]))
        self._cmd(0x20)
        self.wait_idle()

        self.prev[:] = self.buf

        # danach Partial-Modus als "nicht aktiv" markieren
        self._using_partial_mode = False


    # ----------- Partial update (native coords) -----------
    def _extract_window_bytes(self, src, x0_al, y0, x1_al, y1):
        bpr = self.W // 8
        xb0 = x0_al // 8
        xb1 = x1_al // 8
        out = bytearray((xb1 - xb0 + 1) * (y1 - y0 + 1))
        k = 0
        for y in range(y0, y1 + 1):
            row = y * bpr
            sl = src[row + xb0 : row + xb1 + 1]
            out[k:k+len(sl)] = sl
            k += len(sl)
        return out

    def display_partial_native(self, x0, y0, w, h):
        if w <= 0 or h <= 0:
            return

        # Grenzen + X Byte-Alignment
        x1 = x0 + w - 1
        y1 = y0 + h - 1

        if x0 < 0: x0 = 0
        if y0 < 0: y0 = 0
        if x1 >= self.W: x1 = self.W - 1
        if y1 >= self.H: y1 = self.H - 1

        x0_al = (x0 // 8) * 8
        x1_al = ((x1 + 7) // 8) * 8 - 1
        if x1_al >= self.W:
            x1_al = self.W - 1

        self._init_partial_mode()
        self._set_partial_ram_area(x0_al, y0, (x1_al - x0_al + 1), (y1 - y0 + 1))

        new_bytes = self._extract_window_bytes(self.buf,  x0_al, y0, x1_al, y1)
        old_bytes = self._extract_window_bytes(self.prev, x0_al, y0, x1_al, y1)

        # current + old für echtes Partial
        self._cmd(0x24); self._data(new_bytes)
        self._cmd(0x26); self._data(old_bytes)

        # Partial update trigger (V2)
        self._cmd(0x22); self._data(bytes([0xCC]))
        self._cmd(0x20)
        self.wait_idle()

        # prev Fensterbereich aktualisieren
        bpr = self.W // 8
        xb0 = x0_al // 8
        xb1 = x1_al // 8
        for y in range(y0, y1 + 1):
            row = y * bpr
            self.prev[row + xb0 : row + xb1 + 1] = self.buf[row + xb0 : row + xb1 + 1]

    def display_partial_landscape(self, x, y, w, h):
        """
        Partial-Update in Querformat-Koordinaten (dein pix: x=0..295, y=0..127)
        Mapping (wie rotated_pixel_90):
            native_x = y
            native_y = H-1-x
        Rechteck (x..x+w-1, y..y+h-1) =>
            native_x: y..y+h-1
            native_y: H-1-(x+w-1) .. H-1-x
        """
        if w <= 0 or h <= 0:
            return

        x0L, y0L = x, y
        x1L, y1L = x + w - 1, y + h - 1

        nx0 = y0L
        nx1 = y1L
        ny0 = self.H - 1 - x1L
        ny1 = self.H - 1 - x0L

        self.display_partial_native(nx0, ny0, (nx1 - nx0 + 1), (ny1 - ny0 + 1))


# --- Rotation helper (wie bei dir) ---
def rotated_pixel_90(fb, w, h):
    def p(x, y, c=None):
        xx = y
        yy = h - 1 - x
        if c is None:
            return fb.pixel(xx, yy)
        fb.pixel(xx, yy, c)
    return p


def print_text(fb, pix, text, x, y, size=2, bold=False, color=0):
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
