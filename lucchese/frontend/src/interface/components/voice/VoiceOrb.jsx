// Voice orb (Rule 19/20). From Voice.jsx — the tappable pulsing circle whose
// colour/label reflect the current voice state. Pure presentation; the state
// machine lives in state/hooks/useVoice.
const COLORS = {
  idle: ["#1a1a1a", "#2a2a2a"],
  listening: ["#c8a96e", "#8b6914"],
  thinking: ["#4a4a6a", "#2a2a4a"],
  speaking: ["#c8a96e", "#e8d5a3"],
};

const LABELS = {
  idle: "tap to speak",
  listening: "listening...",
  thinking: "thinking...",
  speaking: "speaking...",
};

export default function VoiceOrb({ state, amplitude, onTap }) {
  const pulse = 1 + (amplitude / 128) * 0.4;
  const [c1, c2] = COLORS[state];
  const glowColor = state === "idle" ? "transparent" : c1;

  return (
    <>
      <div style={{
        width: "clamp(200px, 60vw, 260px)", height: "clamp(200px, 60vw, 260px)", borderRadius: "50%",
        background: `radial-gradient(circle, ${glowColor}22 0%, transparent 70%)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        transition: "background 0.4s ease",
      }}>
        <div onClick={onTap} style={{
          width: "clamp(140px, 45vw, 180px)", height: "clamp(140px, 45vw, 180px)", borderRadius: "50%",
          background: `radial-gradient(circle at 35% 35%, ${c1}, ${c2})`,
          boxShadow: state !== "idle" ? `0 0 40px ${c1}66, 0 0 80px ${c1}22` : "0 0 20px #00000088",
          transform: `scale(${pulse})`,
          transition: state === "idle"
            ? "transform 0.3s ease, background 0.4s ease, box-shadow 0.4s ease"
            : "background 0.4s ease, box-shadow 0.4s ease",
          cursor: state === "thinking" || state === "speaking" ? "default" : "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {state === "idle" && (
            <svg width="clamp(24px, 5vw, 32px)" height="clamp(24px, 5vw, 32px)" viewBox="0 0 24 24" fill="none" stroke="#c8a96e" strokeWidth="1.5">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          )}
        </div>
      </div>

      <p style={{
        marginTop: "clamp(1rem, 4vh, 2rem)", fontSize: "clamp(0.65rem, 1.5vw, 0.7rem)", letterSpacing: 3,
        color: state === "idle" ? "#333" : "#888", textTransform: "uppercase",
        animation: state === "thinking" ? "breathe 1.2s ease infinite" : "none",
      }}>
        {LABELS[state]}
      </p>
    </>
  );
}
