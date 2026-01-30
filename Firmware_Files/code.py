# AI Hackpad - My custom macro pad for AI shortcuts + RGB + volume control :)

import time
import board
import digitalio
import rotaryio
import neopixel
import displayio
from adafruit_display_text import label
import terminalio

# HID stuff so the board can act like a keyboard + media keys
import usb_hid
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# ----- My pin setup -----

# 6 RGB LEDs (SK6812 Mini) on GP3
NUM_LEDS = 6
LED_PIN = board.GP3

# I’m using 4 buttons for 4 different AI tools
BUTTON_PINS = [
    board.GP26,  # Button 1
    board.GP27,  # Button 2
    board.GP28,  # Button 3
    board.GP29,  # Button 4
]

# Rotary encoder pins (this controls volume + RGB settings)
ENC_A = board.GP0
ENC_B = board.GP1
ENC_SW = board.GP2

# OLED screen uses I2C (the XIAO RP2040 has SDA on GP6 and SCL on GP7)
OLED_ADDR = 0x3C  # most 0.91" OLEDs use this

# ----- HID setup -----
consumer = ConsumerControl(usb_hid.devices)
kbd = Keyboard(usb_hid.devices)

# ----- LED setup -----
pixels = neopixel.NeoPixel(LED_PIN, NUM_LEDS, auto_write=False)

# Quick HSV to RGB function because I want to mess with colors easily
def hsv_to_rgb(h, s, v):
    h = float(h) % 1.0
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i %= 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)

# ----- Button setup -----
buttons = []
for pin in BUTTON_PINS:
    b = digitalio.DigitalInOut(pin)
    b.direction = digitalio.Direction.INPUT
    b.pull = digitalio.Pull.UP  # buttons go to GND so this makes them work
    buttons.append(b)

# ----- Encoder setup -----
enc = rotaryio.IncrementalEncoder(ENC_A, ENC_B)
last_enc_pos = enc.position

enc_button = digitalio.DigitalInOut(ENC_SW)
enc_button.direction = digitalio.Direction.INPUT
enc_button.pull = digitalio.Pull.UP  # also active low

# ----- OLED setup -----
displayio.release_displays()
i2c = board.I2C()

try:
    import adafruit_displayio_ssd1306
    display_bus = displayio.I2CDisplay(i2c, device_address=OLED_ADDR)
    display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=32)

    # I made a little UI with two lines of text
    ui = displayio.Group()
    title = label.Label(terminalio.FONT, text="AI Pad Ready", x=2, y=2)
    status = label.Label(terminalio.FONT, text="", x=2, y=18)
    ui.append(title)
    ui.append(status)
    display.show(ui)
except Exception as e:
    print("OLED didn't start:", e)
    display = None
    title = None
    status = None

# ----- LED color/brightness settings -----
hue = 0.0
sat = 1.0
brightness_levels = [0.0, 0.2, 0.5, 1.0]  # I can cycle these with encoder press
brightness_index = 2
rgb_on = brightness_levels[brightness_index] > 0

def update_pixels():
    if not rgb_on:
        pixels.fill((0,0,0))
    else:
        r, g, b = hsv_to_rgb(hue, sat, brightness_levels[brightness_index])
        pixels.fill((r, g, b))
    pixels.show()

update_pixels()

# These 4 shortcuts will be sent when pressing buttons 1–4
# I'll use AutoHotkey or Mac Shortcuts to open ChatGPT / Gemini / etc.
ai_shortcuts = [
    (Keycode.CONTROL, Keycode.ALT, Keycode.ONE),
    (Keycode.CONTROL, Keycode.ALT, Keycode.TWO),
    (Keycode.CONTROL, Keycode.ALT, Keycode.THREE),
    (Keycode.CONTROL, Keycode.ALT, Keycode.FOUR),
]

# helper to press a shortcut cleanly
def send_hotkey(combo):
    mods = combo[:-1]
    key = combo[-1]
    for m in mods:
        kbd.press(m)
    kbd.press(key)
    kbd.release_all()

# I keep track of button states so I don't spam the shortcuts
last_btn = [True] * len(buttons)

def long_press(pin, hold_time=0.6):
    if not pin.value:
        t0 = time.monotonic()
        while not pin.value:
            if time.monotonic() - t0 > hold_time:
                return "long"
        return "short"
    return None

# ----- MAIN LOOP -----
while True:

    # ----- BUTTON LOGIC -----
    for i, btn in enumerate(buttons):
        pressed = not btn.value  # active low
        if pressed != (not last_btn[i]):
            if pressed:
                # update OLED text
                if title:
                    title.text = f"AI Button {i+1}"
                    status.text = "Launching..."

                send_hotkey(ai_shortcuts[i])
            else:
                if status:
                    status.text = ""
        last_btn[i] = not pressed

    # ----- ENCODER ROTATION = volume up/down -----
    pos = enc.position
    if pos != last_enc_pos:
        diff = pos - last_enc_pos

        if diff > 0:
            for _ in range(diff):
                consumer.send(ConsumerControlCode.VOLUME_INCREMENT)
        else:
            for _ in range(-diff):
                consumer.send(ConsumerControlCode.VOLUME_DECREMENT)

        last_enc_pos = pos
        if status:
            status.text = "Volume"

    # ----- ENCODER BUTTON = RGB control -----
    if not enc_button.value:
        action = long_press(enc_button)
        if action == "short":
            # switch brightness presets
            brightness_index = (brightness_index + 1) % len(brightness_levels)
            rgb_on = brightness_levels[brightness_index] > 0
            update_pixels()
            if title:
                title.text = f"RGB preset {brightness_index+1}"
            time.sleep(0.25)
        elif action == "long":
            # full toggle
            rgb_on = not rgb_on
            update_pixels()
            if title:
                title.text = "RGB Off" if not rgb_on else "RGB On"
            time.sleep(0.4)

    time.sleep(0.02)  # lil delay so we don't hog CPU
