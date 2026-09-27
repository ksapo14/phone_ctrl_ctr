// 20 ms frames of mono signed 16-bit little-endian PCM at 48 kHz.
class PhoneMicProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.frame = new ArrayBuffer(1920); this.view = new DataView(this.frame); this.offset = 0; this.phase = 0; }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (const sample of channel) {
      this.phase += 48000 / sampleRate;
      while (this.phase >= 1) {
        this.phase -= 1;
        const value = Math.max(-1, Math.min(1, sample));
        this.view.setInt16(this.offset, Math.round(value * (value < 0 ? 32768 : 32767)), true);
        this.offset += 2;
        if (this.offset === 1920) {
          this.port.postMessage(this.frame, [this.frame]);
          this.frame = new ArrayBuffer(1920); this.view = new DataView(this.frame); this.offset = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('phone-mic', PhoneMicProcessor);
