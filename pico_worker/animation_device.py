from p2p_protocol_spec import *
import ubinascii

try:
    import _thread
except ImportError:
    _thread = None


class _DummyLock:
    def acquire(self):
        return True

    def release(self):
        return None


def _make_lock():
    if _thread is None:
        return _DummyLock()
    return _thread.allocate_lock()


class AnimationDevice:
    """
    Thread-shared device state.

    UART thread:
      - Calls command handlers through p2p_protocol_dispatch.
      - Receives file-transfer chunks into RAM only.
      - Never opens, reads, writes, renames or removes files.

    Animation/main thread:
      - Owns flash access.
      - Reads animation files for playback.
      - Pulls completed RAM transfers and writes them to flash when it has time.
    """

    def __init__(self, num_leds=70, max_ram_transfer_bytes=MAX_RAM_TRANSFER_BYTES):
        self.num_leds = num_leds

        self.mode = MODE_IDLE
        self.state = STATE_IDLE
        self.brightness = 255
        self.error = ERR_NONE
        self.pixels = [(0, 0, 0, 0)] * num_leds

        self.play_requested = False
        self.stop_requested = False
        self.show_requested = False

        self.anim_id = 0
        self.loop = True
        self.fps = 30

        self.max_ram_transfer_bytes = max_ram_transfer_bytes

        # Optional callback assigned by the worker main module. It should return
        # a filename for a known animation ID, or None if the file is missing.
        self.animation_file_resolver = None

        self._transfer_lock = _make_lock()
        self._active_transfer = None
        self._ready_transfer = None

    # =====================================================
    # LED/static state
    # =====================================================
    def set_pixel(self, index, r, g, b, w=0):
        if index < 0 or index >= self.num_leds:
            raise ValueError("pixel out of range")
        self.pixels[index] = (r, g, b, w)

    def fill(self, r, g, b, w=0):
        self.pixels = [(r, g, b, w)] * self.num_leds

    def clear(self):
        self.fill(0, 0, 0, 0)

    def show(self):
        self.mode = MODE_STATIC
        self.state = STATE_IDLE
        self.play_requested = False
        self.stop_requested = False
        self.show_requested = True
        return True

    def has_animation(self, anim_id):
        if self.animation_file_resolver is None:
            return True
        return self.animation_file_resolver(anim_id) is not None

    def play(self, anim_id=0, loop=True, fps=30):
        self.anim_id = anim_id
        self.loop = bool(loop)
        self.fps = fps

        self.mode = MODE_ANIMATION
        self.state = STATE_PLAYING

        self.play_requested = True
        self.stop_requested = False
        self.show_requested = False
        return True

    def stop(self):
        self.mode = MODE_IDLE
        self.state = STATE_IDLE
        self.play_requested = False
        self.stop_requested = True
        self.show_requested = False
        return True

    def set_mode(self, mode):
        self.mode = mode

        if mode == MODE_IDLE:
            self.state = STATE_IDLE
            self.play_requested = False
            self.stop_requested = True
            self.show_requested = False

        elif mode == MODE_ANIMATION:
            self.state = STATE_IDLE
            self.stop_requested = False
            self.show_requested = False

        elif mode == MODE_STATIC:
            self.state = STATE_IDLE
            self.play_requested = False
            self.stop_requested = False
            self.show_requested = False

        return True

    def set_brightness(self, brightness):
        if brightness < 0:
            brightness = 0
        elif brightness > 255:
            brightness = 255

        self.brightness = brightness
        return True

    # =====================================================
    # UART file-transfer RAM staging
    # =====================================================
    def transfer_filename(self, transfer_id, transfer_type):
        if transfer_type == TRANSFER_TYPE_ANIMATION:
            return "anim_{:08x}.dlt".format(transfer_id & 0xFFFFFFFF)
        return "transfer_{:08x}.bin".format(transfer_id & 0xFFFFFFFF)

    def begin_transfer(self, transfer_id, transfer_type, total_size):
        if total_size <= 0:
            self.error = ERR_INVALID_ARG
            return ERR_INVALID_ARG, 0

        if total_size > self.max_ram_transfer_bytes:
            # This design intentionally stages the full file in RAM because flash
            # must only be touched by the animation/main thread.
            self.error = ERR_NO_MEMORY
            return ERR_NO_MEMORY, 0

        self._transfer_lock.acquire()
        try:
            if self._active_transfer is not None or self._ready_transfer is not None:
                self.error = ERR_BUSY
                return ERR_BUSY, 0

            try:
                buf = bytearray(total_size)
            except MemoryError:
                self.error = ERR_NO_MEMORY
                return ERR_NO_MEMORY, 0

            self._active_transfer = {
                "transfer_id": transfer_id,
                "transfer_type": transfer_type,
                "total_size": total_size,
                "buffer": buf,
                "bytes_received": 0,
                "next_chunk_index": 0,
                "filename": self.transfer_filename(transfer_id, transfer_type),
            }

            self.state = STATE_BUSY
            self.error = ERR_NONE
            return ERR_NONE, 0

        finally:
            self._transfer_lock.release()

    def receive_data_chunk(self, transfer_id, chunk_index, data):
        self._transfer_lock.acquire()
        try:
            t = self._active_transfer

            if t is None or t["transfer_id"] != transfer_id:
                self.error = ERR_NOT_READY
                return ERR_NOT_READY, 0

            expected = t["next_chunk_index"]
            if chunk_index != expected:
                self.error = ERR_BAD_SEQUENCE
                return ERR_BAD_SEQUENCE, expected

            offset = t["bytes_received"]
            end = offset + len(data)

            if end > t["total_size"]:
                self.error = ERR_OUT_OF_RANGE
                return ERR_OUT_OF_RANGE, expected

            t["buffer"][offset:end] = data
            t["bytes_received"] = end
            t["next_chunk_index"] = (expected + 1) & 0xFFFF

            return ERR_NONE, t["next_chunk_index"]

        finally:
            self._transfer_lock.release()

    def end_transfer(self, transfer_id, expected_crc32):
        self._transfer_lock.acquire()
        try:
            t = self._active_transfer

            if t is None or t["transfer_id"] != transfer_id:
                self.error = ERR_NOT_READY
                return ERR_NOT_READY, 0

            if t["bytes_received"] != t["total_size"]:
                self.error = ERR_TRANSFER_FAILED
                return ERR_TRANSFER_FAILED, t["next_chunk_index"]

            actual_crc32 = ubinascii.crc32(t["buffer"]) & 0xFFFFFFFF
            if actual_crc32 != expected_crc32:
                self._active_transfer = None
                self.state = STATE_ERROR
                self.error = ERR_BAD_CRC
                return ERR_BAD_CRC, t["next_chunk_index"]

            self._ready_transfer = {
                "transfer_id": t["transfer_id"],
                "transfer_type": t["transfer_type"],
                "total_size": t["total_size"],
                "buffer": t["buffer"],
                "crc32": actual_crc32,
                "filename": t["filename"],
            }

            self._active_transfer = None
            self.state = STATE_IDLE
            self.error = ERR_NONE
            return ERR_NONE, t["next_chunk_index"]

        finally:
            self._transfer_lock.release()

    def take_ready_transfer(self):
        """
        Called by the animation/main thread only.

        Returns a completed RAM-staged transfer, or None.
        Ownership of the large bytearray moves to the caller.
        """
        self._transfer_lock.acquire()
        try:
            t = self._ready_transfer
            self._ready_transfer = None
            return t
        finally:
            self._transfer_lock.release()

    def transfer_busy(self):
        self._transfer_lock.acquire()
        try:
            return self._active_transfer is not None or self._ready_transfer is not None
        finally:
            self._transfer_lock.release()
