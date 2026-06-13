// Delete-by-source panel (Rule 16/19/20). From AdminPanel.jsx "manage" tab.
import { SOURCE_COLORS } from "../../../utils/memoryTags";

const SOURCES = ["grok", "chatgpt", "lucchese", "explicit", "document"];

export default function AdminDangerZone({ stats, deleting, onDelete }) {
  return (
    <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, overflow: "hidden" }}>
      <div style={{ padding: "1rem 1.2rem", borderBottom: "1px solid #1a1a1a" }}>
        <p style={{ fontSize: "0.8rem", color: "#888" }}>Delete entries by source</p>
        <p style={{ fontSize: "0.7rem", color: "#444", marginTop: 2 }}>This removes from all three collections</p>
      </div>
      {SOURCES.map((src) => {
        const total = Object.values(stats).reduce((sum, col) => sum + (col.by_source[src] || 0), 0);
        return (
          <div key={src} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "0.9rem 1.2rem", borderBottom: "1px solid #141414",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: SOURCE_COLORS[src] || "#666" }} />
              <span style={{ fontSize: "0.82rem", color: "#ccc", textTransform: "capitalize" }}>{src}</span>
              <span style={{ fontSize: "0.72rem", color: "#444" }}>{total.toLocaleString()} entries</span>
            </div>
            <button
              onClick={() => onDelete(src)}
              disabled={deleting === src || total === 0}
              style={{
                padding: "0.35rem 0.8rem", borderRadius: 7,
                background: total > 0 ? "#e06c7511" : "transparent",
                border: `1px solid ${total > 0 ? "#e06c7544" : "#222"}`,
                color: total > 0 ? "#e06c75" : "#333",
                fontSize: "0.72rem", opacity: deleting === src ? 0.5 : 1,
              }}
            >
              {deleting === src ? "Deleting..." : "Delete all"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
