// Amplitude/pulse animation loops (Rule 13/19: browser audio mechanics).
// From Voice.jsx — two requestAnimationFrame loops that report a level value.
// Each factory returns { start, stop }; callers pass an onLevel callback that
// pushes the value into React state.

// Real microphone level from an AnalyserNode.
export function createAmplitudeLoop(onLevel) {
  let frame = null;
  const start = (analyser) => {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += Math.abs(data[i] - 128);
      onLevel(sum / data.length);
      frame = requestAnimationFrame(tick);
    };
    tick();
  };
  const stop = () => {
    if (frame) cancelAnimationFrame(frame);
    onLevel(0);
  };
  return { start, stop };
}

// Simulated breathing pulse used while the assistant is speaking.
export function createPulseLoop(onLevel) {
  let frame = null;
  const start = () => {
    let t = 0;
    const tick = () => {
      t += 0.08;
      onLevel(18 + Math.sin(t) * 12 + Math.sin(t * 2.3) * 6);
      frame = requestAnimationFrame(tick);
    };
    tick();
  };
  const stop = () => {
    if (frame) cancelAnimationFrame(frame);
    onLevel(0);
  };
  return { start, stop };
}
