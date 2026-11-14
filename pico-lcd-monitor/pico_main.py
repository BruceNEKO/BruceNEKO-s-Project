# -*- coding: utf-8 -*-
# ================================================================
#  Raspberry Pi Pico / Pico W  —— 1602 LCD 显示电脑 CPU/GPU 状态
#  保存到 Pico 根目录，文件名必须是 main.py（上电自动运行）
#  依赖：无（LCD 驱动已内置，只用 machine / sys / select）
#
#  串口协议（电脑每秒发一行）：
#      cpu占用%,cpu温度,gpu占用%,gpu温度
#  例：  23,56.0,8,43.0       未知值用 -1
# ================================================================
from machine import Pin, I2C
import sys
import select
import time

# ---------------- 需要按你的接线修改的三个参数 ----------------
SDA_PIN = 4          # LCD SDA -> GP4（物理脚 6）
SCL_PIN = 5          # LCD SCL -> GP5（物理脚 7）
LCD_ADDR = None      # None = 自动扫描 0x27 / 0x3F；也可写死 0x27
# -------------------------------------------------------------


def pad(text, width=16):
    """MicroPython 没有 str.ljust()，自己补空格"""
    s = str(text)[:width]
    if len(s) < width:
        s += " " * (width - len(s))
    return s


class I2cLcd:
    """PCF8574 转 I2C 的 1602 屏驱动（4 位模式，最小实现）。
    PCF8574 位定义：P0=RS  P1=RW  P2=E  P3=背光  P4~P7=D4~D7
    如果你的模块位序不同，改下面的 RS/RW/EN/BL 常量即可。"""

    RS = 0x01
    RW = 0x02
    EN = 0x04
    BL = 0x08

    def __init__(self, i2c, addr=0x27, cols=16, rows=2):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        self._backlight = self.BL
        time.sleep_ms(60)
        # HD44780 上电初始化序列（前两条在 8 位模式下按“半字节”发送）
        for cmd in (0x33, 0x32, 0x28, 0x28, 0x0C, 0x01):
            self._cmd(cmd)
            time.sleep_ms(2)
        self._cmd(0x06)          # 输入模式：光标右移
        time.sleep_ms(2)
        self.clear()

    # ---- 底层 ----
    def _write(self, byte):
        self.i2c.writeto(self.addr, bytes([byte | self._backlight]))

    def _pulse(self, byte):
        self._write(byte | self.EN)
        time.sleep_us(60)
        self._write(byte & ~self.EN)
        time.sleep_us(60)

    def _nibble(self, nib, rs):
        self._pulse(((nib & 0x0F) << 4) | rs)

    def _byte(self, val, rs):
        self._nibble(val >> 4, rs)
        self._nibble(val, rs)

    def _cmd(self, c):
        self._byte(c, 0)

    # ---- 上层 ----
    def clear(self):
        self._cmd(0x01)
        time.sleep_ms(3)

    def move_to(self, col, row=0):
        self._cmd(0x80 | (col + (0x40 if row else 0)))

    def putstr(self, s):
        for ch in s:
            self._byte(ord(ch), self.RS)

    def line(self, row, text):
        """整行写入，自动补空格到 16 字符"""
        if row >= self.rows:
            return
        self.move_to(0, row)
        self.putstr(pad(text, self.cols))

    def backlight(self, on=True):
        self._backlight = self.BL if on else 0
        self._write(0)


def fmt(tag, pct, temp):
    """CPU  45%  62.5C  —— 固定 16 字符宽"""
    p = "%3d%%" % pct if pct >= 0 else " --%"
    t = "%5.1fC" % temp if temp >= 0 else " --.-C"
    return pad(tag + " " + p + " " + t, 16)


def find_lcd(i2c):
    if LCD_ADDR:
        return I2cLcd(i2c, LCD_ADDR)
    found = i2c.scan()
    for addr in (0x27, 0x3F, 0x20, 0x38):
        if addr in found:
            return I2cLcd(i2c, addr)
    if found:
        return I2cLcd(i2c, found[0])
    return None


def parse(line):
    """"23,56.0,8,43.0" -> (23, 56.0, 8, 43.0)，非法返回 None"""
    parts = line.split(",")
    if len(parts) != 4:
        return None
    try:
        return (int(float(parts[0])), float(parts[1]),
                int(float(parts[2])), float(parts[3]))
    except ValueError:
        return None


def main():
    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400_000)
    lcd = find_lcd(i2c)
    led = None
    for name in ("LED", 25):          # Pico W 用 "LED"，普通 Pico 用 25
        try:
            led = Pin(name, Pin.OUT)
            break
        except Exception:
            led = None

    if lcd is None:
        # 找不到屏：LED 快闪提示（I2C 接线/供电问题）
        while True:
            if led:
                led.toggle()
            time.sleep_ms(100)

    lcd.line(0, "PC Monitor")
    lcd.line(1, "waiting...")
    print("PICO_LCD_READY")        # 上电横幅，方便电脑端确认设备已就绪

    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)

    cpu_pct, cpu_t, gpu_pct, gpu_t = -1, -1.0, -1.0, -1.0
    last_rx = time.ticks_ms()
    stale = False

    while True:
        if poll.poll(0):
            try:
                line = sys.stdin.readline()
            except Exception:
                line = ""
            if line:
                s = line.strip()
                if s == "PING":                 # 链路自检
                    print("PONG")
                    continue
                v = parse(s)
                if v:
                    cpu_pct, cpu_t, gpu_pct, gpu_t = v
                    last_rx = time.ticks_ms()
                    if stale:
                        stale = False
                    lcd.line(0, fmt("CPU", cpu_pct, cpu_t))
                    lcd.line(1, fmt("GPU", gpu_pct, gpu_t))
                    if led:
                        led.toggle()

        # 5 秒没数据 -> 提示电脑端脚本没跑 / 串口没连上
        if not stale and time.ticks_diff(time.ticks_ms(), last_rx) > 5000:
            stale = True
            lcd.line(0, "CPU  --  no host")
            lcd.line(1, "GPU  --   link?")

        time.sleep_ms(20)


main()
