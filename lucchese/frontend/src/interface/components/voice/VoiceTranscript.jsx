// Voice transcript line (Rule 19/20). From Voice.jsx — the user's transcribed text.
export default function VoiceTranscript({ transcript }) {
  if (!transcript) return null;
  return (
    <p style={{
      marginTop: "clamp(0.75rem, 2vh, 1.5rem)", maxWidth: 280, textAlign: "center",
      fontSize: "clamp(0.75rem, 1.5vw, 0.82rem)", color: "#555", lineHeight: 1.6, padding: "0 1rem",
    }}>"{transcript}"</p>
  );
}
