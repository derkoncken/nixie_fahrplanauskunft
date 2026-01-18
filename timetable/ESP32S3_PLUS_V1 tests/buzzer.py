from machine import Pin, PWM
import time

BTN_GPIO = 43     # Button an GPIO3 (D2)
LED_GPIO = 44     # LED an GPIO4 (D3)  <- falls deine LED wirklich an GPIO3 hängt: geht nicht mit Button zusammen
BUZ_GPIO = 6     # Buzzer an GPIO2 (D1)

button = Pin(BTN_GPIO, Pin.IN)        # extern Pull-Down, gedrückt = 1
led    = Pin(LED_GPIO, Pin.OUT)

pwm = PWM(Pin(BUZ_GPIO))
pwm.freq(440)
pwm.duty_u16(0)  # aus

def is_pressed_debounced(samples=6, spacing_ms=5):
    for _ in range(samples):
        if button.value() != 1:
            return False
        time.sleep_ms(spacing_ms)
    return True

while True:
    if is_pressed_debounced():
        led.value(1)
        pwm.duty_u16(4000)  # an
        # warten bis losgelassen
        while button.value() == 1:
            time.sleep_ms(10)
        pwm.duty_u16(0)     # aus
        led.value(0)

    time.sleep_ms(10)
