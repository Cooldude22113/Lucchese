// Voice error line (Rule 15/19). From Voice.jsx — audio/network error message.
export default function VoiceError({ error }) {
  if (!error) return null;
  return (
    <p style={{
      marginTop: "1rem", maxWidth: 280, textAlign: "center",
      fontSize: "clamp(0.7rem, 1.5vw, 0.78rem)", color: "#e06c75", lineHeight: 1.6, padding: "0 1rem",
    }}>⚠ {error}</p>
  );
}
