// Single chat message (Rule 19/20). From App.jsx Message.
import ReactMarkdown from "react-markdown";
import { stripDocMarker } from "../../../utils/docMarker";
import DocumentMarker from "./DocumentMarker";
import MessageActions from "./MessageActions";

export default function MessageBubble({ role, content, isLatest, exchange }) {
  const isUser = role === "user";
  const cleanContent = stripDocMarker(content);

  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: "1.5rem",
      animation: "fadeUp 0.3s ease forwards",
    }}>
      {!isUser && (
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "linear-gradient(135deg, #c8a96e, #8b6914)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700, color: "#0a0a0a",
          marginRight: 10, flexShrink: 0, marginTop: 2,
          fontFamily: "'Playfair Display', serif",
        }}>L</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", maxWidth: "70%" }}>
        <div style={{
          padding: "0.85rem 1.1rem",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "linear-gradient(135deg, #c8a96e22, #c8a96e11)" : "#141414",
          border: isUser ? "1px solid #c8a96e44" : "1px solid #222",
          color: "#e8e0d0", fontSize: "0.92rem", lineHeight: 1.7,
          fontFamily: "'DM Sans', sans-serif", wordBreak: "break-word",
        }}>
          <div className="message-content">
            <ReactMarkdown>{cleanContent}</ReactMarkdown>
          </div>
          {!isUser && <DocumentMarker content={content} />}
        </div>

        {!isUser && isLatest && <MessageActions exchange={exchange} />}
      </div>
    </div>
  );
}
