// Uploaded-document list rows (Rule 19/20). From App.jsx DocumentsPanel list.
import { formatFullDate } from "../../../utils/dates";
import EmptyState from "../common/EmptyState";

export default function DocumentList({ documents, onDelete }) {
  if (documents.length === 0) {
    return <EmptyState style={{ padding: "1rem 0" }}>No documents uploaded yet</EmptyState>;
  }

  return (
    <>
      {documents.map((doc) => (
        <div key={doc.id} style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "0.7rem 0", borderBottom: "1px solid #161616",
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6,
            background: "#1a1a1a", border: "1px solid #222",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c8a96e" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: "0.82rem", color: "#ccc", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {doc.filename}
            </p>
            <p style={{ fontSize: "0.7rem", color: "#444", marginTop: 2 }}>
              {doc.chunk_count} chunks · {formatFullDate(doc.created_at)}
            </p>
          </div>
          <button onClick={() => onDelete(doc.id)} style={{ color: "#444", padding: 4, flexShrink: 0 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14H6L5 6"/>
            </svg>
          </button>
        </div>
      ))}
    </>
  );
}
