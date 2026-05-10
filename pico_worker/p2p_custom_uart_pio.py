# p2p_custom_uart_pio.py

import rp2
from machine import Pin
import time


# =========================================================
# PIO UART TX
# =========================================================
@rp2.asm_pio(
    out_init=rp2.PIO.OUT_HIGH,
    sideset_init=rp2.PIO.OUT_HIGH,
    out_shiftdir=rp2.PIO.SHIFT_RIGHT,
    autopull=False,
)
def pio_uart_tx():
    pull(block)
    set(x, 7)         .side(0) [7]   # start bit

    label("bitloop")
    out(pins, 1)
    jmp(x_dec, "bitloop")       [6]

    nop()              .side(1) [7]  # stop bit


# =========================================================
# PIO UART RX
# =========================================================
@rp2.asm_pio(
    in_shiftdir=rp2.PIO.SHIFT_RIGHT,
    autopush=True,
    push_thresh=8,
    fifo_join=rp2.PIO.JOIN_RX,
)
def pio_uart_rx():
    # Wait for start bit falling low
    wait(0, pin, 0)

    # Move to middle of first data bit.
    # At 8x baud, 1.5 bit times = 12 cycles.
    set(x, 7)              [10]

    label("bitloop")
    in_(pins, 1)
    jmp(x_dec, "bitloop")  [6]

    # IMPORTANT:
    # Wait for stop bit / idle high before looking for another start bit.
    wait(1, pin, 0)


