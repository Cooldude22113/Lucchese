// Typing indicator (Rule 19/20). From App.jsx TypingIndicator — shown while the
// assistant reply is still streaming. Uses the `pulse` keyframe in chat.css.
export default function StreamingMessage() {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: "1.5rem" }}>
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        background: "linear-gradient(135deg, #c8a96e, #8b6914)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, fontWeight: 700, color: "#0a0a0a",
        marginRight: 10, flexShrink: 0,
        fontFamily: "'Playfair Display', serif",
      }}>L</div>
      <div style={{
        padding: "0.85rem 1.2rem", borderRadius: "18px 18px 18px 4px",
        background: "#141414", border: "1px solid #222",
        display: "flex", gap: 5, alignItems: "center",
      }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: "50%", background: "#c8a96e",
            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}
