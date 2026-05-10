import array
import gc
import os
import time
import ubinascii

from machine import Pin
from time import ticks_ms, ticks_diff, sleep_ms

import ws281xx_control
import anim_players

from p2p_protocol_codec import PacketParser
from p2p_protocol_dispatch import ProtocolContext, dispatch_packet
from p2p_protocol_spec import *
from animation_device import AnimationDevice

from p2p_custom_uart_wrapper import (
    uart_send_bytes,
    uart_read_byte_nonblocking,
    uart_flush,
)


# =========================================================
# Configuration
# =========================================================
PIXEL_ORDER = "WRGB"

PIN_NUM = 3
STATE_MACHINE = 4
RGBW_MODE = True

NUM_LEDS = 188

# Built-in/default files. Transferred animation files are saved as
# anim_<8_hex_digit_content_id>.dlt. The default file is registered at boot
# using the same CRC32 content ID that the master calculates.
DEFAULT_ANIM_FILE = "aurora_70_grb32_188.dlt"
ANIM_FILES = {}

FPS = 30
FRAME_MS = 1000 // FPS
FRAME_WORDS = NUM_LEDS

# Cooperative UART budgets.
# Keep these modest while writing directly to flash.
UART_BYTES_AT_FRAME_START = 64
UART_BYTES_DURING_SPARE_TIME = 32
UART_SPARE_SERVICE_SLEEP_MS = 1

DEBUG_UART = False
DEBUG_RAW_BYTES = False
DEBUG_TRANSFER = False
DEBUG_ZERO_FRAMES = True


# =========================================================
# LED strip setup
# =========================================================
strip = ws281xx_control.FastWS281x(
    PIN_NUM,
    NUM_LEDS,
    rgbw=RGBW_MODE,
    sm_id=STATE_MACHINE,
    freq=8_000_000,
)


# =========================================================
# Helper functions
# =========================================================
def transfer_filename(transfer_id, transfer_type):
    if transfer_type == TRANSFER_TYPE_ANIMATION:
        return "anim_{:08x}.dlt".format(transfer_id & 0xFFFFFFFF)

    return "transfer_{:08x}.bin".format(transfer_id & 0xFFFFFFFF)


def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


