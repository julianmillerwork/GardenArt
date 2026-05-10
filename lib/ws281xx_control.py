import array
import struct
import rp2
from machine import Pin
from time import ticks_ms, ticks_diff, sleep_ms

# =========================================================
# PIO drivers
# =========================================================

# 24-bit WS281x RGB
@rp2.asm_pio(
    sideset_init=rp2.PIO.OUT_LOW,
    out_shiftdir=rp2.PIO.SHIFT_LEFT,
)
def ws2812_rgb():
    T1 = 2
    T2 = 5
    T3 = 3

    wrap_target()
    pull(block)
    set(y, 23)

    label("bitloop")
    out(x, 1)               .side(0) [T3 - 1]
    jmp(not_x, "do_zero")   .side(1) [T1 - 1]
    jmp("cont")             .side(1) [T2 - 1]
    label("do_zero")
    nop()                   .side(0) [T2 - 1]
    label("cont")
    jmp(y_dec, "bitloop")
    wrap()


# 32-bit WS281x RGBW
@rp2.asm_pio(
    sideset_init=rp2.PIO.OUT_LOW,
    out_shiftdir=rp2.PIO.SHIFT_LEFT,
)
def ws2812_rgbw():
    T1 = 2
    T2 = 5
    T3 = 3

    wrap_target()
    pull(block)
    set(y, 31)

    label("bitloop")
    out(x, 1)               .side(0) [T3 - 1]
    jmp(not_x, "do_zero")   .side(1) [T1 - 1]
    jmp("cont")             .side(1) [T2 - 1]
    label("do_zero")
    nop()                   .side(0) [T2 - 1]
    label("cont")
    jmp(y_dec, "bitloop")
    wrap()


class FastWS281x:
    def __init__(self, pin_num, num_leds, rgbw=False, sm_id=0, freq=8_000_000):
        self.num_leds = num_leds
        self.rgbw = rgbw
        self.buf = array.array("I", [0] * num_leds)

        if rgbw:
            prog = ws2812_rgbw
        else:
            prog = ws2812_rgb

        self.sm = rp2.StateMachine(
            sm_id,
            prog,
            freq=freq,
            sideset_base=Pin(pin_num)
        )
        self.sm.active(1)

    def show_buf(self, buf):
        self.sm.put(buf)
        sleep_ms(1)  # latch/reset


# =========================================================
# Packing helpers
# =========================================================

def pack_by_order(order, r, g, b, w=0):
    if order == "GRB":
        return (g << 16) | (r << 8) | b
    elif order == "RGB":
        return (r << 16) | (g << 8) | b
    elif order == "BRG":
        return (b << 16) | (r << 8) | g
    elif order == "GRBW":
        return (g << 24) | (r << 16) | (b << 8) | w
    elif order == "RGBW":
        return (r << 24) | (g << 16) | (b << 8) | w
    elif order == "BRGW":
        return (b << 24) | (r << 16) | (g << 8) | w
    elif order == "WRGB":
        return (w << 24) | (r << 16) | (g << 8) | b
    else:
        raise ValueError("Unsupported PIXEL_ORDER: {}".format(order))


def pack_for_strip(r, g, b, w, pixel_order):
    return pack_by_order(pixel_order, r, g, b, w)
