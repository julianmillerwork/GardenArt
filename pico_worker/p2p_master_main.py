import math
import time
from machine import Pin

from p2p_protocol_spec import (
    ERR_FILE_MISSING,
    MODE_ANIMATION,
    MODE_STATIC,
    TRANSFER_TYPE_ANIMATION,
)
from p2p_master_controller import ProtocolMaster, ProtocolError, ProtocolTimeout


led = Pin("LED", Pin.OUT)
led.on()

master = ProtocolMaster()


def pause(ms):
    time.sleep_ms(ms)


def wait_for_device(max_wait_ms=10000, retry_ms=500):
    print("Waiting for worker Pico...")

    start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), start) < max_wait_ms:
        try:
            pong = master.ping(b"Howdy", timeout_ms=1000)
            print("PONG:", pong)
            return True
        except Exception as e:
            print("Ping failed:", e)
            pause(retry_ms)

    print("Worker Pico did not respond within timeout")
    return False


def animation_id_for_file(filename):
    """
    Return the 4-byte content-derived animation ID for filename.

    This uses CRC32 because MicroPython provides it cheaply via ubinascii. It is
    also the CRC checked at END_TRANSFER, so the worker stores the file using the
    same content-derived ID it has already validated.
    """
    return master.animation_id_for_file(filename)


def play_animation_by_id(anim_id, loop=1, fps=30, timeout_ms=1000):
    """
    Ask the worker to play an animation that should already exist on flash.

    Returns True if the worker accepted the play request.
    Raises ProtocolError with ERR_FILE_MISSING if the worker needs the file.
    """
    print("Play animation id={:08x}".format(anim_id & 0xFFFFFFFF))
    master.set_brightness(255)
    master.set_mode(MODE_ANIMATION)
    pause(100)
    return master.play(anim_id=anim_id, loop=loop, fps=fps, timeout_ms=timeout_ms)


def play_animation_file(
    filename,
    loop=1,
    fps=30,
    chunk_size=249,
    progress=True,
    progress_every=10,
    inter_chunk_delay_ms=1,
    retry_delay_ms=300,
    max_chunk_retries=50,
):
    """
    Play an animation using a 32-bit content ID.

    Flow:
      1. Master calculates anim_id = CRC32(file contents).
      2. Master asks the worker to play that anim_id.
      3. If the worker already has anim_<anim_id>.dlt, it plays immediately.
      4. If the worker replies ERR_FILE_MISSING, master streams the file using
         the same anim_id as transfer_id.
      5. Master asks the worker to play that anim_id again.
    """
    anim_id = animation_id_for_file(filename)
    print("Animation file {} has id {:08x}".format(filename, anim_id))

    try:
        play_animation_by_id(anim_id, loop=loop, fps=fps)
        print("Worker already had animation {:08x}".format(anim_id))
        return anim_id

    except ProtocolError as e:
        if e.error_code != ERR_FILE_MISSING:
            raise

        print("Worker needs animation {:08x}; streaming file...".format(anim_id))

    master.send_file(
        filename,
        transfer_id=anim_id,
        transfer_type=TRANSFER_TYPE_ANIMATION,
        chunk_size=chunk_size,
        progress=progress,
        progress_every=progress_every,
        inter_chunk_delay_ms=inter_chunk_delay_ms,
        retry_delay_ms=retry_delay_ms,
        max_chunk_retries=max_chunk_retries,
    )

    # With the current worker implementation the rename happens before the final
    # TRANSFER_OK response is sent, so this does not need a long settling delay.
    pause(100)

    play_animation_by_id(anim_id, loop=loop, fps=fps)
    print("Streaming complete; playing animation {:08x}".format(anim_id))
    return anim_id


def brightness_ramp_sine(start, end, duration_ms=3000, steps=120, show=False):
    for i in range(steps + 1):
        t = i / steps
        eased = 0.5 - 0.5 * math.cos(t * math.pi)
        brightness = int(start + (end - start) * eased)
        master.set_brightness(brightness)
        pause(duration_ms // steps)
        if show:
            master.show()


try:
    if not wait_for_device():
        raise ProtocolTimeout("No response from worker Pico")

    print("STATUS:", master.get_status())

    # Change this filename to the animation file stored on the master Pico.
    TRANSFER_FILE = "aurora_70_grb32_188.dlt"

    anim_id = play_animation_file(
        TRANSFER_FILE,
        loop=1,
        fps=30,
        chunk_size=249,
        progress=True,
        progress_every=10,
        inter_chunk_delay_ms=1,
        retry_delay_ms=300,
        max_chunk_retries=50,
    )

    pause(10000)
    print("Final animation id: {:08x}".format(anim_id))
    print("Final status:", master.get_status())

except ProtocolTimeout as e:
    print("Timeout:", e)

except ProtocolError as e:
    print("Protocol error:", e)
    if e.error_code is not None:
        print("Error code:", e.error_code)
    if e.response is not None:
        print("Response:", e.response)

except Exception as e:
    print("Unexpected error:", repr(e))
