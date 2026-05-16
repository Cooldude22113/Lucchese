import { useState, useRef } from "react";

const API = "https://api.lucchese.app";

const STATE = {
  IDLE:      "idle",
  LISTENING: "listening",
  THINKING:  "thinking",
  SPEAKING:  "speaking",
};

const COLORS = {
  idle:      ["#1a1a1a", "#2a2a2a"],
  listening: ["#c8a96e", "#8b6914"],
  thinking:  ["#4a4a6a", "#2a2a4a"],
  speaking:  ["#c8a96e", "#e8d5a3"],
};

const LABELS = {
  idle:      "tap to speak",
  listening: "listening...",
  thinking:  "thinking...",
  speaking:  "speaking...",
};

export default function Voice() {
  const [state, setState]           = useState(STATE.IDLE);
  const [amplitude, setAmplitude]   = useState(0);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply]           = useState("");
  const [convId, setConvId]         = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef   = useRef([]);
  const streamRef        = useRef(null);
  const analyserRef      = useRef(null);
  const animFrameRef     = useRef(null);
  const audioCtxRef      = useRef(null);
  const silenceTimerRef  = useRef(null);
  const frameRef         = useRef(null);

  // ── Simulated pulse ─────────────────────────────────────────────────────────
  const startPulse = () => {
    let t = 0;
    const tick = () => {
      t += 0.08;
      setAmplitude(18 + Math.sin(t) * 12 + Math.sin(t * 2.3) * 6);
      frameRef.current = requestAnimationFrame(tick);
    };
    tick();
  };

  const stopPulse = () => {
    if (frameRef.current) cancelAnimationFrame(frameRef.current);
    setAmplitude(0);
  };

  // ── Real mic amplitude ──────────────────────────────────────────────────────
  const startAmplitudeLoop = (analyser) => {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += Math.abs(data[i] - 128);
      setAmplitude(sum / data.length);
      animFrameRef.current = requestAnimationFrame(tick);
    };
    tick();
  };

  const stopAmplitudeLoop = () => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    setAmplitude(0);
  };

  // ── Recording ───────────────────────────────────────────────────────────────
  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtxRef.current = ctx;
      const source   = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;
      startAmplitudeLoop(analyser);

      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", ""].find(
        m => m === "" || MediaRecorder.isTypeSupported(m)
      );
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = recorder;
      audioChunksRef.current   = [];

      recorder.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = handleRecordingStop;
      recorder.start();
      setState(STATE.LISTENING);

      // Auto-stop after 8s
      silenceTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current?.state === "recording") stopListening();
      }, 8000);

    } catch (err) {
      console.error("Mic error:", err);
      alert("Microphone access denied.");
    }
  };

  const stopListening = () => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    mediaRecorderRef.current?.stop();
    streamRef.current?.getTracks().forEach(t => t.stop());
    stopAmplitudeLoop();
    audioCtxRef.current?.close();
    setState(STATE.THINKING);
  };

  // ── Send to backend ─────────────────────────────────────────────────────────
  const handleRecordingStop = async () => {
    const mimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
    const blob = new Blob(audioChunksRef.current, { type: mimeType });
    const ext  = mimeType.includes("mp4") ? "mp4" : mimeType.includes("ogg") ? "ogg" : "webm";

    const form = new FormData();
    form.append("file", blob, `recording.${ext}`);
    if (convId) form.append("conversation_id", convId);

    try {
      const res = await fetch(`${API}/voice-chat`, { method: "POST", body: form });
      if (!res.ok) { setState(STATE.IDLE); return; }

      const data = await res.json();
        console.log("Response:", JSON.stringify({
          transcript: data.transcript,
          reply: data.reply?.slice(0, 50),
          audio_b64_length: data.audio_b64?.length,
          has_error: data.error,
        }));
      setTranscript(data.transcript || "");
      setReply(data.reply || "");
      if (data.conv_id) setConvId(data.conv_id);

      if (data.audio_b64) {
        playBase64Audio(data.audio_b64);
      } else {
        setState(STATE.IDLE);
      }

    } catch (err) {
      console.error("Voice chat error:", err);
      setState(STATE.IDLE);
    }
  };

  // ── Play base64 audio ───────────────────────────────────────────────────────
  const playBase64Audio = (b64) => {
    setState(STATE.SPEAKING);
    try {
      const binary = atob(b64);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob   = new Blob([bytes], { type: "audio/mpeg" });
      const url    = URL.createObjectURL(blob);
      const audio  = new Audio(url);

      startPulse();

      audio.onended = () => {
        stopPulse();
        URL.revokeObjectURL(url);
        setState(STATE.IDLE);
      };

      audio.onerror = () => {
        stopPulse();
        URL.revokeObjectURL(url);
        setState(STATE.IDLE);
      };

      audio.play().catch(err => {
        console.error("Play error:", err);
        stopPulse();
        setState(STATE.IDLE);
      });

    } catch (err) {
      console.error("Base64 decode error:", err);
      setState(STATE.IDLE);
    }
  };

  // ── Tap handler ─────────────────────────────────────────────────────────────
  const handleTap = () => {
    if (state === STATE.IDLE)           startListening();
    else if (state === STATE.LISTENING) stopListening();
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  const pulse     = 1 + (amplitude / 128) * 0.4;
  const [c1, c2]  = COLORS[state];
  const glowColor = state === STATE.IDLE ? "transparent" : c1;

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#0a0a0a",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      fontFamily: "'DM Sans', sans-serif", userSelect: "none",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400&family=DM+Sans:wght@300;400&display=swap');
        @keyframes breathe { 0%,100%{opacity:0.6} 50%{opacity:1} }
      `}</style>

      <a href="/chat" style={{
        position: "absolute", top: "1.5rem", left: "1.5rem",
        color: "#333", fontSize: "0.75rem", letterSpacing: 2,
        textDecoration: "none", textTransform: "uppercase",
      }}>← Chat</a>

      <p style={{
        position: "absolute", top: "1.5rem",
        fontFamily: "'Playfair Display', serif", fontSize: "1rem", letterSpacing: 3,
        background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
      }}>LUCCHESE</p>

      <div style={{
        width: 260, height: 260, borderRadius: "50%",
        background: `radial-gradient(circle, ${glowColor}22 0%, transparent 70%)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        transition: "background 0.4s ease",
      }}>
        <div onClick={handleTap} style={{
          width: 180, height: 180, borderRadius: "50%",
          background: `radial-gradient(circle at 35% 35%, ${c1}, ${c2})`,
          boxShadow: state !== STATE.IDLE
            ? `0 0 40px ${c1}66, 0 0 80px ${c1}22`
            : "0 0 20px #00000088",
          transform: `scale(${pulse})`,
          transition: state === STATE.IDLE
            ? "transform 0.3s ease, background 0.4s ease, box-shadow 0.4s ease"
            : "background 0.4s ease, box-shadow 0.4s ease",
          cursor: state === STATE.THINKING || state === STATE.SPEAKING ? "default" : "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {state === STATE.IDLE && (
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#c8a96e" strokeWidth="1.5">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          )}
        </div>
      </div>

      <p style={{
        marginTop: "2rem", fontSize: "0.7rem", letterSpacing: 3,
        color: state === STATE.IDLE ? "#333" : "#888",
        textTransform: "uppercase",
        animation: state === STATE.THINKING ? "breathe 1.2s ease infinite" : "none",
      }}>
        {LABELS[state]}
      </p>

      {transcript && (
        <p style={{
          marginTop: "1.5rem", maxWidth: 280, textAlign: "center",
          fontSize: "0.82rem", color: "#555", lineHeight: 1.6, padding: "0 1rem",
        }}>"{transcript}"</p>
      )}

      {reply && state !== STATE.THINKING && (
        <p style={{
          marginTop: "0.75rem", maxWidth: 300, textAlign: "center",
          fontSize: "0.78rem", color: "#888", lineHeight: 1.6, padding: "0 1rem",
        }}>{reply}</p>
      )}
    </div>
  );
}
