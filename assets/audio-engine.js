/* Browser audio preview, with PCM WAV fallback. No Node.js runtime required. */
(function (root) {
  'use strict';
  function parseWav(bytes) {
    const v = new DataView(bytes); const tag = n => String.fromCharCode(...new Uint8Array(bytes, n, 4));
    if (bytes.byteLength < 44 || tag(0) !== 'RIFF' || tag(8) !== 'WAVE') throw Error('Expected PCM WAV');
    let rate, channels, bits, format, dataOffset, dataLength;
    for (let p = 12; p + 8 <= bytes.byteLength;) {
      const name = tag(p), size = v.getUint32(p + 4, true);
      if (name === 'fmt ') { format = v.getUint16(p + 8, true); channels = v.getUint16(p + 10, true); rate = v.getUint32(p + 12, true); bits = v.getUint16(p + 22, true); }
      if (name === 'data') { dataOffset = p + 8; dataLength = Math.min(size, bytes.byteLength - dataOffset); break; }
      p += 8 + size + (size % 2);
    }
    if (format !== 1 || channels !== 1 || bits !== 16 || !rate || dataOffset === undefined) throw Error('Expected mono 16-bit PCM');
    const samples = new Float32Array(Math.floor(dataLength / 2));
    for (let i = 0; i < samples.length; i++) samples[i] = v.getInt16(dataOffset + i * 2, true) / 32768;
    return { samples, sampleRate: rate };
  }
  function makeWav(samples, rate) {
    const raw = new ArrayBuffer(44 + samples.length * 2), v = new DataView(raw);
    function str(p, s) { for (let i = 0; i < s.length; i++) v.setUint8(p + i, s.charCodeAt(i)); }
    str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) v.setInt16(44 + 2 * i, Math.max(-32768, Math.min(32767, Math.round(samples[i] * 32768))), true);
    return raw;
  }
  function sliceRanges(samples, rate, origin, parts) {
    const slices = parts.map(([a, b]) => {
      if (!Number.isFinite(a) || !Number.isFinite(b) || !(a < b) || a < origin - .001 || b > origin + samples.length / rate + .002) throw Error('Preview range outside loaded audio');
      return samples.slice(Math.max(0, Math.round((a - origin) * rate)), Math.min(samples.length, Math.round((b - origin) * rate)));
    });
    const out = new Float32Array(slices.reduce((n, s) => n + s.length, 0)); let offset = 0;
    for (const s of slices) { out.set(s, offset); offset += s.length; } return out;
  }
  function bounded(promise, ms) {
    let timer; return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Audio operation timed out')), ms); })]).finally(() => clearTimeout(timer));
  }
  class ReviewAudio {
    constructor(options = {}) { this.forceNative = options.forceNative || false; this.element = options.element; this.fetch = options.fetch || root.fetch.bind(root); this.sources = []; this.context = null; this.samples = null; }
    async load(start, end) {
      this.stop(); const response = await this.fetch(`/api/audio?start=${start}&end=${end}`);
      if (!response.ok) throw Error('Cannot load source audio');
      const raw = await response.arrayBuffer(), parsed = parseWav(raw); this.origin = start; this.samples = parsed.samples; this.sampleRate = parsed.sampleRate; this.buffer = null;
      const Ctx = root.AudioContext || root.webkitAudioContext;
      if (!this.forceNative && Ctx) {
        try { this.context ||= new Ctx(); this.buffer = await bounded(this.context.decodeAudioData(raw.slice(0)), 2000); }
        catch (_) { this.buffer = null; }
      }
      return this;
    }
    stop() { for (const s of this.sources) { try { s.stop(); } catch (_) {} } this.sources = []; if (this.element) this.element.pause(); if (this.objectUrl) { root.URL.revokeObjectURL(this.objectUrl); this.objectUrl = null; } }
    async play(parts) {
      this.stop(); if (!this.samples) throw Error('Load selected source audio first');
      const joined = sliceRanges(this.samples, this.sampleRate, this.origin, parts);
      if (!joined.length) throw Error('No retained audio in this preview');
      if (this.buffer && this.context) {
        try {
          await bounded(this.context.resume(), 1200); if (this.context.state !== 'running') throw Error('AudioContext suspended');
          let when = this.context.currentTime + .03;
          for (const [a, b] of parts) { const s = this.context.createBufferSource(); s.buffer = this.buffer; s.connect(this.context.destination); s.start(when, a - this.origin, b - a); this.sources.push(s); when += b - a; }
          if (this.element) this.element.hidden = true; return 'web-audio';
        } catch (_) { this.stop(); }
      }
      if (!this.element) throw Error('HTML audio playback unavailable');
      this.objectUrl = root.URL.createObjectURL(new Blob([makeWav(joined, this.sampleRate)], { type: 'audio/wav' }));
      this.element.src = this.objectUrl; this.element.hidden = false;
      try { await bounded(this.element.play(), 1200); return 'html-audio'; } catch (_) { return 'html-audio-needs-click'; }
    }
  }
  ReviewAudio.parseWav = parseWav; ReviewAudio.makeWav = makeWav; ReviewAudio.sliceRanges = sliceRanges;
  if (typeof module !== 'undefined' && module.exports) module.exports = ReviewAudio; else root.ReviewAudio = ReviewAudio;
})(typeof globalThis !== 'undefined' ? globalThis : this);
