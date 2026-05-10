from time import sleep
import random

NUM_LEDS = 300

from pi_pico_neopixel.pi_pico_neopixel import Neopixel
pixels = Neopixel(NUM_LEDS, 0, 0, "GRB", transfer_mode="PUT", delay=0)



# Create a list of active drops
# Each drop is {"pos": int, "age": int}
drops = []

def clamp(x):
    if x < 0:
        return 0
    if x > 255:
        return 255
    return int(x)

def add_colour(c1, c2):
    return (
        clamp(c1[0] + c2[0]),
        clamp(c1[1] + c2[1]),
        clamp(c1[2] + c2[2]),
    )

def scale_colour(col, factor):
    return (
        clamp(col[0] * factor),
        clamp(col[1] * factor),
        clamp(col[2] * factor),
    )

while True:
    # Dark blue base
    frame = [(0, 4, 12)] * NUM_LEDS

    # Randomly add a new drop
    if random.getrandbits(3) == 0:   # about 1 in 8 frames
        drops.append({"pos": random.randint(0, NUM_LEDS - 1), "age": 0})

    new_drops = []

    for drop in drops:
        pos = drop["pos"]
        age = drop["age"]

        # Ripple profile by age
        # centre strongest, then spreads outward and fades
        if age == 0:
            ripple = [
                (0, 1.0),
            ]
        elif age == 1:
            ripple = [
                (0, 0.5),
                (-1, 0.7), (1, 0.7),
            ]
        elif age == 2:
            ripple = [
                (0, 0.25),
                (-1, 0.5), (1, 0.5),
                (-2, 0.65), (2, 0.65),
            ]
        elif age == 3:
            ripple = [
                (0, 0.1),
                (-1, 0.25), (1, 0.25),
                (-2, 0.45), (2, 0.45),
                (-3, 0.55), (3, 0.55),
            ]
        elif age == 4:
            ripple = [
                (-1, 0.12), (1, 0.12),
                (-2, 0.25), (2, 0.25),
                (-3, 0.35), (3, 0.35),
                (-4, 0.4),  (4, 0.4),
            ]
        elif age == 5:
            ripple = [
                (-2, 0.1), (2, 0.1),
                (-3, 0.18), (3, 0.18),
                (-4, 0.25), (4, 0.25),
                (-5, 0.3),  (5, 0.3),
            ]
        else:
            ripple = []

        # Blue droplet colour
        for offset, strength in ripple:
            i = pos + offset
            if 0 <= i < NUM_LEDS:
                drop_col = scale_colour((20, 120, 255), strength)
                frame[i] = add_colour(frame[i], drop_col)

        # Keep drop alive for a few frames
        if age < 5:
            new_drops.append({"pos": pos, "age": age + 1})

    drops = new_drops

    # Write frame to LEDs
    for i in range(NUM_LEDS):
        pixels[i] = frame[i]

    pixels.show()
    #sleep(0.01)
