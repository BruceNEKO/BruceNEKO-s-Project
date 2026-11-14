#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把电脑的 CPU / GPU 占用率和温度，通过 USB 串口发给 Pico，
由 Pico 显示在 1602 液晶屏上。

用法：
    python pc_stats.py                 # 自动找 Pico 串口并发送
    python pc_stats.py -p COM3         # 手动指定串口
    python pc_stats.py --list          # 列出所有串口
    python pc_stats.py --dry-run       # 不连 Pico，只在控制台看数据
    python pc_stats.py --diag          # 只测传感器读取，然后退出

依赖：  pip install psutil pyserial
CPU 温度来自 LibreHardwareMonitor 的桥接程序 lhm_bridge.exe（已随项目装好）。
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
HERE = os.path.dirname(os.path.abspath(__file__))


def run_cmd(args, timeout=8):
    """跑一个外部命令，返回 stdout 或 None（不弹黑窗）"""
    try:
        p = subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        if p.returncode == 0:
            return p.stdout.decode("utf-8", "replace")
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# GPU：nvidia-smi（N 卡最准，也最轻）
# ------------------------------------------------------------------
NVSMI_CANDIDATES = [
    "nvidia-smi",
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
]


def read_gpu_nvidia():
    for exe in NVSMI_CANDIDATES:
        out = run_cmd([exe, "--query-gpu=utilization.gpu,temperature.gpu",
                       "--format=csv,noheader,nounits"], timeout=5)
        if not out:
            continue
        parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
        if len(parts) < 2:
            continue
        try:
            util = int(parts[0])
        except ValueError:
            util = -1
        try:
            temp = float(parts[1])
        except ValueError:
            temp = -1.0
        return util, temp
    return None, None


# ------------------------------------------------------------------
# CPU 温度：LibreHardwareMonitor 桥接程序
#   LibreHardwareMonitor 0.9.6 已经移除了 WMI 和 Web 服务，
#   所以改用 csc 编译的 lhm_bridge.exe 直接读 LibreHardwareMonitorLib.dll。
#   它走 PawnIO 内核驱动，普通用户权限即可，LHM 界面不用开着。
# ------------------------------------------------------------------
BRIDGE_CANDIDATES = [
    r"C:\Tools\LibreHardwareMonitor\lhm_bridge.exe",
    os.path.join(HERE, "lhm_bridge.exe"),
]


def find_bridge():
    for p in BRIDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def read_bridge(path):
    if not path:
        return None
    try:
        p = subprocess.run([path], capture_output=True, timeout=10,
                           creationflags=CREATE_NO_WINDOW)
        if p.returncode != 0 or not p.stdout:
            return None
        return json.loads(p.stdout.decode("utf-8", "replace"))
    except Exception:
        return None


class SensorReader(threading.Thread):
    """后台线程，每 2 秒刷新一次 CPU 温度，顺便兜底 GPU"""

    def __init__(self, period=2.0):
        super().__init__(daemon=True)
        self.period = period
        self.bridge = find_bridge()
        self.cpu_temp = None
        self.gpu_temp = None
        self.gpu_load = None
        self.cpu_name = ""
        self.gpu_name = ""
        self.ok = False

    def _refresh(self):
        d = read_bridge(self.bridge)
        if not d or "cpu_temp" not in d:
            self.ok = False
            return
        self.ok = True
        t = d.get("cpu_temp", -1)
        if isinstance(t, (int, float)) and t >= 0:
            self.cpu_temp = float(t)
        gt = d.get("gpu_temp", -1)
        if isinstance(gt, (int, float)) and gt >= 0:
            self.gpu_temp = float(gt)
        gl = d.get("gpu_load", -1)
        if isinstance(gl, (int, float)) and gl >= 0:
            self.gpu_load = float(gl)
        self.cpu_name = d.get("cpu_name", "") or self.cpu_name
        self.gpu_name = d.get("gpu_name", "") or self.gpu_name

    def run(self):
        while True:
            try:
                self._refresh()
            except Exception:
                self.ok = False
            time.sleep(self.period)


def read_cpu_temp_fallback():
    """没有桥接程序时的兜底（很多台式机读不到，返回 None）"""
    ps = ("$t=Get-CimInstance -Namespace root/WMI "
          "-ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue;"
          "if($t){($t | Measure-Object -Property CurrentTemperature "
          "-Maximum).Maximum}")
    out = run_cmd(["powershell", "-NoProfile", "-Command", ps])
    try:
        return round(float(out.strip()) / 10.0 - 273.15, 1)
    except Exception:
        return None


# ------------------------------------------------------------------
# 串口
# ------------------------------------------------------------------
def find_pico_port():
    if not serial:
        return None
    cands = []
    for p in list_ports.comports():
        text = " ".join(str(x) for x in (p.description, p.manufacturer, p.hwid))
        if any(k in text for k in ("MicroPython", "USB 串行设备",
                                   "USB Serial Device", "2E8A", "Board CDC")):
            cands.append(p.device)
    if cands:
        return cands[0]
    ports = [p.device for p in list_ports.comports()]
    return ports[0] if ports else None


