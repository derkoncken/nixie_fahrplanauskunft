from machine import Pin
import time

btn = Pin(0, Pin.IN, Pin.PULL_UP)  # GPIO anpassen!

_last_ms = 0
def on_btn(pin):
    global _last_ms
    now = time.ticks_ms()
    # 200 ms Sperre gegen Prellen / Doppelklick
    if time.ticks_diff(now, _last_ms) < 200:
        return
    _last_ms = now

    if pin.value() == 0:  # gedrückt (active low)
        print("BTN IRQ: gedrückt")

btn.irq(trigger=Pin.IRQ_FALLING, handler=on_btn)

while True:
    time.sleep(1)
