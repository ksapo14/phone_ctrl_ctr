using System;
using System.IO;
using System.Runtime.InteropServices;

// A bounded PCM renderer, explicitly targeted at a virtual cable playback device.
// No default-device fallback: phone speech must never play through the monitors.
public static class PhoneAudio {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct Caps { public ushort mid,pid; public uint version; [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string name; public uint formats; public ushort channels,reserved; public uint support; }
    [StructLayout(LayoutKind.Sequential, Pack=2)]
    struct Format { public ushort tag,channels; public uint rate,bytes; public ushort align,bits,extra; }
    [StructLayout(LayoutKind.Sequential)]
    struct Header { public IntPtr data; public uint length,recorded; public UIntPtr user; public uint flags,loops; public IntPtr next; public UIntPtr reserved; }
    [DllImport("winmm.dll")] static extern uint waveOutGetNumDevs();
    [DllImport("winmm.dll", CharSet=CharSet.Unicode)] static extern uint waveOutGetDevCapsW(UIntPtr id,out Caps caps,uint size);
    [DllImport("winmm.dll")] static extern uint waveOutOpen(out IntPtr handle,uint id,ref Format format,IntPtr callback,IntPtr instance,uint flags);
    [DllImport("winmm.dll")] static extern uint waveOutPrepareHeader(IntPtr handle,IntPtr header,uint size);
    [DllImport("winmm.dll")] static extern uint waveOutUnprepareHeader(IntPtr handle,IntPtr header,uint size);
    [DllImport("winmm.dll")] static extern uint waveOutWrite(IntPtr handle,IntPtr header,uint size);
    [DllImport("winmm.dll")] static extern uint waveOutReset(IntPtr handle);
    [DllImport("winmm.dll")] static extern uint waveOutClose(IntPtr handle);
    static void Check(uint result) { if(result!=0) throw new IOException("Windows audio error "+result); }
    public static string[] Devices() {
        string[] names=new string[waveOutGetNumDevs()];
        for(uint i=0;i<names.Length;i++) { Caps caps; Check(waveOutGetDevCapsW((UIntPtr)i,out caps,(uint)Marshal.SizeOf(typeof(Caps)))); names[i]=caps.name; }
        return names;
    }
    public static void Run(string deviceName) {
        string[] names=Devices(); int selected=-1;
        for(int i=0;i<names.Length;i++) if(names[i].IndexOf(deviceName,StringComparison.OrdinalIgnoreCase)>=0) {
            if(selected>=0) throw new IOException("Multiple audio devices match. Set PHONE_AUDIO_DEVICE to a more specific name."); selected=i;
        }
        if(selected<0) throw new IOException("Virtual microphone not found. Install VB-CABLE, restart Windows, and select CABLE Output in Wispr. Expected playback device: "+deviceName);
        Format format=new Format {tag=1,channels=1,rate=48000,bytes=96000,align=2,bits=16,extra=0};
        IntPtr handle; Check(waveOutOpen(out handle,(uint)selected,ref format,IntPtr.Zero,IntPtr.Zero,0));
        IntPtr[] headers=new IntPtr[8], buffers=new IntPtr[8]; bool[] prepared=new bool[8], used=new bool[8];
        uint size=(uint)Marshal.SizeOf(typeof(Header));
        try {
            for(int i=0;i<headers.Length;i++) {
                buffers[i]=Marshal.AllocHGlobal(1920); headers[i]=Marshal.AllocHGlobal((int)size);
                Header header=new Header {data=buffers[i],length=1920}; Marshal.StructureToPtr(header,headers[i],false);
                Check(waveOutPrepareHeader(handle,headers[i],size)); prepared[i]=true;
            }
            Console.WriteLine("READY"); Console.Out.Flush();
            Stream input=Console.OpenStandardInput(); byte[] frame=new byte[1920]; int drops=0;
            while(true) {
                int offset=0;
                while(offset<frame.Length) { int count=input.Read(frame,offset,frame.Length-offset); if(count==0) return; offset+=count; }
                int slot=-1;
                for(int i=0;i<headers.Length;i++) {
                    Header header=(Header)Marshal.PtrToStructure(headers[i],typeof(Header));
                    if(!used[i] || (header.flags & 1)!=0) { slot=i; break; }
                }
                if(slot<0) { if(++drops>25) throw new IOException("Audio output stalled. Reconnect the phone microphone."); continue; }
                drops=0; Marshal.Copy(frame,0,buffers[slot],frame.Length); Check(waveOutWrite(handle,headers[slot],size)); used[slot]=true;
            }
        } finally {
            waveOutReset(handle);
            for(int i=0;i<headers.Length;i++) { if(prepared[i]) waveOutUnprepareHeader(handle,headers[i],size); if(headers[i]!=IntPtr.Zero) Marshal.FreeHGlobal(headers[i]); if(buffers[i]!=IntPtr.Zero) Marshal.FreeHGlobal(buffers[i]); }
            waveOutClose(handle);
        }
    }
}
