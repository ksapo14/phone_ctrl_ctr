using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class WindowsControl {
    [StructLayout(LayoutKind.Sequential)] struct MouseInput { public int dx, dy; public uint data, flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct KeyInput { public ushort key, scan; public uint flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Explicit)] struct InputUnion { [FieldOffset(0)] public MouseInput mouse; [FieldOffset(0)] public KeyInput key; }
    [StructLayout(LayoutKind.Sequential)] struct Input { public uint type; public InputUnion data; }
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindow callback, IntPtr param);
    delegate bool EnumWindow(IntPtr hwnd, IntPtr param);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int max);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hwnd, int index);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr hwnd, uint cmd);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int cmd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint from, uint to, bool attach);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr hwnd, uint attr, out int value, int size);
    static bool leftHeld, rightHeld, x1Held;
    static void Emit(Input input) { if (SendInput(1, new Input[] { input }, Marshal.SizeOf(typeof(Input))) != 1) throw new InvalidOperationException("Windows blocked input. Elevated apps and the secure desktop cannot be controlled from a normal session."); }
    static void Mouse(uint flags, int dx, int dy, int data) { Input i = new Input(); i.data.mouse = new MouseInput { dx=dx, dy=dy, data=unchecked((uint)data), flags=flags }; Emit(i); }
    static void Key(ushort key, bool up) { Input i = new Input(); i.type=1; i.data.key = new KeyInput { key=key, flags=up ? 2u : 0u }; Emit(i); }
    public static void Move(int dx, int dy) { Mouse(1, dx, dy, 0); }
    public static void Scroll(int dx, int dy) { if(dy != 0) Mouse(0x800,0,0,dy); if(dx != 0) Mouse(0x1000,0,0,dx); }
    public static void Button(string button, bool down) {
      if(button=="x1") { Mouse(down?0x80u:0x100u,0,0,1); x1Held=down; return; }
      if(button!="left" && button!="right") throw new ArgumentException("Unknown mouse button");
      bool left=button=="left"; Mouse(left ? (down?2u:4u) : (down?8u:16u),0,0,0); if(left) leftHeld=down; else rightHeld=down;
    }
    public static void Click(string button) { Button(button,true); Button(button,false); }
    public static void DoubleClick(string button) { Click(button); System.Threading.Thread.Sleep(80); Click(button); }
    public static void Release() { if(leftHeld) Button("left",false); if(rightHeld) Button("right",false); if(x1Held) Button("x1",false); }
    static void Chord(params ushort[] keys) { int pressed=0; try { foreach(ushort k in keys) { Key(k,false); pressed++; } } finally { for(int i=pressed-1;i>=0;i--) Key(keys[i],true); } }
    public static void Media(string action) {
      switch(action) {
        case "playPause": Chord(0xB3); break;
        case "next": Chord(0xB0); break;
        case "previous": Chord(0xB1); break;
        case "stop": Chord(0xB2); break;
        default: throw new ArgumentException("Unknown media action");
      }
    }
    public static void Gesture(string name) {
      switch(name) {
        case "taskView": Chord(0x5B,0x09); break;
        case "desktop": Chord(0x5B,0x44); break;
        case "nextWindow": SwitchWindow(1); break;
        case "previousWindow": SwitchWindow(-1); break;
        case "nextDesktop": Chord(0x5B,0x11,0x27); break;
        case "previousDesktop": Chord(0x5B,0x11,0x25); break;
        case "search": Chord(0x5B,0x53); break;
        case "notifications": Chord(0x5B,0x4E); break;
        default: throw new ArgumentException("Unknown gesture");
      }
    }
    public static void Zoom(int delta) { Key(0x11,false); try { Scroll(0,delta); } finally { Key(0x11,true); } }
    public class WindowInfo { public string id; public string title; public bool active; }
    static List<string> switchOrder=new List<string>();
    static DateTime lastSwitch=DateTime.MinValue;
    static void SwitchWindow(int direction) {
      WindowInfo[] current=Windows();
      if((DateTime.UtcNow-lastSwitch).TotalSeconds>2) { switchOrder.Clear(); foreach(WindowInfo w in current) switchOrder.Add(w.id); }
      switchOrder.RemoveAll(id => !Array.Exists(current,w => w.id==id));
      if(switchOrder.Count==0) return;
      int index=switchOrder.IndexOf(GetForegroundWindow().ToInt64().ToString());
      int next=(Math.Max(0,index)+direction+switchOrder.Count)%switchOrder.Count;
      Focus(switchOrder[next]); lastSwitch=DateTime.UtcNow;
    }
    public static WindowInfo[] Windows() {
      List<WindowInfo> result=new List<WindowInfo>(); IntPtr foreground=GetForegroundWindow();
      EnumWindows(delegate(IntPtr hwnd, IntPtr unused) {
        if(!IsWindowVisible(hwnd) || GetWindow(hwnd,4)!=IntPtr.Zero || (GetWindowLong(hwnd,-20)&0x80)!=0) return true;
        int cloaked; if(DwmGetWindowAttribute(hwnd,14,out cloaked,4)==0 && cloaked!=0) return true;
        StringBuilder title=new StringBuilder(512); GetWindowText(hwnd,title,title.Capacity);
        if(title.Length>0) result.Add(new WindowInfo { id=hwnd.ToInt64().ToString(), title=title.ToString(), active=hwnd==foreground });
        return true;
      },IntPtr.Zero);
      return result.ToArray();
    }
    public static void Focus(string id) {
      bool found=false; foreach(WindowInfo w in Windows()) if(w.id==id) found=true;
      if(!found) throw new InvalidOperationException("That window is no longer open.");
      IntPtr hwnd=new IntPtr(long.Parse(id)); if(IsIconic(hwnd)) ShowWindow(hwnd,9);
      uint pid; uint foregroundThread=GetWindowThreadProcessId(GetForegroundWindow(),out pid); uint current=GetCurrentThreadId();
      bool attached=foregroundThread!=current && AttachThreadInput(current,foregroundThread,true);
      try { if(!SetForegroundWindow(hwnd)) { Key(0x12,false); Key(0x12,true); if(!SetForegroundWindow(hwnd)) throw new InvalidOperationException("Windows prevented switching to this window."); } }
      finally { if(attached) AttachThreadInput(current,foregroundThread,false); }
    }

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class DeviceEnumerator {}
    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IDeviceEnumerator {
      int EnumAudioEndpoints(int flow, uint mask, out IntPtr devices);
      [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
    }
    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IDevice {
      [PreserveSig] int Activate(ref Guid iid, uint context, IntPtr activation, [MarshalAs(UnmanagedType.IUnknown)] out object endpoint);
    }
    [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IEndpointVolume {
      [PreserveSig] int RegisterControlChangeNotify(IntPtr notify); [PreserveSig] int UnregisterControlChangeNotify(IntPtr notify); [PreserveSig] int GetChannelCount(out uint count);
      [PreserveSig] int SetMasterVolumeLevel(float level, ref Guid context); [PreserveSig] int SetMasterVolumeLevelScalar(float level, ref Guid context);
      [PreserveSig] int GetMasterVolumeLevel(out float level); [PreserveSig] int GetMasterVolumeLevelScalar(out float level);
    }
    static IEndpointVolume Endpoint() {
      IDeviceEnumerator enumerator=(IDeviceEnumerator)new DeviceEnumerator(); IDevice device=null;
      try { Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0,1,out device)); object endpoint; Guid iid=typeof(IEndpointVolume).GUID; Marshal.ThrowExceptionForHR(device.Activate(ref iid,23,IntPtr.Zero,out endpoint)); return (IEndpointVolume)endpoint; }
      finally { if(device!=null) Marshal.ReleaseComObject(device); Marshal.ReleaseComObject(enumerator); }
    }
    public static int Volume() { IEndpointVolume endpoint=Endpoint(); try { float level; Marshal.ThrowExceptionForHR(endpoint.GetMasterVolumeLevelScalar(out level)); return (int)Math.Round(level*100); } finally { Marshal.ReleaseComObject(endpoint); } }
    public static void SetVolume(int value) { IEndpointVolume endpoint=Endpoint(); try { Guid context=Guid.Empty; Marshal.ThrowExceptionForHR(endpoint.SetMasterVolumeLevelScalar(value/100f,ref context)); } finally { Marshal.ReleaseComObject(endpoint); } }

    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct PhysicalMonitor { public IntPtr handle; [MarshalAs(UnmanagedType.ByValTStr,SizeConst=128)] public string description; }
    delegate bool EnumMonitor(IntPtr monitor, IntPtr hdc, IntPtr rect, IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr clip, EnumMonitor callback, IntPtr data);
    [DllImport("dxva2.dll")] static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr monitor,out uint count);
    [DllImport("dxva2.dll")] static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr monitor,uint count,[Out] PhysicalMonitor[] physical);
    [DllImport("dxva2.dll")] static extern bool DestroyPhysicalMonitors(uint count,PhysicalMonitor[] monitors);
    [DllImport("dxva2.dll")] static extern bool GetMonitorBrightness(IntPtr monitor,out uint min,out uint current,out uint max);
    [DllImport("dxva2.dll")] static extern bool SetMonitorBrightness(IntPtr monitor,uint value);
    public static int MonitorBrightness(int setValue) {
      int result=-1;
      EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,delegate(IntPtr monitor,IntPtr hdc,IntPtr rect,IntPtr data) {
        uint count; if(!GetNumberOfPhysicalMonitorsFromHMONITOR(monitor,out count)||count==0) return true;
        PhysicalMonitor[] physical=new PhysicalMonitor[count]; if(!GetPhysicalMonitorsFromHMONITOR(monitor,count,physical)) return true;
        try { foreach(PhysicalMonitor p in physical) { uint min,current,max; if(GetMonitorBrightness(p.handle,out min,out current,out max)&&max>min) {
          if(setValue>=0) { if(!SetMonitorBrightness(p.handle,min+(uint)((max-min)*setValue/100))) continue; current=min+(uint)((max-min)*setValue/100); }
          result=(int)((current-min)*100/(max-min));
        } } } finally { DestroyPhysicalMonitors(count,physical); } return true;
      },IntPtr.Zero);
      return result;
    }
}
