import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 240
FPS = 30
OUTPUT = "disco_fade_rgbw_188.dlt"

# Delta settings
KEYFRAME_INTERVAL = 20
DELTA_MAX_CHANGES_RATIO = 0.85


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def fract(x):
    return x - math.floor(x)


def hash01(n):
    """
    Deterministic pseudo-random 0..1 value.
    """
    x = math.sin(n * 12.9898 + 78.233) * 43758.5453
    return fract(x)


def smoothstep(x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def colour_wheel(u):
    """
    RGB colour wheel.
    u is 0..1.
    """
    u = fract(u)

    if u < 1.0 / 6.0:
        x = u * 6.0
        return 255, clamp8(255 * x), 0

    if u < 2.0 / 6.0:
        x = (u - 1.0 / 6.0) * 6.0
        return clamp8(255 * (1.0 - x)), 255, 0

    if u < 3.0 / 6.0:
        x = (u - 2.0 / 6.0) * 6.0
        return 0, 255, clamp8(255 * x)

    if u < 4.0 / 6.0:
        x = (u - 3.0 / 6.0) * 6.0
        return 0, clamp8(255 * (1.0 - x)), 255

    if u < 5.0 / 6.0:
        x = (u - 4.0 / 6.0) * 6.0
        return clamp8(255 * x), 0, 255

    x = (u - 5.0 / 6.0) * 6.0
    return 255, 0, clamp8(255 * (1.0 - x))


def blend_rgb(a, b, t):
    ar, ag, ab = a
    br, bg, bb = b

    return (
        ar + (br - ar) * t,
        ag + (bg - ag) * t,
        ab + (bb - ab) * t,
    )


def slow_colour_fade(frame_index):
    """
    Slow global fade between strong disco colours.
    """
    # One major colour transition roughly every 2 seconds.
    phase = frame_index / 60.0

    colour_a_index = math.floor(phase)
    colour_b_index = colour_a_index + 1

    t = smoothstep(fract(phase))

    hue_a = fract(colour_a_index * 0.173)
    hue_b = fract(colour_b_index * 0.173)

    c_a = colour_wheel(hue_a)
    c_b = colour_wheel(hue_b)

    return blend_rgb(c_a, c_b, t)


def slow_breath(frame_index):
    """
    Smooth whole-animation brightness breathing.
    """
    u = frame_index / TOTAL_FRAMES
    return 0.55 + 0.35 * (0.5 + 0.5 * math.sin(2.0 * math.pi * u * 2.0))


def soft_wave_amount(p, frame_index):
    """
    Slow moving waves across the strip.
    """
    t = frame_index / FPS

    wave1 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 1.5 - t * 0.18))
    wave2 = 0.5 + 0.5 * math.sin(2.0 * math.pi * (p * 3.0 + t * 0.11 + 0.3))

    return 0.45 + 0.35 * wave1 + 0.20 * wave2


def rapid_section_amount(frame_index):
    """
    Enables short rapid sections, but not all the time.

    Returns 0..1.
    """
    cycle = frame_index % 120

    # Short energetic section between frames 72 and 100 of each 4s cycle.
    if 72 <= cycle <= 100:
        x = (cycle - 72) / 28.0

        # Fade in/out the rapid section.
        if x < 0.25:
            return smoothstep(x / 0.25)
        if x > 0.75:
            return smoothstep((1.0 - x) / 0.25)
        return 1.0

    return 0.0


def chase_amount(p, frame_index):
    """
    Fast moving highlight, only used during rapid sections.
    """
    x1 = fract(p * 5.0 - frame_index * 0.12)
    x2 = fract(p * 8.0 + frame_index * 0.16)

    pulse1 = max(0.0, 1.0 - abs(x1 - 0.5) * 9.0)
    pulse2 = max(0.0, 1.0 - abs(x2 - 0.5) * 11.0)

    return max(pulse1, pulse2 * 0.75)


