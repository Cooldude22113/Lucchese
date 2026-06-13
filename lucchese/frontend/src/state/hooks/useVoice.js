// Voice page state machine (Rule 19). From Voice.jsx — idle → listening →
// thinking → speaking, orchestrating audio/* mechanics and the /voice-chat API.
import { useState, useRef, useCallback } from "react";
import { voiceChat } from "../../api/voiceApi";
import { getAudioContext } from "../../audio/audioContext";
import { startRecording } from "../../audio/recorder";
import { playBase64 } from "../../audio/playback";
import { createAmplitudeLoop, createPulseLoop } from "../../audio/amplitude";
import { AUDIO_ERRORS } from "../../utils/errors";

export const VOICE_STATE = {
  IDLE: "idle",
  LISTENING: "listening",
  THINKING: "thinking",
  SPEAKING: "speaking",
};

export function useVoice() {
  const [state, setState] = useState(VOICE_STATE.IDLE);
  const [amplitude, setAmplitude] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [audioError, setAudioError] = useState(null);

  const recorderRef = useRef(null);
  const convIdRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const ampLoopRef = useRef(null);
  const pulseLoopRef = useRef(null);

  if (!ampLoopRef.current) ampLoopRef.current = createAmplitudeLoop(setAmplitude);
  if (!pulseLoopRef.current) pulseLoopRef.current = createPulseLoop(setAmplitude);

  // ── Send recorded audio to the backend, then speak the reply ────────────────
  const handleResult = useCallback(async (blob, ext) => {
    try {
      const res = await voiceChat(blob, ext, convIdRef.current);
      if (!res.ok) { setState(VOICE_STATE.IDLE); return; }

      const data = await res.json();
      setTranscript(data.transcript || "");
      setReply(data.reply || "");
      if (data.conv_id) convIdRef.current = data.conv_id;
      setAudioError(null);

      if (data.audio_b64) {
        setState(VOICE_STATE.SPEAKING);
        await playBase64(data.audio_b64, {
          onStart: () => pulseLoopRef.current.start(),
          onError: (kind) =>
            setAudioError(kind === "decode" ? AUDIO_ERRORS.decodeVoice : AUDIO_ERRORS.playbackError),
        });
        pulseLoopRef.current.stop();
        setState(VOICE_STATE.IDLE);
      } else {
        setState(VOICE_STATE.IDLE);
      }
    } catch (err) {
      console.error("Voice chat error:", err);
      setAudioError(AUDIO_ERRORS.network);
      setState(VOICE_STATE.IDLE);
    }
  }, []);

  // ── Recording control ───────────────────────────────────────────────────────
  const startListening = useCallback(async () => {
    try {
      setAudioError(null);
      // Create/resume the AudioContext inside the tap gesture (iOS).
      const ctx = await getAudioContext();

      recorderRef.current = await startRecording({
        onStream: (stream) => {
          const source = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 256;
          source.connect(analyser);
          ampLoopRef.current.start(analyser);
        },
      });
      setState(VOICE_STATE.LISTENING);

      // Auto-stop after 8s.
      silenceTimerRef.current = setTimeout(() => {
        if (recorderRef.current?.recorder.state === "recording") stopListening();
      }, 8000);
    } catch (err) {
      console.error("Mic error:", err);
      setAudioError(AUDIO_ERRORS.micDenied);
    }
  }, []);

  const stopListening = useCallback(async () => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    ampLoopRef.current.stop();
    setState(VOICE_STATE.THINKING);
    const { blob, ext } = await recorderRef.current.stop();
    handleResult(blob, ext);
  }, [handleResult]);

  const handleTap = useCallback(() => {
    if (state === VOICE_STATE.IDLE) startListening();
    else if (state === VOICE_STATE.LISTENING) stopListening();
  }, [state, startListening, stopListening]);

  return { state, amplitude, transcript, reply, audioError, handleTap };
}
