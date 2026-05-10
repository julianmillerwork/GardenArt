import math
import random
import struct

# =========================================================
# Configuration
# =========================================================
NUM_LEDS = 300
FPS = 30
DURATION_SECONDS = 20
TOTAL_FRAMES = FPS * DURATION_SECONDS

OUTPUT = "raindrops_rgbw_300x360_grbw32.bin"

NUM_DROPS = 8
SEED = 42

# Very dark background
BG_R = 0
BG_G = 0
BG_B = 2
BG_W = 0

random.seed(SEED)


# =========================================================
# Helpers
# =========================================================
def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def pack_rgbw(r, g, b, w):
    # Stored as 0xGGRRBBWW
    word = (
        (clamp8(g) << 24) |
        (clamp8(r) << 16) |
        (clamp8(b) << 8)  |
        clamp8(w)
    )
    return struct.pack("<I", word)


def add4(a, b):
    return (
        clamp8(a[0] + b[0]),
        clamp8(a[1] + b[1]),
        clamp8(a[2] + b[2]),
        clamp8(a[3] + b[3]),
    )


# =========================================================
# Drop model
# =========================================================
class Drop:
    def __init__(self, initial=False):
        self.reset(initial=initial)

    def reset(self, initial=False):
        if initial:
            self.pos = random.uniform(0, NUM_LEDS - 1)
        else:
            self.pos = random.uniform(-40, -5)

        self.speed = random.uniform(0.35, 1.0)      # LEDs per frame
        self.radius = random.uniform(2.0, 5.5)
        self.tail = random.uniform(4.0, 12.0)
        self.brightness = random.uniform(0.45, 1.0)

        # Cool watery tones
        self.r_base = random.uniform(0, 10)
        self.g_base = random.uniform(25, 90)
        self.b_base = random.uniform(120, 255)
        self.w_base = random.uniform(5, 80)

    def step(self):
        self.pos += self.speed
        if self.pos - self.tail > NUM_LEDS + 2:
            self.reset(initial=False)

    def contribution(self, i):
        # head + trailing tail
        delta = i - self.pos

        # ahead of head: tiny glow only
        if delta > self.radius:
            return (0, 0, 0, 0)

        # behind the head: long fading tail
        if delta < -self.tail:
            return (0, 0, 0, 0)

        if delta >= 0:
            # rounded head
            x = delta / self.radius if self.radius > 0 else 0
            falloff = math.exp(-3.2 * x * x) * self.brightness
            sparkle = math.exp(-12.0 * x * x) * self.brightness
        else:
            # longer rear trail
            x = (-delta) / self.tail if self.tail > 0 else 0
            falloff = math.exp(-2.0 * x * x) * self.brightness * 0.85
            sparkle = math.exp(-20.0 * x * x) * self.brightness * 0.25

        r = self.r_base * falloff
        g = self.g_base * falloff
        b = self.b_base * falloff
        w = self.w_base * (0.45 * falloff + 0.9 * sparkle)

        return (
            clamp8(r),
            clamp8(g),
            clamp8(b),
            clamp8(w),
        )


# =========================================================
# Animation generation
# =========================================================
def subtle_background(frame_idx):
    # very gentle breathing in the deep blue
    t = frame_idx / FPS
    mod = 0.88 + 0.12 * math.sin(2 * math.pi * 0.12 * t)
    return (
        clamp8(BG_R * mod),
        clamp8(BG_G * mod),
        clamp8(BG_B * mod),
        clamp8(BG_W * mod),
    )


def generate():
    drops = [Drop(initial=True) for _ in range(NUM_DROPS)]

    with open(OUTPUT, "wb") as f:
        for frame in range(TOTAL_FRAMES):
            bg = subtle_background(frame)

            for i in range(NUM_LEDS):
                colour = bg

                for d in drops:
                    colour = add4(colour, d.contribution(i))

                f.write(pack_rgbw(*colour))

            for d in drops:
                d.step()

    print("Wrote", OUTPUT)
    print("Frames:", TOTAL_FRAMES)
    print("LEDs:", NUM_LEDS)
    print("FPS:", FPS)


generate()