# -*- coding: utf-8 -*-
"""生成 Pico -> 1602(I2C) 接线图，所有文字由本脚本绘制。"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 1130
img = Image.new("RGB", (W, H), "#ffffff")
d = ImageDraw.Draw(img)

CN = r"C:\Windows\Fonts\msyh.ttc"
CNB = r"C:\Windows\Fonts\msyhbd.ttc"
MONO = r"C:\Windows\Fonts\consola.ttf"
f_title = ImageFont.truetype(CNB, 38)
f_sub = ImageFont.truetype(CN, 20)
f_pin = ImageFont.truetype(CN, 14)
f_num = ImageFont.truetype(CN, 13)
f_lbl = ImageFont.truetype(CNB, 19)
f_note = ImageFont.truetype(CN, 18)
f_lcd = ImageFont.truetype(MONO, 26)

d.text((60, 34), "Pico → 1602 液晶屏接线图（I2C 转接板）", font=f_title, fill="#111")
d.text((60, 86), "只需要 4 根线；先断电接线，再接 USB", font=f_sub, fill="#666")

# ---------------- Pico ----------------
px0, py0, px1, py1 = 140, 170, 470, 850
d.rounded_rectangle([px0, py0, px1, py1], 14, fill="#1c7a4a", outline="#0f5230", width=3)
d.rounded_rectangle([265, 146, 345, 176], 4, fill="#c9ced6", outline="#8b929c", width=2)
d.text((352, 148), "USB", font=f_pin, fill="#555")

LEFT = ["GP0", "GP1", "GND", "GP2", "GP3", "GP4", "GP5", "GND", "GP6", "GP7",
        "GP8", "GP9", "GND", "GP10", "GP11", "GP12", "GP13", "GND", "GP14", "GP15"]
RIGHT = ["VBUS", "VSYS", "GND", "3V3_EN", "3V3(OUT)", "ADC_VREF", "GP28", "GND",
         "GP27", "GP26", "RUN", "GP22", "GND", "GP21", "GP20", "GP19", "GP18",
         "GND", "GP17", "GP16"]
Y0, PITCH = 200, 32
HL = {6: "#2563eb", 7: "#16a34a", 36: "#dc2626", 38: "#111111", 40: "#dc2626"}


def yof(i):
    return Y0 + i * PITCH


for i, name in enumerate(LEFT):
    n, y = i + 1, yof(i)
    col = HL.get(n, "#b9c0c8")
    d.line([px0 - 16, y, px0, y], fill=col, width=6 if n in HL else 4)
    d.text((px0 - 22, y), str(n), font=f_num, fill=col if n in HL else "#888", anchor="rm")
    d.text((px0 + 12, y), name, font=f_pin,
           fill="#ffffff" if n in HL else "#cfe8d8", anchor="lm")

for i, name in enumerate(RIGHT):
    n, y = 40 - i, yof(i)
    col = HL.get(n, "#b9c0c8")
    d.line([px1, y, px1 + 16, y], fill=col, width=6 if n in HL else 4)
    d.text((px1 + 22, y), str(n), font=f_num, fill=col if n in HL else "#888", anchor="lm")
    d.text((px1 - 12, y), name, font=f_pin,
           fill="#ffffff" if n in HL else "#cfe8d8", anchor="rm")

d.rounded_rectangle([300, 800, 400, 834], 6, fill="#0f5230")
d.text((350, 817), "BOOTSEL", font=f_num, fill="#9fd3b4", anchor="mm")

# ---------------- LCD ----------------
lx0, ly0, lx1, ly1 = 900, 250, 1410, 650
d.rounded_rectangle([lx0, ly0, lx1, ly1], 10, fill="#2f6b3a", outline="#1d4525", width=3)
d.rounded_rectangle([932, 282, 1378, 486], 6, fill="#86a94f", outline="#4d6430", width=4)
d.text((955, 316), "CPU  45%  62.5C", font=f_lcd, fill="#1d2a12")
d.text((955, 372), "GPU  12%  46.0C", font=f_lcd, fill="#1d2a12")
d.text((1165, 566), "1602 LCD", font=f_lbl, fill="#ffffff", anchor="lm")
d.text((1165, 606), "带 PCF8574 I2C 转接板", font=f_note, fill="#cfe3d0", anchor="lm")

LCD_PINS = [("GND", "#111111", 520), ("VCC", "#dc2626", 553),
            ("SDA", "#2563eb", 586), ("SCL", "#16a34a", 619)]
for name, col, y in LCD_PINS:
    d.line([lx0 - 18, y, lx0, y], fill=col, width=6)
    d.text((lx0 + 12, y), name, font=f_pin, fill="#ffffff", anchor="lm")


def wire(pts, col, halo=False, w=7):
    if halo:
        d.line(pts, fill="#ffffff", width=w + 7, joint="curve")
    d.line(pts, fill=col, width=w, joint="curve")


# GND: pin38 -> LCD GND
wire([(px1 + 16, yof(2)), (640, yof(2)), (640, 520), (lx0 - 18, 520)], "#111111")
# VCC: pin36 -> LCD VCC（白色描边做出“跨线”效果）
wire([(px1 + 16, yof(4)), (700, yof(4)), (700, 553), (lx0 - 18, 553)], "#dc2626", halo=True)
# SDA: GP4 -> LCD SDA
wire([(px0 - 16, yof(5)), (74, yof(5)), (74, 930), (790, 930),
      (790, 586), (lx0 - 18, 586)], "#2563eb")
# SCL: GP5 -> LCD SCL
wire([(px0 - 16, yof(6)), (44, yof(6)), (44, 968), (830, 968),
      (830, 619), (lx0 - 18, 619)], "#16a34a")

d.text((660, 396), "GND", font=f_lbl, fill="#111111", anchor="lm")
d.text((714, 430), "VCC", font=f_lbl, fill="#dc2626", anchor="lm")
d.text((520, 916), "SDA", font=f_lbl, fill="#2563eb", anchor="mb")
d.text((520, 982), "SCL", font=f_lbl, fill="#16a34a", anchor="mt")

# ---------------- 说明 ----------------
d.rounded_rectangle([60, 1030, 1440, 1108], 10, fill="#fff7e6", outline="#f0c674", width=2)
d.text((82, 1044), "① VCC 先接 36 脚 3V3(OUT)；屏幕全亮却没字、或字很淡 → 改接 40 脚 VBUS(5V)",
       font=f_note, fill="#6b4700")
d.text((82, 1076), "② 用转接板上的电位器调对比度    ③ 一定断电插拔杜邦线    ④ 针脚丝印顺序以实物为准",
       font=f_note, fill="#6b4700")

img.save(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\pico-lcd-monitor\wiring_i2c.png")
print("saved")
