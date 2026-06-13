// Persistent AudioContext (Rule 13/19: browser audio mechanics).
// From Voice.jsx getAudioContext. iOS Safari only allows an AudioContext to be
// created/resumed inside a user gesture, so we create one lazily on first tap
// and reuse it for every subsequent playback.

let ctx = null;

export async function getAudioContext() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  return ctx;
}
