// Audio playback (Rule 13/19: browser audio mechanics).
// Decode + play through the persistent AudioContext (iOS-safe). Combines
// App.jsx playAudioBlob and Voice.jsx playBase64Audio, plus a small queue that
// serialises streamed TTS sentences (App.jsx drainTTSQueue).

import { getAudioContext } from "./audioContext";

function base64ToArrayBuffer(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

// Plays a decoded ArrayBuffer; resolves when playback ends. Callbacks let the
// caller drive UI state and surface decode/playback errors.
async function playArrayBuffer(arrayBuffer, { onStart, onError } = {}) {
  const ctx = await getAudioContext();

  let decoded;
  try {
    decoded = await ctx.decodeAudioData(arrayBuffer);
  } catch (err) {
    onError?.("decode", err);
    return;
  }

  const source = ctx.createBufferSource();
  source.buffer = decoded;
  source.connect(ctx.destination);
  onStart?.();

  return new Promise((resolve) => {
    source.onended = resolve;
    source.onerror = (err) => {
      onError?.("playback", err);
      resolve();
    };
    source.start(0);
  });
}

export async function playBlob(blob, handlers) {
  const arrayBuffer = await blob.arrayBuffer();
  return playArrayBuffer(arrayBuffer, handlers);
}

export async function playBase64(b64, handlers) {
  return playArrayBuffer(base64ToArrayBuffer(b64), handlers);
}

// Serial queue for streamed TTS — push sentence audio fetchers, they play in
// order without overlapping. `fetchAndPlay` is supplied by the caller (it knows
// how to hit the TTS endpoint and play the blob).
export function createPlaybackQueue(fetchAndPlay) {
  const queue = [];
  let playing = false;

  async function drain() {
    if (playing) return;
    playing = true;
    while (queue.length > 0) {
      await fetchAndPlay(queue.shift());
    }
    playing = false;
  }

  return {
    enqueue(item) {
      queue.push(item);
      drain();
    },
  };
}
