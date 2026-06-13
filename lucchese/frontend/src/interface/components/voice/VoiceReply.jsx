// Voice reply line (Rule 19/20). From Voice.jsx — the assistant's text reply,
// hidden while thinking.
export default function VoiceReply({ reply, state }) {
  if (!reply || state === "thinking") return null;
  return (
    <p style={{
      marginTop: "clamp(0.5rem, 1vh, 0.75rem)", maxWidth: 300, textAlign: "center",
      fontSize: "clamp(0.7rem, 1.5vw, 0.78rem)", color: "#888", lineHeight: 1.6, padding: "0 1rem",
    }}>{reply}</p>
  );
}
