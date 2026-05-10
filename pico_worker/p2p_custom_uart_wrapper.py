# p2p_custom_uart_wrapper.py
#
# Standard MicroPython UART wrapper.
#
# Wiring:
#   UART0 TX = GP0
#   UART0 RX = GP1
#
# Pico-to-Pico:
#   Master GP0 TX -> Worker GP1 RX
#   Master GP1 RX <- Worker GP0 TX
#   GND <-> GND

from machine import UART, Pin
import time


# =========================================================
# UART configuration
# =========================================================
UART_ID = 0
TX_PIN = 0
RX_PIN = 1
BAUDRATE = 921600

# MicroPython UART RX buffer.
# Large buffer helps during file transfer bursts.
RX_BUF_SIZE = 8192

_uart = UART(
    UART_ID,
    baudrate=BAUDRATE,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(TX_PIN),
    rx=Pin(RX_PIN),
    rxbuf=RX_BUF_SIZE,
)


# =========================================================
# TX helpers
# =========================================================
def uart_send_byte(b):
    if isinstance(b, bytes) or isinstance(b, bytearray):
        b = b[0]

    _uart.write(bytes([b & 0xFF]))


def uart_send_bytes(data):
    if data is None:
        return 0

    if isinstance(data, int):
        return uart_send_byte(data)

    written = _uart.write(data)
    if written is None:
        return 0
    return written


# =========================================================
# RX helpers
# =========================================================
def uart_any():
    n = _uart.any()
    if n is None:
        return 0
    return n


def uart_read_byte_nonblocking():
    if not _uart.any():
        return None

    b = _uart.read(1)
    if not b:
        return None

    return b[0]


def uart_read_bytes_nonblocking(n=None):
    available = _uart.any()

    if not available:
        return b""

    if n is None or n > available:
        n = available

    data = _uart.read(n)
    if data is None:
        return b""

    return data


# =========================================================
# Flush / cleanup
# =========================================================
def uart_flush():
    """
    Best-effort TX drain.

    machine.UART on RP2040 MicroPython does not consistently expose a real
    flush method across versions, so this waits long enough for a small response
    packet to leave the UART.

    At 115200 baud:
      1 byte = roughly 10 bits = 86.8 us
    """
    try:
        _uart.flush()
        return
    except AttributeError:
        pass

    # Small conservative guard delay.
    time.sleep_ms(2)


def uart_deinit():
    try:
        _uart.deinit()
    except AttributeError:
        pass


# =========================================================
# Compatibility with previous PIO wrapper
# =========================================================
def uart_debug_read_hw_byte_nonblocking():
    return uart_read_byte_nonblocking()