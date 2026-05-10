import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "raindrops_running_glass_600x600_grb32.bin"


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


def smoothstep(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def pulse_window(loop_u, start_u, dur_u):
    """
    Loop-safe time window:
    returns 0 before start, ramps up, then ramps down over duration.
    """
    t = loop_u - start_u
    if t < 0.0:
        t += 1.0

    if t >= dur_u:
        return 0.0

    x = t / dur_u

    # rise then fall, smooth
    if x < 0.2:
        return smoothstep(x / 0.2)
    if x > 0.8:
        return smoothstep((1.0 - x) / 0.2)
    return 1.0


def droplet_head_profile(p, centre_p, half_width_p):
    d = abs(p - centre_p)
    if d >= half_width_p:
        return 0.0
    x = 1.0 - (d / half_width_p)
    return x * x * x


def droplet_tail_profile(p, head_p, tail_len):
    """
    Tail trails above the moving head.
    Assumes droplets move downward, so tail is "above" head
    on the strip.
    """
    if p > head_p:
        return 0.0

    d = head_p - p
    if d >= tail_len:
        return 0.0

    x = 1.0 - (d / tail_len)
    return x * x


def background(p, theta):
    """
    Dark rainy glass background with subtle motion.
    """
    x = 2.0 * math.pi * p

    wave1 = 0.5 + 0.5 * math.sin(1.4 * x + 1.0 * theta + 0.4)
    wave2 = 0.5 + 0.5 * math.sin(3.8 * x - 2.0 * theta + 1.1)
    wave3 = 0.5 + 0.5 * math.sin(0.7 * x + 3.0 * theta + 2.4)

    glow = wave1 * 0.42 + wave2 * 0.36 + wave3 * 0.22
    glow = glow ** 1.5

    # cool deep blue background
    base_r = 0
    base_g = 4 + 5 * glow
    base_b = 14 + 12 * glow

    return base_r, base_g, base_b


# -------------------------------------------------
# Droplet definitions
#
# start_u    : when droplet begins
# dur_u      : duration of travel
# start_p    : start position near top
# end_p      : end position lower down
# width_p    : droplet head width
# tail_len   : trail length
# strength   : overall brightness
# coldness   : more blue-white highlight
# -------------------------------------------------
DROPLETS = [
    {"start_u": 0.01, "dur_u": 0.16, "start_p": 0.06, "end_p": 0.30, "width_p": 0.012, "tail_len": 0.10, "strength": 1.00, "coldness": 1.0},
    {"start_u": 0.05, "dur_u": 0.20, "start_p": 0.14, "end_p": 0.48, "width_p": 0.010, "tail_len": 0.13, "strength": 0.90, "coldness": 1.1},
    {"start_u": 0.09, "dur_u": 0.18, "start_p": 0.28, "end_p": 0.62, "width_p": 0.011, "tail_len": 0.11, "strength": 1.15, "coldness": 0.9},
    {"start_u": 0.14, "dur_u": 0.15, "start_p": 0.10, "end_p": 0.25, "width_p": 0.009, "tail_len": 0.08, "strength": 0.85, "coldness": 1.0},
    {"start_u": 0.19, "dur_u": 0.24, "start_p": 0.42, "end_p": 0.86, "width_p": 0.012, "tail_len": 0.16, "strength": 1.10, "coldness": 1.15},
    {"start_u": 0.24, "dur_u": 0.17, "start_p": 0.18, "end_p": 0.44, "width_p": 0.010, "tail_len": 0.10, "strength": 0.95, "coldness": 0.95},
    {"start_u": 0.29, "dur_u": 0.21, "start_p": 0.55, "end_p": 0.90, "width_p": 0.011, "tail_len": 0.15, "strength": 1.20, "coldness": 1.2},
    {"start_u": 0.35, "dur_u": 0.16, "start_p": 0.08, "end_p": 0.36, "width_p": 0.009, "tail_len": 0.09, "strength": 0.88, "coldness": 1.0},
    {"start_u": 0.41, "dur_u": 0.19, "start_p": 0.24, "end_p": 0.57, "width_p": 0.010, "tail_len": 0.12, "strength": 1.00, "coldness": 1.05},
    {"start_u": 0.47, "dur_u": 0.14, "start_p": 0.36, "end_p": 0.52, "width_p": 0.008, "tail_len": 0.07, "strength": 0.82, "coldness": 0.9},
    {"start_u": 0.53, "dur_u": 0.22, "start_p": 0.62, "end_p": 0.97, "width_p": 0.012, "tail_len": 0.17, "strength": 1.18, "coldness": 1.15},
    {"start_u": 0.60, "dur_u": 0.18, "start_p": 0.12, "end_p": 0.40, "width_p": 0.010, "tail_len": 0.10, "strength": 0.92, "coldness": 1.0},
    {"start_u": 0.67, "dur_u": 0.20, "start_p": 0.30, "end_p": 0.69, "width_p": 0.011, "tail_len": 0.14, "strength": 1.08, "coldness": 1.1},
    {"start_u": 0.74, "dur_u": 0.15, "start_p": 0.16, "end_p": 0.33, "width_p": 0.009, "tail_len": 0.08, "strength": 0.86, "coldness": 0.95},
    {"start_u": 0.81, "dur_u": 0.19, "start_p": 0.48, "end_p": 0.82, "width_p": 0.010, "tail_len": 0.13, "strength": 1.05, "coldness": 1.05},
    {"start_u": 0.89, "dur_u": 0.16, "start_p": 0.22, "end_p": 0.50, "width_p": 0.010, "tail_len": 0.10, "strength": 0.94, "coldness": 1.0},
]


def add_running_droplets(p, loop_u):
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0

    for d in DROPLETS:
        # loop-safe forward time from droplet start
        t = loop_u - d["start_u"]
        if t < 0.0:
            t += 1.0

        if t >= d["dur_u"]:
            continue

        u = t / d["dur_u"]

        # smooth motion from start to end
        move = smoothstep(u)
        head_p = d["start_p"] + (d["end_p"] - d["start_p"]) * move

        # fade in/out over lifetime
        life_env = pulse_window(loop_u, d["start_u"], d["dur_u"])
        if life_env <= 0.0:
            continue

        # head
        head = droplet_head_profile(p, head_p, d["width_p"])
        if head > 0.0:
            s = head * life_env * d["strength"]

            add_r += s * 20
            add_g += s * 120
            add_b += s * 255

            # cold white highlight inside head
            core = head * head * life_env * d["strength"]
            add_r += core * 24 * d["coldness"]
            add_g += core * 40 * d["coldness"]
            add_b += core * 55 * d["coldness"]

        # trailing tail
        tail = droplet_tail_profile(p, head_p, d["tail_len"])
        if tail > 0.0:
            # tail fades as droplet moves
            tail_env = life_env * (0.85 - 0.25 * u)
            if tail_env < 0.0:
                tail_env = 0.0

            s = tail * tail_env * d["strength"]

            add_r += s * 2
            add_g += s * 26
            add_b += s * 90

    return add_r, add_g, add_b


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        loop_u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * loop_u

        for i in range(NUM_LEDS):
            p = i / NUM_LEDS

            r, g, b = background(p, theta)
            dr, dg, db = add_running_droplets(p, loop_u)

            r += dr
            g += dg
            b += db

            r = clamp8(r)
            g = clamp8(g)
            b = clamp8(b)

            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)