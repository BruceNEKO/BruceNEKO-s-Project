using System;
using System.Globalization;
using System.Text;
using LibreHardwareMonitor.Hardware;

// 通过 LibreHardwareMonitorLib.dll 读取 CPU/GPU 传感器，输出一行 JSON。
// 编译： csc /r:LibreHardwareMonitorLib.dll /out:lhm_bridge.exe lhm_bridge.cs
class LhmBridge
{
    static void UpdateAll(IHardware hw)
    {
        hw.Update();
        foreach (IHardware sub in hw.SubHardware) UpdateAll(sub);
    }

    static string F(double v)
    {
        return v.ToString("0.0", CultureInfo.InvariantCulture);
    }

    static string Q(string s)
    {
        if (s == null) s = "";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }

    static int Main(string[] args)
    {
        Computer c = new Computer();
        c.IsCpuEnabled = true;
        c.IsGpuEnabled = true;
        c.IsMotherboardEnabled = false;
        c.IsControllerEnabled = false;
        try { c.Open(); }
        catch (Exception e)
        {
            Console.Write("{\"error\":" + Q(e.Message) + "}");
            return 2;
        }

        double tctl = -1, die = -1, pkg = -1, anyCpu = -1;
        double gpuT = -1, gpuL = -1;
        string cpuName = "", gpuName = "";

        foreach (IHardware hw in c.Hardware)
        {
            UpdateAll(hw);
            if (hw.HardwareType == HardwareType.Cpu)
            {
                if (cpuName == "") cpuName = hw.Name;
                foreach (ISensor s in hw.Sensors)
                {
                    if (s.SensorType != SensorType.Temperature || s.Value == null) continue;
                    double v = s.Value.Value;
                    string n = s.Name.ToLower();
                    if (n.IndexOf("tctl/tdie") >= 0) tctl = v;
                    else if (n.IndexOf("tctl") >= 0) tctl = v;
                    else if (n.IndexOf("package") >= 0) pkg = v;
                    else if (n.IndexOf("tdie") >= 0 || n.IndexOf("die") >= 0) die = v;
                    if (anyCpu < 0 || v > anyCpu) anyCpu = v;
                }
            }
            else if (hw.HardwareType == HardwareType.GpuNvidia ||
                     hw.HardwareType == HardwareType.GpuAmd ||
                     hw.HardwareType == HardwareType.GpuIntel)
            {
                if (gpuName == "") gpuName = hw.Name;
                foreach (ISensor s in hw.Sensors)
                {
                    if (s.Value == null) continue;
                    if (s.SensorType == SensorType.Temperature)
                    {
                        if (gpuT < 0 || s.Name.ToLower().IndexOf("core") >= 0) gpuT = s.Value.Value;
                    }
                    else if (s.SensorType == SensorType.Load &&
                             s.Name.ToLower().IndexOf("core") >= 0)
                    {
                        gpuL = s.Value.Value;
                    }
                }
            }
        }

        double cpuT = tctl >= 0 ? tctl : (die >= 0 ? die : (pkg >= 0 ? pkg : anyCpu));

        StringBuilder sb = new StringBuilder();
        sb.Append("{\"cpu_temp\":").Append(F(cpuT));
        sb.Append(",\"gpu_temp\":").Append(F(gpuT));
        sb.Append(",\"gpu_load\":").Append(F(gpuL));
        sb.Append(",\"cpu_name\":").Append(Q(cpuName));
        sb.Append(",\"gpu_name\":").Append(Q(gpuName));
        sb.Append("}");

        try { Console.OutputEncoding = Encoding.UTF8; } catch {}
        Console.Write(sb.ToString());
        c.Close();
        return 0;
    }
}