LAST_ERROR = []


def open_serial(port, baud=115200, quiet=False):
    if not serial:
        return None
    try:
        ser = serial.Serial(port, baud, timeout=1, write_timeout=2)
        time.sleep(0.3)
        LAST_ERROR.clear()
        return ser
    except Exception as e:
        LAST_ERROR[:] = [str(e)]
        if not quiet:
            print("串口打开失败：", e)
        return None


def port_busy():
    """错误信息里判断是不是「被别的程序占着」"""
    if not LAST_ERROR:
        return False
    msg = LAST_ERROR[0]
    return any(k in msg for k in ("PermissionError", "拒绝访问",
                                  "Access is denied", "busy", "占用"))


def handshake(ser, timeout=1.5):
    """发 PING，确认 Pico 端的 main.py 真在跑并会回 PONG"""
    try:
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        ser.flush()
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b"PONG" in buf:
                    return True
        return False
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="CPU/GPU 状态 -> Pico + 1602 LCD")
    ap.add_argument("-p", "--port", help="串口，如 COM3")
    ap.add_argument("-i", "--interval", type=float, default=1.0, help="刷新秒数")
    ap.add_argument("--dry-run", action="store_true", help="只在控制台打印")
    ap.add_argument("--diag", action="store_true", help="打印传感器来源后退出")
    ap.add_argument("--list", action="store_true", help="列出串口后退出")
    args = ap.parse_args()

    if args.list:
        for p in list_ports.comports():
            print(p.device, "-", p.description)
        return

    if psutil is None:
        print("缺少 psutil：pip install psutil")
        return

    psutil.cpu_percent(interval=None)          # 预热

    reader = SensorReader()
    print("温度源：", reader.bridge or "未找到 lhm_bridge.exe（CPU 温度会显示 --.-C）")
    reader.start()
    time.sleep(1.5)

    if args.diag:
        nv = read_gpu_nvidia()
        print("CPU : %s  温度 %s" % (reader.cpu_name or "?",
                                     "%.1fC" % reader.cpu_temp if reader.cpu_temp is not None else "读不到"))
        print("GPU : %s  温度 %s  占用 %s" % (reader.gpu_name or "?",
                                            "%.1fC" % reader.gpu_temp if reader.gpu_temp is not None else "读不到",
                                            "%d%%" % reader.gpu_load if reader.gpu_load is not None else "读不到"))
        print("nvidia-smi 直接读：", nv)
        return

    fallback_temp = None
    fallback_checked = False

    ser = None
    port = args.port or find_pico_port()
    if not args.dry_run:
        print("使用串口：", port)
        ser = open_serial(port) if port else None
        if ser is None and port_busy():
            print("")
            print("*** %s 被别的程序占用了 ***" % port)
            print("多半是已经有一个 start_monitor.bat 窗口在跑，")
            print("或者 Thonny 还连着 Pico。关掉那个窗口/程序再双击本文件。")
            return
        if ser:
            if handshake(ser):
                print("Pico 已握手：main.py 正在运行，开始推送数据。")
            else:
                print("警告：Pico 没有回应（main.py 没在跑？屏没接？）——继续尝试发送。")

    print("开始采样，Ctrl+C 结束。")
    try:
        while True:
            cpu_pct = int(round(psutil.cpu_percent(interval=None)))
            gpu_pct, gpu_temp = read_gpu_nvidia()
            if gpu_pct is None:
                gpu_pct = int(reader.gpu_load) if reader.gpu_load is not None else -1
            if gpu_temp is None:
                gpu_temp = reader.gpu_temp if reader.gpu_temp is not None else -1.0

            cpu_temp = reader.cpu_temp
            if cpu_temp is None and not fallback_checked:
                fallback_temp = read_cpu_temp_fallback()
                fallback_checked = True
            if cpu_temp is None:
                cpu_temp = fallback_temp
            if cpu_temp is None:
                cpu_temp = -1.0

            line = "%d,%.1f,%d,%.1f" % (cpu_pct, cpu_temp, gpu_pct, gpu_temp)

            if args.dry_run:
                print("CPU %3d%%  %5.1fC   |   GPU %3d%%  %5.1fC" % (
                    cpu_pct, cpu_temp, gpu_pct, gpu_temp))
            else:
                if ser is None:
                    ser = open_serial(port, quiet=True) if port else None
                    if ser:
                        print("串口已重新连上。")
                if ser is not None:
                    try:
                        ser.write((line + "\n").encode())
                        ser.flush()
                    except Exception:
                        try:
                            ser.close()
                        except Exception:
                            pass
                        ser = None

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        if ser:
            ser.close()


if __name__ == "__main__":
    main()
