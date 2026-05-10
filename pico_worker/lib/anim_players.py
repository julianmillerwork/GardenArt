import array
import struct
import ws281xx_control

# =========================================================
# Raw BIN player
# Raw BIN is assumed to contain NUM_LEDS packed 32-bit RGBW
# words only.
# =========================================================
class RawBinPlayer:
    def __init__(self, filename, num_leds, frame_ms, PIXEL_ORDER):
        self.filename = filename
        self.num_leds = num_leds
        self.frame_bytes = num_leds * 4
        self.frame_ms = frame_ms
        self.PIXEL_ORDER=PIXEL_ORDER
        self.f = None

    def open(self):
        if self.f:
            self.f.close()
        self.f = open(self.filename, "rb")

    def close(self):
        if self.f:
            self.f.close()
            self.f = None

    def next_frame_into(self, frame_buf, PIXEL_ORDER):
        mv = memoryview(frame_buf)
        n = self.f.readinto(mv)
        if n == self.frame_bytes:
            return True

        self.f.seek(0)
        n = self.f.readinto(mv)
        if n == self.frame_bytes:
            return True

        raise RuntimeError("Raw BIN file read failed after rewind")


# =========================================================
# DLT player
# DLT stores NUM_LEDS pixels as R,G,B,W bytes.
# =========================================================
class DeltaPlayer:
    def __init__(self, filename, expected_leds,PIXEL_ORDER):
        self.filename = filename
        self.expected_leds = expected_leds
        self.f = None
        self.frame_ms = None
        self.led_count = None
        self.frame_count = None
        self.frames_read = 0
        self.PIXEL_ORDER=PIXEL_ORDER

    def open(self):
        if self.f:
            self.f.close()
        self.f = open(self.filename, "rb")
        self._read_header()

    def close(self):
        if self.f:
            self.f.close()
            self.f = None

    def _read_exact(self, n):
        data = self.f.read(n)
        if data is None or len(data) != n:
            raise RuntimeError("Unexpected EOF in DLT file")
        return data

    def _read_header(self):
        magic = self._read_exact(4)
        if magic != b"DLTA":
            raise RuntimeError("Not a valid DLT file")

        version = struct.unpack("<H", self._read_exact(2))[0]
        if version != 1:
            raise RuntimeError("Unsupported DLT version: {}".format(version))

        self.led_count = struct.unpack("<H", self._read_exact(2))[0]
        self.frame_count = struct.unpack("<H", self._read_exact(2))[0]
        fps = struct.unpack("<H", self._read_exact(2))[0]

        if self.led_count != self.expected_leds:
            raise RuntimeError(
                "DLT LED count {} does not match NUM_LEDS {}".format(
                    self.led_count, self.expected_leds
                )
            )

        if fps <= 0:
            raise RuntimeError("Invalid DLT FPS")

        self.frame_ms = max(1, 1000 // fps)
        self.frames_read = 0

    def _rewind(self):
        self.f.seek(0)
        self._read_header()

    def next_frame_into(self, frame_buf,PIXEL_ORDER):
        if self.frames_read >= self.frame_count:
            self._rewind()

        frame_type_b = self.f.read(1)
        if not frame_type_b or len(frame_type_b) != 1:
            self._rewind()
            frame_type_b = self._read_exact(1)

        frame_type = frame_type_b[0]

        if frame_type == 0x00:
            self._read_keyframe_into(frame_buf,PIXEL_ORDER)
        elif frame_type == 0x01:
            self._read_delta_into(frame_buf,PIXEL_ORDER)
        else:
            raise RuntimeError("Unknown DLT frame type: {}".format(frame_type))

        self.frames_read += 1
        return True

    def _read_keyframe_into(self, frame_buf, PIXEL_ORDER):
        raw = self._read_exact(self.led_count * 4)

        for i in range(self.led_count):
            base = i * 4
            r = raw[base + 0]
            g = raw[base + 1]
            b = raw[base + 2]
            w = raw[base + 3]
            frame_buf[i] = ws281xx_control.pack_for_strip(r, g, b, w, PIXEL_ORDER)

    def _read_delta_into(self, frame_buf,PIXEL_ORDER):
        num_changes = struct.unpack("<H", self._read_exact(2))[0]

        for _ in range(num_changes):
            index = struct.unpack("<H", self._read_exact(2))[0]
            if index >= self.led_count:
                raise RuntimeError("DLT delta pixel index out of range")

            px = self._read_exact(4)
            r = px[0]
            g = px[1]
            b = px[2]
            w = px[3]

            frame_buf[index] = ws281xx_control.pack_for_strip(r, g, b, w, PIXEL_ORDER)

