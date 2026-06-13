// Error message helpers (Rule 10/15/22: pure helper).
// The user-facing audio/network error strings used by Chat and Voice, kept in
// one place so the copy stays consistent.

export const AUDIO_ERRORS = {
  decode: "Failed to decode audio format.",
  decodeVoice: "Failed to decode audio. Unsupported format.",
  play: "Failed to play audio. Please check your speakers.",
  playRetry: "Failed to play audio. Please try again.",
  ttsUnavailable: "TTS service unavailable.",
  playbackFailed: "Audio playback failed. Please try again.",
  playbackError: "Audio playback error. Please try again.",
  micDenied: "Microphone access denied. Please allow microphone permissions.",
  network: "Network error. Please try again.",
};
