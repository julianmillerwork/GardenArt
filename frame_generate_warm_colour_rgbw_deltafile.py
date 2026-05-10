import math
import random
import struct

NUM_LEDS = 70
TOTAL_FRAMES = 600
FPS = 30
OUTPUT = "candle_white_magenta_gold_70x600.dlt"

# Delta tuning
KEYFRAME_INTERVAL = 24
DELTA_MAX_CHANGES_RATIO = 0.82

# Repeatable randomness
SEED = 24680


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def smoothstep01(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def pulse01(x):
    if x <= 0.0 or x >= 1.0:
        return 0.0
    if x < 0.5:
        return smoothstep01(x * 2.0)
    return smoothstep01((1.0 - x) * 2.0)


def wrap_dist(a, b):
    d = abs(a - b)
    if d > 0.5:
        d = 1.0 - d
    return d


def hsv_to_rgb(h, s, v):
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6

    if i == 0:
        return v, t, p
    elif i == 1:
        return q, v, p
    elif i == 2:
        return p, v, t
    elif i == 3:
        return p, q, v
    elif i == 4:
        return t, p, v
    return v, p, q


def build_bursts():
    """
    Warm magenta/gold whip bursts.
    """
    rng = random.Random(SEED)
    bursts = []

    t = 0
    while t < TOTAL_FRAMES:
        gap = rng.randint(12, 30)
        t += gap
        if t >= TOTAL_FRAMES:
            break

        duration = rng.randint(8, 18)
        centre = rng.uniform(0.08, 0.92)
        width = rng.uniform(0.06, 0.18)
        drift = rng.uniform(-0.16, 0.16)
        strength = rng.uniform(0.75, 1.20)

        # Mostly magenta and gold with slight variation
        if rng.random() < 0.58:
            hue = rng.uniform(0.88, 0.98)   # magenta / pink-red
            sat = rng.uniform(0.72, 0.98)
        else:
            hue = rng.uniform(0.10, 0.16)   # gold / amber
            sat = rng.uniform(0.78, 1.00)

        bursts.append({
            "start": t,
            "duration": duration,
            "centre": centre,
            "width": width,
            "drift": drift,
            "strength": strength,
            "hue": hue,
            "sat": sat,
        })

    return bursts


BURSTS = build_bursts()


def candle_white_background(p, loop_u):
    """
    Warm candle-white base:
    - strong W channel
    - amber body
    - gentle living movement
    """
    w1 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 0.85 + loop_u * 0.23))
    w2 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 2.4 - loop_u * 0.47 + 0.19))
    w3 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 5.6 + loop_u * 0.91 + 0.53))

    body = w1 * 0.50 + w2 * 0.32 + w3 * 0.18
    body = body ** 1.7

    flicker1 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (loop_u * 1.8 + p * 0.35))
    flicker2 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (loop_u * 3.4 - p * 0.55 + 0.27))
    flicker = (0.65 * flicker1 + 0.35 * flicker2) ** 1.8

    # Warm white core
    w = 105 + 95 * body + 28 * flicker

    # Amber / candle warmth on RGB
    r = 26 + 36 * body + 20 * flicker
    g = 10 + 16 * body + 8 * flicker
    b = 2 + 5 * body

    # Occasional subtle warmer pockets
    warmth_wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 1.1 - loop_u * 0.31 + 0.4))
    r += 8 * warmth_wave
    g += 3 * warmth_wave

    return r, g, b, w


def add_magenta_gold_bursts(p, frame_index):
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0
    add_w = 0.0

    for burst in BURSTS:
        start = burst["start"]
        end = start + burst["duration"]
        if frame_index < start or frame_index >= end:
            continue

        u = (frame_index - start) / burst["duration"]
        t_env = pulse01(u)

        centre = (burst["centre"] + burst["drift"] * (u - 0.5)) % 1.0
        d = wrap_dist(p, centre)
        if d >= burst["width"]:
            continue

        spatial = 1.0 - (d / burst["width"])
        spatial = spatial * spatial * spatial

        env = t_env * spatial * burst["strength"]

        rr, gg, bb = hsv_to_rgb(burst["hue"], burst["sat"], 1.0)

        # Main whip colour
        add_r += rr * 195.0 * env
        add_g += gg * 165.0 * env
        add_b += bb * 185.0 * env

        # White-hot inner core
        core = env * env
        add_w += 78.0 * core

        # Slight warm bloom around the core
        add_r += rr * 42.0 * core
        add_g += gg * 26.0 * core
        add_b += bb * 30.0 * core

    return add_r, add_g, add_b, add_w


def build_frame(frame_index):
    loop_u = frame_index / TOTAL_FRAMES
    frame = []

    for i in range(NUM_LEDS):
        p = i / NUM_LEDS

        r, g, b, w = candle_white_background(p, loop_u)
        br, bg, bb, bw = add_magenta_gold_bursts(p, frame_index)

        r += br
        g += bg
        b += bb
        w += bw

        frame.append((
            clamp8(r),
            clamp8(g),
            clamp8(b),
            clamp8(w),
        ))

    return frame


def write_header(f):
    f.write(b"DLTA")
    f.write(struct.pack("<H", 1))
    f.write(struct.pack("<H", NUM_LEDS))
    f.write(struct.pack("<H", TOTAL_FRAMES))
    f.write(struct.pack("<H", FPS))


def write_keyframe(f, frame):
    f.write(b"\x00")
    for r, g, b, w in frame:
        f.write(bytes((r, g, b, w)))


def write_delta(f, prev_frame, frame):
    changes = []

    for i, (old_px, new_px) in enumerate(zip(prev_frame, frame)):
        if old_px != new_px:
            changes.append((i, new_px))

    f.write(b"\x01")
    f.write(struct.pack("<H", len(changes)))

    for index, (r, g, b, w) in changes:
        f.write(struct.pack("<H", index))
        f.write(bytes((r, g, b, w)))

    return len(changes)


with open(OUTPUT, "wb") as f:
    write_header(f)

    prev_frame = None
    keyframes = 0
    delta_frames = 0
    total_changes = 0

    for frame_index in range(TOTAL_FRAMES):
        frame = build_frame(frame_index)

        force_keyframe = (
            prev_frame is None or
            (frame_index % KEYFRAME_INTERVAL == 0)
        )

        if force_keyframe:
            write_keyframe(f, frame)
            keyframes += 1
        else:
            changes = sum(1 for a, b in zip(prev_frame, frame) if a != b)

            if changes > int(NUM_LEDS * DELTA_MAX_CHANGES_RATIO):
                write_keyframe(f, frame)
                keyframes += 1
            else:
                write_delta(f, prev_frame, frame)
                delta_frames += 1
                total_changes += changes

        prev_frame = frame

print("Wrote", OUTPUT)
print("Frames:", TOTAL_FRAMES)
print("LEDs:", NUM_LEDS)
print("FPS:", FPS)
print("Bursts:", len(BURSTS))
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)
if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)