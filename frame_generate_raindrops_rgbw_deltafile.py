import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 600
FPS = 30
OUTPUT = "raindrops_70_grb32_188.dlt"

# Delta settings
KEYFRAME_INTERVAL = 20
DELTA_MAX_CHANGES_RATIO = 0.45


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
        # -----------------------------
        # Fast bright falling drop
        # -----------------------------
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


def build_frame(frame_index):
    loop_u = frame_index / TOTAL_FRAMES
    theta = 2.0 * math.pi * loop_u

    frame = []
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

        # Store as RGBW-style bytes for DLT, with W always zero
        frame.append((r, g, b, 0))

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
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)
if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)