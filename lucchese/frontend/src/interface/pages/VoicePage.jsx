// Voice screen (Rule 19/20). From Voice.jsx — full-screen orb driven by useVoice.
import VoiceOrb from "../components/voice/VoiceOrb";
import VoiceTranscript from "../components/voice/VoiceTranscript";
import VoiceReply from "../components/voice/VoiceReply";
import VoiceError from "../components/voice/VoiceError";
import { useVoice } from "../../state/hooks/useVoice";

export default function VoicePage() {
  const { state, amplitude, transcript, reply, audioError, handleTap } = useVoice();

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#0a0a0a",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      fontFamily: "'DM Sans', sans-serif", userSelect: "none", padding: "1rem",
    }}>
      <a href="/chat" style={{
        position: "absolute", top: "1.5rem", left: "1.5rem",
        color: "#333", fontSize: "0.75rem", letterSpacing: 2,
        textDecoration: "none", textTransform: "uppercase",
      }}>← Chat</a>

      <p style={{
        position: "absolute", top: "1.5rem",
        fontFamily: "'Playfair Display', serif", fontSize: "clamp(0.8rem, 2vw, 1rem)", letterSpacing: 3,
        background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
      }}>LUCCHESE</p>

      <VoiceOrb state={state} amplitude={amplitude} onTap={handleTap} />
      <VoiceError error={audioError} />
      <VoiceTranscript transcript={transcript} />
      <VoiceReply reply={reply} state={state} />
    </div>
  );
}
