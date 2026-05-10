import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "aurora_600x600_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def wrap_dist(a, b):
    """
    Circular distance on a 0..1 loop.
    """
    d = abs(a - b)
    if d > 0.5:
        d = 1.0 - d
    return d


def smooth_pulse(loop_u, centre_u, half_width_u):
    """
    Loop-safe pulse envelope.
    loop_u       : current phase 0..1
    centre_u     : pulse centre 0..1
    half_width_u : half-width of pulse in loop units

    Returns 0..1
    """
    d = wrap_dist(loop_u, centre_u)
    if d >= half_width_u:
        return 0.0

    x = 1.0 - (d / half_width_u)
    # Smooth bell-like pulse
    return x * x * (3.0 - 2.0 * x)


def spatial_burst_profile(p, centre_p, half_width_p):
    """
    Spatial burst envelope across the strip.
    p          : LED position 0..1
    centre_p   : burst centre 0..1
    half_width_p : burst half-width 0..1
    """
    d = abs(p - centre_p)
    if d >= half_width_p:
        return 0.0

    x = 1.0 - (d / half_width_p)
    # Sharper than the time envelope so it looks like a defined burst region
    return x * x * x


def aurora_background(i, theta):
    """
    Loop-safe aurora background.
    """
    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    wave1 = 0.5 + 0.5 * math.sin(2.2 * x + 1.0 * theta)
    wave2 = 0.5 + 0.5 * math.sin(4.9 * x - 2.0 * theta + 1.3)
    wave3 = 0.5 + 0.5 * math.sin(1.3 * x + 5.0 * theta + 2.1)

    glow = wave1 * 0.42 + wave2 * 0.34 + wave3 * 0.24
    glow = glow ** 1.8

    curtain1 = 0.5 + 0.5 * math.sin(12.0 * x + 3.0 * theta + 0.8)
    curtain2 = 0.5 + 0.5 * math.sin(8.0 * x - 5.0 * theta + 2.4)
    curtain = (curtain1 ** 5) * 0.65 + (curtain2 ** 4) * 0.35
    curtain *= glow

    drift_g = 0.5 + 0.5 * math.sin(1.0 * theta + 0.2)
    drift_b = 0.5 + 0.5 * math.sin(2.0 * theta + 2.0)
    drift_p = 0.5 + 0.5 * math.sin(3.0 * theta + 4.0)

    scene = 0.5 + 0.5 * math.sin(theta - 0.4)

    base_g = 55 + 18 * scene
    base_b = 28 + 14 * scene
    base_r = 4 + 2 * scene

    g = base_g + glow * (145 + 95 * drift_g) + curtain * 70
    b = base_b + glow * (85 + 135 * drift_b) + curtain * 95
    r = base_r + glow * (14 + 50 * drift_p) + curtain * 22

    return r, g, b, glow


# -------------------------------------------------
# Discrete flash burst events
#
# centre_u   = time in loop (0..1)
# half_u     = burst half-duration in loop units
# centre_p   = strip position (0..1)
# half_p     = spatial half-width across strip
# strength   = overall flash strength
# pinkness   = how magenta/pink the flash is
# blue_boost = how icy/blue the flash is
# -------------------------------------------------
BURSTS = [
    {"centre_u": 0.06, "half_u": 0.020, "centre_p": 0.18, "half_p": 0.070, "strength": 1.00, "pinkness": 1.00, "blue_boost": 0.80},
    {"centre_u": 0.12, "half_u": 0.030, "centre_p": 0.72, "half_p": 0.090, "strength": 0.85, "pinkness": 0.90, "blue_boost": 1.00},
    {"centre_u": 0.21, "half_u": 0.018, "centre_p": 0.40, "half_p": 0.060, "strength": 1.15, "pinkness": 1.10, "blue_boost": 0.75},
    {"centre_u": 0.29, "half_u": 0.025, "centre_p": 0.82, "half_p": 0.075, "strength": 0.95, "pinkness": 1.00, "blue_boost": 0.95},
    {"centre_u": 0.36, "half_u": 0.022, "centre_p": 0.10, "half_p": 0.065, "strength": 1.10, "pinkness": 1.20, "blue_boost": 0.70},
    {"centre_u": 0.44, "half_u": 0.028, "centre_p": 0.56, "half_p": 0.085, "strength": 0.90, "pinkness": 0.95, "blue_boost": 1.05},
    {"centre_u": 0.53, "half_u": 0.020, "centre_p": 0.30, "half_p": 0.060, "strength": 1.20, "pinkness": 1.15, "blue_boost": 0.85},
    {"centre_u": 0.61, "half_u": 0.032, "centre_p": 0.88, "half_p": 0.095, "strength": 0.85, "pinkness": 0.85, "blue_boost": 1.10},
    {"centre_u": 0.69, "half_u": 0.019, "centre_p": 0.47, "half_p": 0.055, "strength": 1.25, "pinkness": 1.25, "blue_boost": 0.75},
    {"centre_u": 0.77, "half_u": 0.026, "centre_p": 0.20, "half_p": 0.080, "strength": 0.90, "pinkness": 1.00, "blue_boost": 0.95},
    {"centre_u": 0.86, "half_u": 0.021, "centre_p": 0.66, "half_p": 0.065, "strength": 1.10, "pinkness": 1.05, "blue_boost": 0.90},
    {"centre_u": 0.94, "half_u": 0.024, "centre_p": 0.93, "half_p": 0.075, "strength": 1.00, "pinkness": 1.10, "blue_boost": 0.80},
]


def add_discrete_bursts(p, loop_u, glow):
    """
    Returns additional (r, g, b) from explicit burst events.
    """
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0

    # Slight preference for flashes to read better where aurora already exists
    glow_bias = 0.55 + 0.45 * glow

    for burst in BURSTS:
        t_env = smooth_pulse(loop_u, burst["centre_u"], burst["half_u"])
        if t_env <= 0.0:
            continue

        s_env = spatial_burst_profile(p, burst["centre_p"], burst["half_p"])
        if s_env <= 0.0:
            continue

        env = t_env * s_env * glow_bias * burst["strength"]

        # Pink-violet aurora flash
        add_r += env * 190.0 * burst["pinkness"]
        add_g += env * 42.0
        add_b += env * 145.0 * burst["blue_boost"]

        # Small brighter core for some bursts
        core = env * env
        add_r += core * 70.0 * burst["pinkness"]
        add_g += core * 10.0
        add_b += core * 55.0 * burst["blue_boost"]

    return add_r, add_g, add_b


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        loop_u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * loop_u

        for i in range(NUM_LEDS):
            p = i / NUM_LEDS

            r, g, b, glow = aurora_background(i, theta)
            br, bg, bb = add_discrete_bursts(p, loop_u, glow)

            r += br
            g += bg
            b += bb

            r = clamp8(r)
            g = clamp8(g)
            b = clamp8(b)

            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)