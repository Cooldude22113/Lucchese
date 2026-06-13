// Voice/audio endpoints (Rule 19): transcription, TTS and full voice-chat.
import { postRaw, postForm } from "./client";

// POST /transcribe — speech-to-text for an audio blob. Returns { text }.
export async function transcribe(blob, ext = "webm") {
  const form = new FormData();
  form.append("file", blob, `recording.${ext}`);
  const res = await postForm("/transcribe", form);
  return res.json();
}

// POST /tts — text-to-speech. Returns the raw Response so callers can read the
// audio blob (and check res.ok before decoding).
export function tts(text) {
  return postRaw("/tts", { text });
}

// POST /voice-chat — full round trip (audio in → transcript + reply + audio_b64).
export async function voiceChat(blob, ext = "webm", conversation_id) {
  const form = new FormData();
  form.append("file", blob, `recording.${ext}`);
  if (conversation_id) form.append("conversation_id", conversation_id);
  const res = await postForm("/voice-chat", form);
  return res;
}
