// Scrolling message list (Rule 19/20). From App.jsx chat message area.
import MessageBubble from "./MessageBubble";
import StreamingMessage from "./StreamingMessage";

export default function MessageList({ messages, loading, lastExchange, bottomRef }) {
  const lastIsAssistant = messages[messages.length - 1]?.role === "assistant";

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "2rem 2rem 1rem", maxWidth: 760, width: "100%", margin: "0 auto", alignSelf: "center", boxSizing: "border-box" }}>
      {messages.length === 0 && (
        <div style={{ textAlign: "center", marginTop: "4rem" }}>
          <p style={{
            fontFamily: "'Playfair Display', serif", fontSize: "1.8rem",
            background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
            marginBottom: "0.5rem",
          }}>Lucchese</p>
          <p style={{ color: "#444", fontSize: "0.85rem" }}>Select a conversation or start a new one</p>
        </div>
      )}
      {messages.map((m, i) => {
        const isLatest = i === messages.length - 1 && m.role === "assistant";
        return (
          <MessageBubble
            key={i}
            {...m}
            isLatest={isLatest}
            exchange={isLatest ? lastExchange : null}
          />
        );
      })}
      {loading && !lastIsAssistant && <StreamingMessage />}
      <div ref={bottomRef} />
    </div>
  );
}