# =========================================================
# Driver class
# =========================================================
class CustomUARTPIO:
    def __init__(
        self,
        tx_pin,
        rx_pin,
        baudrate=115200,
        tx_sm_id=0,
        rx_sm_id=1,
        rx_buf_size=1024,

        # Optional flow control
        # rts_pin: output from this Pico, high = I am ready to receive
        # cts_pin: input to this Pico, high = other side is ready
        rts_pin=None,
        cts_pin=None,

        # RX buffer watermarks for RTS
        rts_high_watermark=None,
        rts_low_watermark=None,

        # TX pacing
        default_chunk_size=32,
        default_inter_chunk_us=1000,
        cts_timeout_ms=1000,
    ):
        if rx_buf_size < 32:
            raise ValueError("rx_buf_size too small")

        self.baudrate = int(baudrate)
        self.sm_freq = self.baudrate * 8

        self.tx_pin = tx_pin if isinstance(tx_pin, Pin) else Pin(tx_pin, Pin.OUT, value=1)
        self.rx_pin = rx_pin if isinstance(rx_pin, Pin) else Pin(rx_pin, Pin.IN, Pin.PULL_UP)

        self.tx_sm_id = tx_sm_id
        self.rx_sm_id = rx_sm_id

        self.default_chunk_size = default_chunk_size
        self.default_inter_chunk_us = default_inter_chunk_us
        self.cts_timeout_ms = cts_timeout_ms

        # -------------------------------------------------
        # Optional flow-control pins
        # -------------------------------------------------
        self.rts_pin = None
        self.cts_pin = None

        if rts_pin is not None:
            self.rts_pin = rts_pin if isinstance(rts_pin, Pin) else Pin(rts_pin, Pin.OUT)
            self.rts_pin.value(1)  # ready

        if cts_pin is not None:
            self.cts_pin = cts_pin if isinstance(cts_pin, Pin) else Pin(cts_pin, Pin.IN, Pin.PULL_DOWN)

        # -------------------------------------------------
        # Software RX ring buffer
        # -------------------------------------------------
        self._rx_buf = bytearray(rx_buf_size)
        self._rx_buf_size = rx_buf_size
        self._rx_head = 0
        self._rx_tail = 0
        self.rx_overflow_count = 0

        if rts_high_watermark is None:
            rts_high_watermark = int(rx_buf_size * 0.75)

        if rts_low_watermark is None:
            rts_low_watermark = int(rx_buf_size * 0.40)

        self.rts_high_watermark = rts_high_watermark
        self.rts_low_watermark = rts_low_watermark
        self._rx_ready = True

        # -------------------------------------------------
        # TX state machine
        # -------------------------------------------------
        self.sm_tx = rp2.StateMachine(
            self.tx_sm_id,
            pio_uart_tx,
            freq=self.sm_freq,
            out_base=self.tx_pin,
            sideset_base=self.tx_pin,
        )

        # -------------------------------------------------
        # RX state machine
        # -------------------------------------------------
        self.sm_rx = rp2.StateMachine(
            self.rx_sm_id,
            pio_uart_rx,
            freq=self.sm_freq,
            in_base=self.rx_pin,
            jmp_pin=self.rx_pin,
        )

        self.active(True)

    # =====================================================
    # Control
    # =====================================================
    def active(self, enable=None):
        if enable is None:
            return None

        en = 1 if enable else 0
        self.sm_tx.active(en)
        self.sm_rx.active(en)

    def deinit(self):
        self.active(False)
        if self.rts_pin is not None:
            self.rts_pin.value(0)

    # =====================================================
    # RX buffer helpers
    # =====================================================
    def _rx_count(self):
        if self._rx_head >= self._rx_tail:
            return self._rx_head - self._rx_tail
        return self._rx_buf_size - (self._rx_tail - self._rx_head)

    def _rx_free(self):
        return self._rx_buf_size - 1 - self._rx_count()

    def _update_rts(self):
        if self.rts_pin is None:
            return

        used = self._rx_count()

        if self._rx_ready and used >= self.rts_high_watermark:
            self._rx_ready = False
            self.rts_pin.value(0)  # not ready

        elif not self._rx_ready and used <= self.rts_low_watermark:
            self._rx_ready = True
            self.rts_pin.value(1)  # ready

    def _rx_buf_put(self, b):
        next_head = (self._rx_head + 1) % self._rx_buf_size

        if next_head == self._rx_tail:
            self.rx_overflow_count += 1
            self._update_rts()
            return False

        self._rx_buf[self._rx_head] = b & 0xFF
        self._rx_head = next_head
        self._update_rts()
        return True

    def _rx_buf_get(self):
        if self._rx_head == self._rx_tail:
            self._update_rts()
            return None

        b = self._rx_buf[self._rx_tail]
        self._rx_tail = (self._rx_tail + 1) % self._rx_buf_size
        self._update_rts()
        return b

    # =====================================================
    # RX FIFO helpers
    # =====================================================
    @staticmethod
    def _extract_rx_byte(word):
        return (word >> 24) & 0xFF

    def poll_rx_fifo(self, max_bytes=None):
        count = 0

        try:
            while self.sm_rx.rx_fifo():
                word = self.sm_rx.get()
                self._rx_buf_put(self._extract_rx_byte(word))

                count += 1
                if max_bytes is not None and count >= max_bytes:
                    break

        except AttributeError:
            try:
                word = self.sm_rx.get()
                self._rx_buf_put(self._extract_rx_byte(word))
                count = 1
            except Exception:
                pass

        self._update_rts()
        return count

    # =====================================================
    # Flow control
    # =====================================================
    def _wait_cts(self, timeout_ms=None):
        if self.cts_pin is None:
            return True

        if timeout_ms is None:
            timeout_ms = self.cts_timeout_ms

        start = time.ticks_ms()

        while not self.cts_pin.value():
            self.poll_rx_fifo()

            if timeout_ms is not None:
                if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                    return False

        return True

    # =====================================================
    # TX side
    # =====================================================
    def write_byte(self, b, wait_cts=True):
        if wait_cts:
            if not self._wait_cts():
                return 0

        self.sm_tx.put(b & 0xFF)
        return 1

    def write(
        self,
        data,
        chunk_size=None,
        inter_chunk_us=None,
        wait_cts=True,
    ):
        """
        Write bytes with optional chunking and pacing.

        chunk_size:
            Number of bytes sent before inserting a gap.

        inter_chunk_us:
            Pause between chunks.

        wait_cts:
            If True and cts_pin is configured, wait until other side is ready.
        """
        if isinstance(data, int):
            return self.write_byte(data, wait_cts=wait_cts)

        if chunk_size is None:
            chunk_size = self.default_chunk_size

        if inter_chunk_us is None:
            inter_chunk_us = self.default_inter_chunk_us

        total = 0
        chunk_count = 0

        for b in data:
            if wait_cts:
                if not self._wait_cts():
                    return total

            self.sm_tx.put(b & 0xFF)
            total += 1
            chunk_count += 1

            # Opportunistically drain RX while transmitting
            self.poll_rx_fifo(max_bytes=4)

            if chunk_size and chunk_count >= chunk_size:
                chunk_count = 0

                # Let TX FIFO drain a little and give receiver time to catch up
                self.flush_fifo_only()
                if inter_chunk_us:
                    time.sleep_us(inter_chunk_us)

                self.poll_rx_fifo()

        return total

    def write_packet(
        self,
        payload,
        chunk_size=None,
        inter_chunk_us=None,
        wait_cts=True,
    ):
        """
        Sends a simple packet:

            0xA5
            length low byte
            length high byte
            payload bytes
            checksum

        checksum is simple 8-bit sum of payload.
        """
        length = len(payload)

        if length > 65535:
            raise ValueError("packet too large")

        checksum = sum(payload) & 0xFF

        packet = bytearray()
        packet.append(0xA5)
        packet.append(length & 0xFF)
        packet.append((length >> 8) & 0xFF)
        packet.extend(payload)
        packet.append(checksum)

        return self.write(
            packet,
            chunk_size=chunk_size,
            inter_chunk_us=inter_chunk_us,
            wait_cts=wait_cts,
        )

    def flush_fifo_only(self):
        """
        Wait until the PIO TX FIFO is empty.

        Note: this does not guarantee the final byte has fully left the pin,
        only that the FIFO has drained into the state machine.
        """
        try:
            while self.sm_tx.tx_fifo():
                self.poll_rx_fifo(max_bytes=4)
        except AttributeError:
            pass

    def flush(self):
        self.flush_fifo_only()

        # Wait roughly one full UART byte time for the final byte to finish
        bit_time_us = 1000000 // self.baudrate
        time.sleep_us(bit_time_us * 12)

    # =====================================================
    # RX side API
    # =====================================================
    def any(self):
        self.poll_rx_fifo()
        return self._rx_count()

    def read_byte_nonblocking(self):
        self.poll_rx_fifo()
        return self._rx_buf_get()

    def read_nonblocking(self, n=None):
        self.poll_rx_fifo()

        available = self._rx_count()

        if available == 0:
            return b""

        if n is None or n > available:
            n = available

        out = bytearray(n)

        for i in range(n):
            b = self._rx_buf_get()
            if b is None:
                return bytes(out[:i])
            out[i] = b

        return bytes(out)

    def read_packet_nonblocking(self):
        """
        Reads the packet format produced by write_packet().

        Returns:
            payload bytes if a complete valid packet is available
            None if incomplete
            b"" if bad packet/checksum was discarded
        """
        self.poll_rx_fifo()

        if self._rx_count() < 4:
            return None

        # Find start byte
        while self._rx_count() and self._rx_buf[self._rx_tail] != 0xA5:
            self._rx_buf_get()

        if self._rx_count() < 4:
            return None

        # Peek length
        start = self._rx_tail

        def peek(offset):
            return self._rx_buf[(start + offset) % self._rx_buf_size]

        if peek(0) != 0xA5:
            return b""

        length = peek(1) | (peek(2) << 8)
        total_len = 1 + 2 + length + 1

        if length > self._rx_buf_size - 8:
            self._rx_buf_get()
            return b""

        if self._rx_count() < total_len:
            return None

        # Consume header
        self._rx_buf_get()
        self._rx_buf_get()
        self._rx_buf_get()

        payload = bytearray(length)

        for i in range(length):
            payload[i] = self._rx_buf_get()

        received_checksum = self._rx_buf_get()
        calculated_checksum = sum(payload) & 0xFF

        if received_checksum != calculated_checksum:
            return b""

        return bytes(payload)

    def clear_rx_buffer(self):
        self._rx_head = 0
        self._rx_tail = 0
        self._update_rts()

    def line_idle(self):
        return bool(self.rx_pin.value())

    def debug_read_hw_byte_nonblocking(self):
        try:
            if self.sm_rx.rx_fifo():
                return self._extract_rx_byte(self.sm_rx.get())
        except AttributeError:
            pass
        return None