def file_crc32(filename, block_size=512):
    crc = 0
    with open(filename, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            crc = ubinascii.crc32(block, crc) & 0xFFFFFFFF
    return crc & 0xFFFFFFFF


def register_builtin_animation_files():
    if file_exists(DEFAULT_ANIM_FILE):
        try:
            anim_id = file_crc32(DEFAULT_ANIM_FILE)
            ANIM_FILES[anim_id] = DEFAULT_ANIM_FILE
            print(
                "Registered built-in animation id={:08x} file={}".format(
                    anim_id,
                    DEFAULT_ANIM_FILE,
                )
            )
        except Exception as e:
            print("Could not register built-in animation:", repr(e))


def get_free_flash_bytes():
    """
    Returns approximate free bytes on the current filesystem, or None if statvfs
    is unavailable.
    """
    try:
        stat = os.statvfs(".")
        return stat[0] * stat[3]
    except Exception:
        return None


# =========================================================
# Shared state forward declarations
# =========================================================
animation_enabled = False
current_player = None
current_player_filename = None
current_anim_id = None


# =========================================================
# LED diagnostics
# =========================================================
def is_zero_buf(buf):
    for px in buf:
        if px != 0:
            return False
    return True


def show_leds(buf, reason):
    if DEBUG_ZERO_FRAMES and is_zero_buf(buf):
        print("!!! ZERO LED FRAME SENT:", reason)
        try:
            print(
                "state:",
                device.state,
                "mode:",
                device.mode,
                "animation_enabled:",
                animation_enabled,
                "stop_requested:",
                device.stop_requested,
                "show_requested:",
                device.show_requested,
                "play_requested:",
                device.play_requested,
                "transfer_active:",
                transfer_manager.active,
                "current_file:",
                current_player_filename,
            )
        except Exception as e:
            print("zero-frame diagnostic failed:", repr(e))

    strip.show_buf(buf)


# =========================================================
# Animation file/player handling
# =========================================================
def resolve_animation_file(anim_id):
    transferred = "anim_{:08x}.dlt".format(anim_id & 0xFFFFFFFF)
    if file_exists(transferred):
        return transferred

    fallback = ANIM_FILES.get(anim_id & 0xFFFFFFFF)
    if fallback and file_exists(fallback):
        return fallback

    return None


def make_player(filename, num_leds, default_frame_ms):
    with open(filename, "rb") as probe:
        magic = probe.read(4)

    if magic == b"DLTA":
        player = anim_players.DeltaPlayer(filename, num_leds, PIXEL_ORDER)
        player.open()
        print("Detected DLT animation:", filename)
        print("DLT uses PIXEL_ORDER =", PIXEL_ORDER)
        print("DLT LED count =", num_leds)
        print("DLT frame time (ms):", player.frame_ms)
        return player

    player = anim_players.RawBinPlayer(
        filename,
        num_leds,
        default_frame_ms,
        PIXEL_ORDER,
    )
    player.open()
    print("Detected raw BIN animation:", filename)
    print("BIN is assumed pre-packed for", num_leds, "RGBW pixels")
    print("BIN frame time (ms):", default_frame_ms)
    return player


def close_current_player():
    global current_player, current_player_filename, current_anim_id

    if current_player is not None:
        try:
            current_player.close()
        except Exception as e:
            print("player close error:", repr(e))

    current_player = None
    current_player_filename = None
    current_anim_id = None


def stop_animation_for_flash_write(filename):
    """
    Only stop playback if the file being replaced is currently open.

    Important:
    This does not clear the LEDs. WS281x LEDs should keep their last latched
    frame while playback is stopped.
    """
    global animation_enabled

    if current_player_filename == filename:
        print("Stopping current animation before replacing:", filename)
        animation_enabled = False
        device.state = STATE_IDLE
        close_current_player()


def open_player_for_anim(anim_id, fps):
    global current_player, current_player_filename, current_anim_id

    filename = resolve_animation_file(anim_id)
    if filename is None:
        print("No animation file for anim_id", anim_id)
        device.error = ERR_INVALID_ARG
        return None

    if (
        current_player is not None
        and current_anim_id == anim_id
        and current_player_filename == filename
    ):
        return current_player

    close_current_player()

    try:
        p = make_player(filename, NUM_LEDS, 1000 // fps if fps else FRAME_MS)
        current_player = p
        current_player_filename = filename
        current_anim_id = anim_id
        device.error = ERR_NONE
        return p
    except Exception as e:
        print("open player failed:", repr(e))
        device.error = ERR_INVALID_ARG
        close_current_player()
        return None


# =========================================================
# Transfer manager: direct-to-flash receive
# =========================================================
class StreamingFlashTransferManager:
    """
    Receives UART file transfers directly into flash.

    This replaces the old RAM-staging design:

        old: UART -> RAM bytearray(total_size) -> flash
        new: UART -> anim_<id>.dlt.tmp -> rename after CRC passes

    Advantages:
    - Does not allocate the whole file in RAM.
    - Allows files much larger than available Pico RAM.
    - Existing animation remains untouched until the new file is fully received
      and CRC-verified.
    """

    def __init__(self):
        self.active = False

        self.transfer_id = None
        self.transfer_type = None
        self.total_size = 0

        self.final_filename = None
        self.tmp_filename = None
        self.fp = None

        self.write_offset = 0
        self.expected_chunk_index = 0

        self.expected_crc = None
        self.calculated_crc = None
        self.rolling_crc = 0

        self.error = ERR_NONE

    def begin(self, transfer_id, transfer_type, total_size):
        if self.active:
            self.error = ERR_BUSY
            return False

        if total_size <= 0:
            self.error = ERR_INVALID_ARG
            return False

        self.final_filename = transfer_filename(transfer_id, transfer_type)
        self.tmp_filename = self.final_filename + ".tmp"

        free_bytes = get_free_flash_bytes()
        if free_bytes is not None:
            # Leave a small safety margin. Filesystems often need some spare space.
            safety_margin = 4096
            if total_size + safety_margin > free_bytes:
                print(
                    "Not enough flash for transfer. need={} free={} margin={}".format(
                        total_size,
                        free_bytes,
                        safety_margin,
                    )
                )
                self.error = ERR_NO_MEMORY
                return False

        try:
            os.remove(self.tmp_filename)
        except OSError:
            pass

        try:
            self.fp = open(self.tmp_filename, "wb")
        except OSError as e:
            print("Could not open temp transfer file:", repr(e))
            self.error = ERR_TRANSFER_FAILED
            self.fp = None
            return False

        self.active = True

        self.transfer_id = transfer_id
        self.transfer_type = transfer_type
        self.total_size = total_size

        self.write_offset = 0
        self.expected_chunk_index = 0

        self.expected_crc = None
        self.calculated_crc = None
        self.rolling_crc = 0

        self.error = ERR_NONE

        print(
            "Flash streaming transfer started id={} size={} tmp={}".format(
                transfer_id,
                total_size,
                self.tmp_filename,
            )
        )

        return True

    def add_chunk(self, transfer_id, chunk_index, data):
        if not self.active:
            self.error = ERR_NOT_READY
            return TRANSFER_ABORTED

        if transfer_id != self.transfer_id:
            self.error = ERR_INVALID_ARG
            return TRANSFER_ABORTED

        # Duplicate chunk. This usually means the worker accepted the chunk,
        # but the master did not receive the ACK/response and resent it.
        # Do not write it again.
        if chunk_index < self.expected_chunk_index:
            if DEBUG_TRANSFER:
                print(
                    "DATA_CHUNK duplicate id={} chunk={} expected_next={}".format(
                        transfer_id,
                        chunk_index,
                        self.expected_chunk_index,
                    )
                )
            self.error = ERR_NONE
            return TRANSFER_IN_PROGRESS

        # Future chunk before expected chunk. The worker has missed data.
        if chunk_index > self.expected_chunk_index:
            print(
                "DATA_CHUNK out of order id={} got={} expected={}".format(
                    transfer_id,
                    chunk_index,
                    self.expected_chunk_index,
                )
            )
            self.error = ERR_INVALID_ARG
            return TRANSFER_NEED_RETRY

        end_offset = self.write_offset + len(data)

        if end_offset > self.total_size:
            self.error = ERR_OUT_OF_RANGE
            return TRANSFER_ABORTED

        try:
            self.fp.write(data)
        except OSError as e:
            print("Transfer file write failed:", repr(e))
            self.error = ERR_TRANSFER_FAILED
            self.abort()
            return TRANSFER_ABORTED

        self.write_offset = end_offset
        self.expected_chunk_index += 1

        # Incremental CRC avoids one big crc32 over a large file.
        self.rolling_crc = ubinascii.crc32(data, self.rolling_crc) & 0xFFFFFFFF

        self.error = ERR_NONE
        return TRANSFER_IN_PROGRESS

    def end(self, transfer_id, expected_crc):
        if not self.active:
            self.error = ERR_NOT_READY
            return TRANSFER_ABORTED

        if transfer_id != self.transfer_id:
            self.error = ERR_INVALID_ARG
            return TRANSFER_ABORTED

        if self.write_offset != self.total_size:
            self.error = ERR_TRANSFER_FAILED
            print(
                "Transfer incomplete: got {} of {}".format(
                    self.write_offset,
                    self.total_size,
                )
            )
            self.abort()
            return TRANSFER_ABORTED

        self.expected_crc = expected_crc
        self.calculated_crc = self.rolling_crc & 0xFFFFFFFF

        if self.calculated_crc != self.expected_crc:
            self.error = ERR_BAD_CHECKSUM
            print(
                "Transfer CRC mismatch expected={:08x} got={:08x}".format(
                    self.expected_crc,
                    self.calculated_crc,
                )
            )
            self.abort()
            return TRANSFER_BAD_CRC

        try:
            self.fp.flush()
            self.fp.close()
            self.fp = None
        except Exception as e:
            print("Transfer file close failed:", repr(e))
            self.error = ERR_TRANSFER_FAILED
            self.abort()
            return TRANSFER_ABORTED

        # Only after successful CRC do we replace the final file.
        # If this is the currently playing file, close the player first.
        stop_animation_for_flash_write(self.final_filename)

        try:
            os.remove(self.final_filename)
        except OSError:
            pass

        try:
            os.rename(self.tmp_filename, self.final_filename)
        except OSError as e:
            print("Transfer rename failed:", repr(e))
            self.error = ERR_TRANSFER_FAILED
            self.abort()
            return TRANSFER_ABORTED

        print(
            "Flash streaming transfer complete id={} size={} crc={:08x} file={}".format(
                self.transfer_id,
                self.total_size,
                self.calculated_crc,
                self.final_filename,
            )
        )

        self._reset_state()
        gc.collect()
        return TRANSFER_OK

    def abort(self):
        try:
            if self.fp is not None:
                self.fp.close()
        except Exception:
            pass

        try:
            if self.tmp_filename:
                os.remove(self.tmp_filename)
        except Exception:
            pass

        self._reset_state()
        gc.collect()

    def _reset_state(self):
        self.active = False

        self.transfer_id = None
        self.transfer_type = None
        self.total_size = 0

        self.final_filename = None
        self.tmp_filename = None
        self.fp = None

        self.write_offset = 0
        self.expected_chunk_index = 0

        self.expected_crc = None
        self.calculated_crc = None
        self.rolling_crc = 0

        self.error = ERR_NONE

    def transfer_busy(self):
        return self.active


# =========================================================
# Shared device/protocol setup
# =========================================================
led = Pin("LED", Pin.OUT)
led.on()

register_builtin_animation_files()

device = AnimationDevice(NUM_LEDS)
device.animation_file_resolver = resolve_animation_file
transfer_manager = StreamingFlashTransferManager()
ctx = ProtocolContext(device, transfer_manager)
parser = PacketParser()

last_uart_error = None


# =========================================================
# Cooperative UART servicing
# =========================================================
def tx_bytes(data):
    uart_send_bytes(data)
    uart_flush()


def describe_packet(pkt):
    print("---- UART PACKET ----")
    print("ok:", pkt.get("ok"))
    print("cmd:", pkt.get("cmd"), pkt.get("cmd_name"))
    print("seq:", pkt.get("seq"))
    print("payload len:", len(pkt.get("payload", b"")))
    print("---------------------")


def service_uart(max_bytes):
    """
    Cooperatively service up to max_bytes from UART.

    The animation loop decides when and how much UART work is allowed.
    This prevents transfer parsing and flash writes from completely starving
    rendering.
    """
    global last_uart_error

    count = 0

    while count < max_bytes:
        b = uart_read_byte_nonblocking()

        if b is None:
            break

        count += 1

        if DEBUG_RAW_BYTES:
            print("UART RX byte:", hex(b))

        pkt = parser.feed(b)

        if pkt is None:
            continue

        if DEBUG_UART:
            describe_packet(pkt)

        if not pkt["ok"]:
            if DEBUG_UART:
                print("UART packet rejected:", pkt)
            continue

        try:
            if DEBUG_UART:
                print(
                    "UART CMD before dispatch:",
                    pkt.get("cmd"),
                    pkt.get("cmd_name"),
                    "seq=",
                    pkt.get("seq"),
                    "payload_len=",
                    len(pkt.get("payload", b"")),
                )

            response = dispatch_packet(ctx, pkt)

            if DEBUG_UART:
                print(
                    "UART CMD after dispatch:",
                    pkt.get("cmd"),
                    pkt.get("cmd_name"),
                    "stop_requested=",
                    device.stop_requested,
                    "show_requested=",
                    device.show_requested,
                    "play_requested=",
                    device.play_requested,
                    "state=",
                    device.state,
                    "mode=",
                    device.mode,
                )

        except Exception as e:
            last_uart_error = repr(e)
            print("DISPATCH ERROR:", last_uart_error)
            response = None

        if response is not None:
            tx_bytes(response)

    return count


# =========================================================
# Static pixel rendering and brightness control
# =========================================================
def apply_brightness_to_buf(src_buf, dst_buf, brightness):
    if brightness >= 255:
        return src_buf

    if brightness <= 0:
        for i in range(len(src_buf)):
            dst_buf[i] = 0
        return dst_buf

    for i, px in enumerate(src_buf):
        w = (px >> 24) & 0xFF
        r = (px >> 16) & 0xFF
        g = (px >> 8) & 0xFF
        b = px & 0xFF

        w = (w * brightness) >> 8
        r = (r * brightness) >> 8
        g = (g * brightness) >> 8
        b = (b * brightness) >> 8

        dst_buf[i] = (w << 24) | (r << 16) | (g << 8) | b

    return dst_buf


def render_static_pixels(source_buf, output_buf):
    for i, px in enumerate(device.pixels):
        r, g, b, w = px
        source_buf[i] = (w << 24) | (r << 16) | (g << 8) | b

    display_buf = apply_brightness_to_buf(
        source_buf,
        output_buf,
        device.brightness,
    )

    show_leds(display_buf, "render_static_pixels/show_requested")


# =========================================================
# Device request handling
# =========================================================
def handle_device_requests(frame_buf, output_buf, off_buf):
    global animation_enabled

    if device.stop_requested:
        # Important:
        # Do not blank LEDs here. Stop means stop playback, not clear display.
        print("Stop requested: stopping animation but leaving LEDs latched")
        device.stop_requested = False
        animation_enabled = False
        device.state = STATE_IDLE
        close_current_player()

    if device.show_requested:
        render_static_pixels(frame_buf, output_buf)
        device.show_requested = False
        device.stop_requested = False
        animation_enabled = False
        device.state = STATE_IDLE
        close_current_player()

    if device.play_requested:
        device.play_requested = False

        # If a file transfer is in progress, do not open the animation yet.
        # This is especially important if the requested animation is the one
        # currently being received.
        if transfer_manager.transfer_busy():
            device.play_requested = True
            return

        p = open_player_for_anim(device.anim_id, device.fps)
        if p is not None:
            animation_enabled = True
            device.mode = MODE_ANIMATION
            device.state = STATE_PLAYING
        else:
            animation_enabled = False
            device.state = STATE_ERROR


# =========================================================
# Playback loop with cooperative scheduling
# =========================================================
def play_loop(pixel_order):
    global animation_enabled

    frame_buf = array.array("I", [0] * FRAME_WORDS)
    output_buf = array.array("I", [0] * FRAME_WORDS)
    off_buf = array.array("I", [0] * FRAME_WORDS)

    stats_interval_ms = 3000
    stats_start = ticks_ms()
    stats_frames = 0
    stats_total_frame_ms = 0
    stats_worst_frame_ms = 0
    stats_uart_bytes = 0

    animation_enabled = False

    try:
        while True:
            frame_start = ticks_ms()

            # 1. Bounded UART work at the start of the frame.
            stats_uart_bytes += service_uart(UART_BYTES_AT_FRAME_START)

            # 2. Apply commands received from UART.
            handle_device_requests(frame_buf, output_buf, off_buf)

            # 3. Render exactly one animation frame when enabled.
            #
            # Direct-to-flash transfer can happen while animation is playing.
            # If the transferred file is the same as the current file, the player
            # is only stopped at final rename time after CRC passes.
            if animation_enabled and current_player is not None:
                try:
                    current_player.next_frame_into(frame_buf, pixel_order)

                    # A command may have arrived inside the previous service_uart()
                    # window, so allow it to take effect before showing.
                    handle_device_requests(frame_buf, output_buf, off_buf)

                    if animation_enabled:
                        display_buf = apply_brightness_to_buf(
                            frame_buf,
                            output_buf,
                            device.brightness,
                        )
                        show_leds(display_buf, "animation frame")

                except Exception as e:
                    print("animation frame error:", repr(e))
                    device.error = ERR_TRANSFER_FAILED
                    device.state = STATE_ERROR
                    animation_enabled = False
                    close_current_player()

            target_frame_ms = FRAME_MS
            if current_player is not None:
                target_frame_ms = current_player.frame_ms

            elapsed = ticks_diff(ticks_ms(), frame_start)

            stats_frames += 1
            stats_total_frame_ms += elapsed
            if elapsed > stats_worst_frame_ms:
                stats_worst_frame_ms = elapsed

            # 4. Spend spare time on bounded UART service.
            #
            # Note: DATA_CHUNK dispatch now writes directly to flash, so this
            # spare-time UART servicing may include small flash writes.
            # Keep master chunk size modest if animation stutters.
            remaining = target_frame_ms - elapsed

            while remaining > 0:
                stats_uart_bytes += service_uart(UART_BYTES_DURING_SPARE_TIME)

                elapsed_now = ticks_diff(ticks_ms(), frame_start)
                remaining = target_frame_ms - elapsed_now

                if remaining <= 0:
                    break

                nap = UART_SPARE_SERVICE_SLEEP_MS
                if remaining < nap:
                    nap = remaining

                sleep_ms(nap)

            now = ticks_ms()
            stats_elapsed_ms = ticks_diff(now, stats_start)

            if stats_elapsed_ms >= stats_interval_ms:
                achieved_fps = (stats_frames * 1000.0) / stats_elapsed_ms
                avg_frame_ms = (
                    stats_total_frame_ms / stats_frames
                    if stats_frames
                    else 0
                )

                if last_uart_error:
                    uart_state = last_uart_error
                else:
                    uart_state = "ok"

                print(
                    "FPS {:.2f} | avg frame {:.2f} ms | worst frame {} ms | target {} ms | uart bytes {} | state {} | transfer_active {} | uart {}".format(
                        achieved_fps,
                        avg_frame_ms,
                        stats_worst_frame_ms,
                        target_frame_ms,
                        stats_uart_bytes,
                        device.state,
                        transfer_manager.active,
                        uart_state,
                    )
                )

                stats_start = now
                stats_frames = 0
                stats_total_frame_ms = 0
                stats_worst_frame_ms = 0
                stats_uart_bytes = 0

    finally:
        close_current_player()


# =========================================================
# Start
# =========================================================
print("Starting cooperative worker loop")
play_loop(PIXEL_ORDER)