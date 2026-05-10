import struct

NUM_LEDS = 188 
TOTAL_FRAMES = 300      # 10 seconds at 30 FPS
FPS = 30
OUTPUT = "alternate_purple_yellow_fade_out_and_back_188.dlt"

KEYFRAME_INTERVAL = 24
DELTA_MAX_CHANGES_RATIO = 0.9

# Colours as R, G, B, W
PURPLE = (160, 0, 255, 0)
YELLOW = (255, 220, 0, 0)


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix_px(px_a, px_b, t):
    return (
        clamp8(lerp(px_a[0], px_b[0], t)),
        clamp8(lerp(px_a[1], px_b[1], t)),
        clamp8(lerp(px_a[2], px_b[2], t)),
        clamp8(lerp(px_a[3], px_b[3], t)),
    )


def smoothstep01(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def build_frame(frame_index):
    """
    0s -> 5s:
        even pixels fade PURPLE -> YELLOW
        odd  pixels fade YELLOW -> PURPLE

    5s -> 10s:
        reverse back to the original arrangement

    Frame 0 and final frame match exactly for clean looping.
    """
    half_frames = TOTAL_FRAMES // 2

    if frame_index < half_frames:
        # Forward fade over first 5 seconds
        denom = max(1, half_frames - 1)
        t = smoothstep01(frame_index / denom)
    else:
        # Reverse fade over next 5 seconds
        denom = max(1, (TOTAL_FRAMES - half_frames) - 1)
        t = 1.0 - smoothstep01((frame_index - half_frames) / denom)

    frame = []
    for i in range(NUM_LEDS):
        if i % 2 == 0:
            # Even pixels: purple -> yellow -> purple
            frame.append(mix_px(PURPLE, YELLOW, t))
        else:
            # Odd pixels: yellow -> purple -> yellow
            frame.append(mix_px(YELLOW, PURPLE, t))

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
    first_frame = None
    last_frame = None
    keyframes = 0
    delta_frames = 0
    total_changes = 0

    for frame_index in range(TOTAL_FRAMES):
        frame = build_frame(frame_index)

        if frame_index == 0:
            first_frame = frame
        if frame_index == TOTAL_FRAMES - 1:
            last_frame = frame

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
print("First frame equals last frame:", first_frame == last_frame)