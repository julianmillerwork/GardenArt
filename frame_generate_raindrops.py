import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "raindrops_600x600_grb32.bin"


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
    Loop-safe pulse envelope over time.
    """
    d = wrap_dist(loop_u, centre_u)
    if d >= half_width_u:
        return 0.0

    x = 1.0 - (d / half_width_u)
    return x * x * (3.0 - 2.0 * x)


def drop_streak_profile(p, centre_p, half_width_p):
    """
    Narrow bright raindrop streak.
    """
    d = abs(p - centre_p)
    if d >= half_width_p:
        return 0.0

    x = 1.0 - (d / half_width_p)
    return x * x * x * x


def ripple_profile(p, centre_p, radius, thickness):
    """
    Soft ring-like ripple around centre_p.
    Since this is a 1D strip, ripple appears as a bright band
    moving outward from the centre in both directions.
    """
    d = abs(p - centre_p)
    ring_d = abs(d - radius)

    if ring_d >= thickness:
        return 0.0

    x = 1.0 - (ring_d / thickness)
    return x * x * (3.0 - 2.0 * x)


# -------------------------------------------------
# Drop event list
#
# centre_u  : time of impact / main drop event in loop (0..1)
# centre_p  : strip position (0..1)
# strength  : overall intensity
# width_p   : spatial width of the falling streak
# ripple_max: max ripple radius
# -------------------------------------------------
DROPS = [
    {"centre_u": 0.03, "centre_p": 0.12, "strength": 1.00, "width_p": 0.010, "ripple_max": 0.10},
    {"centre_u": 0.08, "centre_p": 0.58, "strength": 0.85, "width_p": 0.008, "ripple_max": 0.07},
    {"centre_u": 0.13, "centre_p": 0.84, "strength": 1.15, "width_p": 0.012, "ripple_max": 0.12},
    {"centre_u": 0.18, "centre_p": 0.30, "strength": 0.95, "width_p": 0.009, "ripple_max": 0.08},
    {"centre_u": 0.24, "centre_p": 0.70, "strength": 1.05, "width_p": 0.010, "ripple_max": 0.09},
    {"centre_u": 0.29, "centre_p": 0.20, "strength": 0.90, "width_p": 0.008, "ripple_max": 0.07},
    {"centre_u": 0.34, "centre_p": 0.47, "strength": 1.20, "width_p": 0.012, "ripple_max": 0.13},
    {"centre_u": 0.40, "centre_p": 0.90, "strength": 0.80, "width_p": 0.008, "ripple_max": 0.06},
    {"centre_u": 0.46, "centre_p": 0.38, "strength": 1.00, "width_p": 0.010, "ripple_max": 0.09},
    {"centre_u": 0.52, "centre_p": 0.62, "strength": 1.10, "width_p": 0.011, "ripple_max": 0.11},
    {"centre_u": 0.57, "centre_p": 0.08, "strength": 0.85, "width_p": 0.008, "ripple_max": 0.07},
    {"centre_u": 0.63, "centre_p": 0.76, "strength": 1.05, "width_p": 0.010, "ripple_max": 0.10},
    {"centre_u": 0.69, "centre_p": 0.27, "strength": 0.95, "width_p": 0.009, "ripple_max": 0.08},
    {"centre_u": 0.74, "centre_p": 0.54, "strength": 1.25, "width_p": 0.012, "ripple_max": 0.13},
    {"centre_u": 0.80, "centre_p": 0.94, "strength": 0.85, "width_p": 0.008, "ripple_max": 0.07},
    {"centre_u": 0.86, "centre_p": 0.16, "strength": 1.00, "width_p": 0.010, "ripple_max": 0.09},
    {"centre_u": 0.91, "centre_p": 0.66, "strength": 1.10, "width_p": 0.011, "ripple_max": 0.11},
    {"centre_u": 0.97, "centre_p": 0.42, "strength": 0.90, "width_p": 0.009, "ripple_max": 0.08},
]


def background(p, theta):
    """
    Dark rainy blue background with subtle motion.
    """
    x = 2.0 * math.pi * p

    wave1 = 0.5 + 0.5 * math.sin(1.8 * x + 1.0 * theta)
    wave2 = 0.5 + 0.5 * math.sin(4.2 * x - 2.0 * theta + 1.7)
    wave3 = 0.5 + 0.5 * math.sin(0.9 * x + 3.0 * theta + 0.8)

    glow = (wave1 * 0.45 + wave2 * 0.35 + wave3 * 0.20)
    glow = glow ** 1.6

    base_b = 18 + 10 * glow
    base_g = 4 + 5 * glow
    base_r = 0

    return base_r, base_g, base_b


def add_drop_and_ripple(p, loop_u):
    """
    Sum all raindrop events affecting this LED at this time.
    """
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0

    for d in DROPS:
        du = wrap_dist(loop_u, d["centre_u"])

        # -----------------------------
        # Fast bright falling drop
        # -----------------------------
        # very short flash window around impact
        streak_half_u = 0.010
        streak_env = smooth_pulse(loop_u, d["centre_u"], streak_half_u)

        if streak_env > 0.0:
            streak = drop_streak_profile(p, d["centre_p"], d["width_p"])
            if streak > 0.0:
                s = streak_env * streak * d["strength"]
                add_r += s * 20
                add_g += s * 110
                add_b += s * 255

        # -----------------------------
        # Expanding ripple after impact
        # -----------------------------
        # only on the forward side of the loop after impact
        forward = loop_u - d["centre_u"]
        if forward < 0:
            forward += 1.0

        ripple_duration = 0.075
        if forward < ripple_duration:
            t = forward / ripple_duration
            radius = d["ripple_max"] * t
            thickness = 0.010 + 0.010 * (1.0 - t)

            ripple = ripple_profile(p, d["centre_p"], radius, thickness)
            if ripple > 0.0:
                env = (1.0 - t) ** 1.3
                s = ripple * env * d["strength"]

                add_r += s * 8
                add_g += s * 60
                add_b += s * 180

        # -----------------------------
        # Small central glow after hit
        # -----------------------------
        glow_duration = 0.030
        if forward < glow_duration:
            t = forward / glow_duration
            centre_glow = drop_streak_profile(p, d["centre_p"], d["width_p"] * 2.2)
            env = (1.0 - t) ** 1.8
            s = centre_glow * env * d["strength"]

            add_r += s * 10
            add_g += s * 50
            add_b += s * 120

    return add_r, add_g, add_b


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        loop_u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * loop_u

        for i in range(NUM_LEDS):
            p = i / NUM_LEDS

            r, g, b = background(p, theta)
            dr, dg, db = add_drop_and_ripple(p, loop_u)

            r += dr
            g += dg
            b += db

            r = clamp8(r)
            g = clamp8(g)
            b = clamp8(b)

            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)