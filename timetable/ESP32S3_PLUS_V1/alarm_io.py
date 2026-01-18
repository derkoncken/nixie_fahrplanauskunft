# alarm_io.py — Button/LED/Buzzer + Alarm-Logik
import time
from machine import Pin, PWM

_DEBOUNCE_MS = 200

BLINK_INTERVAL_MS = 250
BEEP_MS = 140
BEEP_FREQ = 880
BEEP_DUTY = 5000

class AlarmIO:
    def __init__(self, btn_gpio, led_gpio, buz_gpio):
        self.button = Pin(btn_gpio, Pin.IN)  # extern Pull-Down: gedrückt = 1
        self.led = Pin(led_gpio, Pin.OUT)
        self.led.value(0)

        self.pwm = PWM(Pin(buz_gpio))
        self.pwm.freq(BEEP_FREQ)
        self.pwm.duty_u16(0)

        self._last_irq_ms = 0
        self.arm_request = False

        # state
        self.alarm_armed = False
        self.alarm_triggered = False
        self.last_cd_alarm = None

        self.blink_enabled = False
        self.blink_state = 0
        self.blink_last_ms = 0

        self.button.irq(trigger=Pin.IRQ_RISING, handler=self._btn_irq)

    def _btn_irq(self, pin):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_irq_ms) < _DEBOUNCE_MS:
            return
        self._last_irq_ms = now
        if pin.value() == 1:
            self.arm_request = True
            self.led.value(1)

    def beep_once(self):
        self.pwm.freq(BEEP_FREQ)
        self.pwm.duty_u16(BEEP_DUTY)
        time.sleep_ms(BEEP_MS)
        self.pwm.duty_u16(0)
        time.sleep_ms(BEEP_MS)
        self.pwm.duty_u16(BEEP_DUTY)
        time.sleep_ms(BEEP_MS)
        self.pwm.duty_u16(0)

    def disarm(self):
        self.alarm_armed = False
        self.alarm_triggered = False
        self.blink_enabled = False
        self.blink_state = 0
        self.led.value(0)

    def arm(self):
        self.alarm_armed = True
        self.alarm_triggered = False
        self.blink_enabled = False
        self.blink_state = 0
        self.blink_last_ms = time.ticks_ms()
        self.last_cd_alarm = None
        self.led.value(1)

    def tick_led(self):
        if not self.alarm_armed:
            self.led.value(0)
            return

        if not self.blink_enabled:
            self.led.value(1)
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.blink_last_ms) >= BLINK_INTERVAL_MS:
            self.blink_last_ms = now
            self.blink_state ^= 1
            self.led.value(self.blink_state)

    def pick_alarm_result(self, r1, r2, alarm_source):
        return r2 if alarm_source == 1 else r1

    def apply_alarm_logic(self, r1, r2, alarm_source, alarm_threshold_min):
        """
        Gibt True zurück, wenn ein Beep beim Fetch sinnvoll wäre (wenn Alarm bereits getriggert).
        """
        r_alarm = self.pick_alarm_result(r1, r2, alarm_source)
        cd_alarm = r_alarm[0] if r_alarm is not None else None

        if self.alarm_armed:
            if (cd_alarm is not None) and (cd_alarm < alarm_threshold_min) and (not self.alarm_triggered):
                self.alarm_triggered = True
                self.blink_enabled = True
                self.blink_state = 1
                self.blink_last_ms = time.ticks_ms()
                self.beep_once()

            if self.alarm_triggered:
                if cd_alarm is None:
                    self.disarm()
                elif (self.last_cd_alarm is not None) and (cd_alarm > self.last_cd_alarm) and (cd_alarm >= alarm_threshold_min):
                    self.disarm()

        self.last_cd_alarm = cd_alarm
        return self.alarm_triggered
