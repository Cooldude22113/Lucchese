// Chat conversation sidebar (Rule 19/20). From App.jsx sidebar — brand, new
// conversation, conversation list and the Documents button.
import { formatShortDate } from "../../utils/dates";
import EmptyState from "../components/common/EmptyState";

export default function Sidebar({ conversations, activeId, onLoad, onNew, onDelete, onOpenDocs }) {
  return (
    <div style={{
      width: 240, background: "#0d0d0d", borderRight: "1px solid #1a1a1a",
      display: "flex", flexDirection: "column", flexShrink: 0,
    }}>
      <div style={{ padding: "1.2rem 1rem 0.8rem", borderBottom: "1px solid #1a1a1a" }}>
        <a href="/" style={{ textDecoration: "none" }}>
          <p style={{
            fontFamily: "'Playfair Display', serif", fontSize: "1rem",
            background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
            marginBottom: "0.8rem",
          }}>Lucchese</p>
        </a>
        <button onClick={onNew} style={{
          width: "100%", padding: "0.55rem 0.8rem", background: "#161616",
          border: "1px solid #2a2a2a", borderRadius: 8, color: "#888", fontSize: "0.8rem",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          New conversation
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
        {conversations.length === 0 && (
          <EmptyState style={{ fontSize: "0.75rem", padding: "1rem" }}>No conversations yet</EmptyState>
        )}
        {conversations.map((conv) => (
          <div key={conv.id}
            className={`conv-item${activeId === conv.id ? " active" : ""}`}
            onClick={() => onLoad(conv.id)}
            style={{
              padding: "0.65rem 1rem", cursor: "pointer", borderLeft: "2px solid transparent",
              display: "flex", alignItems: "center", gap: 8, transition: "background 0.15s",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: "0.78rem", color: "#bbb", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {conv.title || "Untitled"}
              </p>
              <p style={{ fontSize: "0.68rem", color: "#444", marginTop: 2 }}>{formatShortDate(conv.updated_at)}</p>
            </div>
            <button className="del-btn" onClick={(e) => onDelete(e, conv.id)} style={{ color: "#555", padding: 2, flexShrink: 0 }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
            </button>
          </div>
        ))}
      </div>

      <div style={{ padding: "0.8rem 1rem", borderTop: "1px solid #1a1a1a" }}>
        <button onClick={onOpenDocs} style={{
          width: "100%", padding: "0.55rem 0.8rem", background: "#161616",
          border: "1px solid #2a2a2a", borderRadius: 8, color: "#888", fontSize: "0.8rem",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          Documents
        </button>
      </div>
    </div>
  );
}
