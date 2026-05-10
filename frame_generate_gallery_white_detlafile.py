import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 600          # 20s at 30 FPS
FPS = 30
OUTPUT = "bright_white_w_only_188.dlt"

KEYFRAME_INTERVAL = 20


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def smoothstep(x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def wrap_dist(a, b):
    """
    Circular distance on a 0..1 loop.
    """
    d = abs(a - b)
    if d > 0.5:
        d = 1.0 - d
    return d


def soft_spatial_pulse(p, centre, half_width):
    """
    Soft travelling highlight across the strip.
    """
    d = wrap_dist(p, centre)

    if d >= half_width:
        return 0.0

    x = 1.0 - d / half_width

    # Smooth, elegant falloff.
    return smoothstep(x)


def gentle_shimmer(p, theta):
    """
    Very subtle loop-safe shimmer.

    All frequencies are integers so the first and last frame match.
    """
    s1 = 0.5 + 0.5 * math.sin(2.0 * math.pi * p * 3.0 + 2.0 * theta)
    s2 = 0.5 + 0.5 * math.sin(2.0 * math.pi * p * 7.0 - 3.0 * theta + 1.4)
    s3 = 0.5 + 0.5 * math.sin(2.0 * math.pi * p * 11.0 + 5.0 * theta + 2.2)

    shimmer = 0.50 * s1 + 0.32 * s2 + 0.18 * s3

    # Keep it extremely restrained.
    return shimmer - 0.5


def white_level_for_pixel(i, theta):
    p = i / NUM_LEDS

    # Strong base white level.
    # This is intentionally high because this is a "bright white light" mode.
    base = 210.0

    # Whole-strip slow breathing, very subtle.
    # Range is about ±10.
    breath = 0.5 + 0.5 * math.sin(1.0 * theta)
    breath = smoothstep(breath)
    breath_lift = -6.0 + 12.0 * breath

    # Very soft travelling highlights.
    centre_1 = (theta / (2.0 * math.pi)) % 1.0
    centre_2 = (0.5 - theta / (2.0 * math.pi) * 0.55) % 1.0

    sweep_1 = soft_spatial_pulse(p, centre_1, 0.20)
    sweep_2 = soft_spatial_pulse(p, centre_2, 0.28)

    sweep_lift = 18.0 * sweep_1 + 10.0 * sweep_2

    # Gentle shimmer, only a few brightness counts.
    shimmer = gentle_shimmer(p, theta)
    shimmer_lift = 5.0 * shimmer

    # Slight fixed-position variation so it is not clinically flat.
    fixed_variation = 3.0 * math.sin(2.0 * math.pi * p * 2.0 + 0.6)

    w = base + breath_lift + sweep_lift + shimmer_lift + fixed_variation

    return clamp8(w)


def build_frame(frame_index):
    """
    Build a loop-safe frame.

    frame 0 and frame TOTAL_FRAMES - 1 are identical.
    """
    if TOTAL_FRAMES <= 1:
        u = 0.0
    else:
        u = frame_index / (TOTAL_FRAMES - 1)

    theta = 2.0 * math.pi * u

    frame = []

    for i in range(NUM_LEDS):
        w = white_level_for_pixel(i, theta)

        # RGB deliberately off. W channel only.
        frame.append((0, 0, 0, w))

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

    first_frame = None
    last_frame = None

    for frame_index in range(TOTAL_FRAMES):
        frame = build_frame(frame_index)

        if frame_index == 0:
            first_frame = frame

        if frame_index == TOTAL_FRAMES - 1:
            last_frame = frame

        force_keyframe = (
            prev_frame is None or
            frame_index % KEYFRAME_INTERVAL == 0
        )

        if force_keyframe:
            write_keyframe(f, frame)
            keyframes += 1
        else:
            changes = sum(1 for a, b in zip(prev_frame, frame) if a != b)

            keyframe_size = 1 + (NUM_LEDS * 4)
            delta_size = 1 + 2 + (changes * 6)

            if delta_size >= keyframe_size:
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
print("Duration seconds:", TOTAL_FRAMES / FPS)
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)

if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)

if first_frame == last_frame:
    print("Loop check: first and last frames are identical")
else:
    print("Loop check: WARNING first and last frames differ")