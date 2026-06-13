// Microphone recording mechanics (Rule 13/19: browser audio mechanics).
// Shared by App.jsx toggleRecording (chat dictation) and Voice.jsx
// startListening/stopListening. Network calls are the caller's job — this only
// owns getUserMedia + MediaRecorder + blob assembly.

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "",
];

export function pickMimeType() {
  return MIME_CANDIDATES.find(
    (m) => m === "" || MediaRecorder.isTypeSupported(m)
  );
}

export function extForMime(mimeType) {
  if (!mimeType) return "webm";
  if (mimeType.includes("mp4")) return "mp4";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

// Starts recording. Returns a handle exposing the stream, the recorder, and a
// stop() that resolves with the recorded Blob (and its extension).
export async function startRecording({ onStream } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  if (onStream) onStream(stream);

  const mimeType = pickMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
  const chunks = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  const stopped = new Promise((resolve) => {
    recorder.onstop = () => {
      const type = recorder.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type });
      resolve({ blob, ext: extForMime(type) });
    };
  });

  recorder.start();

  const stop = () => {
    if (recorder.state === "recording") recorder.stop();
    stream.getTracks().forEach((t) => t.stop());
    return stopped;
  };

  return { stream, recorder, stop, stopped };
}
