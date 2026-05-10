import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 120
FPS = 30
OUTPUT = "aurora_4_grb32_188.dlt"

# Delta settings
KEYFRAME_INTERVAL = 20
DELTA_MAX_CHANGES_RATIO = 0.85


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
    return x * x * (3.0 - 2.0 * x)


def spatial_burst_profile(p, centre_p, half_width_p):
    """
    Spatial burst envelope across the strip.
    p            : LED position 0..1
    centre_p     : burst centre 0..1
    half_width_p : burst half-width 0..1
    """
    d = abs(p - centre_p)
    if d >= half_width_p:
        return 0.0

    x = 1.0 - (d / half_width_p)
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
# -------------------------------------------------
BURSTS = [
    {"centre_u": 0.06, "half_u": 0.020, "centre_p": 0.18, "half_p": 0.070, "strength": 1.00, "pinkness": 2.00, "blue_boost": 0.80},
    {"centre_u": 0.12, "half_u": 0.030, "centre_p": 0.72, "half_p": 0.090, "strength": 0.85, "pinkness": 1.90, "blue_boost": 1.00},
    {"centre_u": 0.21, "half_u": 0.018, "centre_p": 0.40, "half_p": 0.060, "strength": 1.15, "pinkness": 2.10, "blue_boost": 0.75},
    {"centre_u": 0.29, "half_u": 0.025, "centre_p": 0.82, "half_p": 0.075, "strength": 0.95, "pinkness": 2.00, "blue_boost": 0.95},
    {"centre_u": 0.36, "half_u": 0.022, "centre_p": 0.10, "half_p": 0.065, "strength": 1.10, "pinkness": 2.20, "blue_boost": 0.70},
    {"centre_u": 0.44, "half_u": 0.028, "centre_p": 0.56, "half_p": 0.085, "strength": 0.90, "pinkness": 1.95, "blue_boost": 1.05},
    {"centre_u": 0.53, "half_u": 0.020, "centre_p": 0.30, "half_p": 0.060, "strength": 1.20, "pinkness": 2.15, "blue_boost": 0.85},
    {"centre_u": 0.61, "half_u": 0.032, "centre_p": 0.88, "half_p": 0.095, "strength": 0.85, "pinkness": 1.85, "blue_boost": 1.10},
    {"centre_u": 0.69, "half_u": 0.019, "centre_p": 0.47, "half_p": 0.055, "strength": 1.25, "pinkness": 2.25, "blue_boost": 0.75},
    {"centre_u": 0.77, "half_u": 0.026, "centre_p": 0.20, "half_p": 0.080, "strength": 0.90, "pinkness": 2.00, "blue_boost": 0.95},
    {"centre_u": 0.86, "half_u": 0.021, "centre_p": 0.66, "half_p": 0.065, "strength": 1.10, "pinkness": 2.05, "blue_boost": 0.90},
    {"centre_u": 0.94, "half_u": 0.024, "centre_p": 0.93, "half_p": 0.075, "strength": 1.00, "pinkness": 2.10, "blue_boost": 0.80},
]


def add_discrete_bursts(p, loop_u, glow):
    """
    Returns additional (r, g, b) from explicit burst events.
    """
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0

    glow_bias = 0.55 + 0.45 * glow

    for burst in BURSTS:
        t_env = smooth_pulse(loop_u, burst["centre_u"], burst["half_u"])
        if t_env <= 0.0:
            continue

        s_env = spatial_burst_profile(p, burst["centre_p"], burst["half_p"])
        if s_env <= 0.0:
            continue

        env = t_env * s_env * glow_bias * burst["strength"]

        add_r += env * 190.0 * burst["pinkness"]
        add_g += env * 42.0
        add_b += env * 145.0 * burst["blue_boost"]

        core = env * env
        add_r += core * 70.0 * burst["pinkness"]
        add_g += core * 10.0
        add_b += core * 55.0 * burst["blue_boost"]

    return add_r, add_g, add_b


def build_frame(frame_index):
    loop_u = frame_index / TOTAL_FRAMES
    theta = 2.0 * math.pi * loop_u

    frame = []
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