def sparkle_amount(i, frame_index, rapid_amount):
    """
    Sparse sparkle, stronger during rapid sections.
    """
    threshold = 0.985 - rapid_amount * 0.045
    h = hash01(i * 97 + frame_index * 131)

    if h > threshold:
        return 1.0

    if h > threshold - 0.025:
        return 0.35

    return 0.0


def white_flash_amount(frame_index):
    """
    Big white flashes, but less often than the previous disco mode.
    """
    f = frame_index

    # Big flash every 2 seconds.
    if f % 60 == 0:
        return 1.0

    # One fade-down frame after the main flash.
    if f % 60 == 1:
        return 0.45

    # Occasional double-flash during rapid section.
    cycle = f % 120
    if cycle in (84, 90):
        return 0.8

    return 0.0


def local_white_sweep(p, frame_index):
    """
    Softer travelling white accent using the W channel.
    """
    t = frame_index / FPS

    centre = fract(t * 0.28)
    d = abs(p - centre)

    if d > 0.5:
        d = 1.0 - d

    width = 0.12

    if d >= width:
        return 0.0

    x = 1.0 - d / width
    return x * x * 0.65


def build_frame(frame_index):
    base_r, base_g, base_b = slow_colour_fade(frame_index)

    breath = slow_breath(frame_index)
    rapid = rapid_section_amount(frame_index)
    white_flash = white_flash_amount(frame_index)

    frame = []

    for i in range(NUM_LEDS):
        p = i / NUM_LEDS

        # Slow base colour variation across the strip.
        wave = soft_wave_amount(p, frame_index)

        # Subtle hue offset per position, but slow.
        hue_offset = 0.06 * math.sin(
            2.0 * math.pi * (p * 2.0 + frame_index / 180.0)
        )

        local_r, local_g, local_b = colour_wheel(
            fract(frame_index / 180.0 + p * 0.18 + hue_offset)
        )

        # Blend mostly from the slow global colour, with a bit of local colour.
        r = base_r * 0.72 + local_r * 0.28
        g = base_g * 0.72 + local_g * 0.28
        b = base_b * 0.72 + local_b * 0.28

        intensity = breath * wave

        # During rapid sections, add chase accents rather than changing everything.
        chase = chase_amount(p, frame_index) * rapid
        sparkle = sparkle_amount(i, frame_index, rapid)

        r *= intensity
        g *= intensity
        b *= intensity

        if chase > 0.0:
            chase_colour = colour_wheel(fract(frame_index * 0.045 + p * 0.9))
            cr, cg, cb = chase_colour

            r = max(r, cr * chase)
            g = max(g, cg * chase)
            b = max(b, cb * chase)

        # W channel is used for white sweep and sparkles.
        w = 0.0

        sweep = local_white_sweep(p, frame_index)
        if sweep > 0.0:
            w = max(w, 120 * sweep)

            # Also add a small RGB lift so the white sweep has body.
            r += 45 * sweep
            g += 45 * sweep
            b += 45 * sweep

        if sparkle > 0.0:
            # Coloured sparkle plus W sparkle.
            sparkle_hue = hash01(i * 17 + frame_index * 23)
            sr, sg, sb = colour_wheel(sparkle_hue)

            r = max(r, sr * sparkle)
            g = max(g, sg * sparkle)
            b = max(b, sb * sparkle)

            w = max(w, 90 + 130 * sparkle)

        # Big white flash overrides most of the frame.
        if white_flash > 0.0:
            # Keep a little colour underneath.
            colour_keep = 0.20

            r = r * colour_keep + 255 * white_flash
            g = g * colour_keep + 255 * white_flash
            b = b * colour_keep + 255 * white_flash
            w = max(w, 255 * white_flash)

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
            frame_index % KEYFRAME_INTERVAL == 0
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
                written_changes = write_delta(f, prev_frame, frame)
                delta_frames += 1
                total_changes += written_changes

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