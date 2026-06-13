// Document upload modal (Rule 19/20). From App.jsx DocumentsPanel — drop zone +
// list inside a Modal. Document state/actions come from useDocuments.
import { useRef, useState } from "react";
import Modal from "../common/Modal";
import DocumentList from "./DocumentList";
import { useDocuments } from "../../../state/hooks/useDocuments";

export default function UploadPanel({ onClose }) {
  const { documents, uploading, uploadMsg, upload, remove } = useDocuments();
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  return (
    <Modal onClose={onClose}>
      {/* Header */}
      <div style={{
        padding: "1.2rem 1.5rem", borderBottom: "1px solid #1a1a1a",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: "1.1rem", color: "#e8e0d0" }}>Documents</h2>
          <p style={{ fontSize: "0.73rem", color: "#555", marginTop: 2 }}>PDFs and text files Lucchese can search</p>
        </div>
        <button onClick={onClose} style={{ color: "#555", padding: 4 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          margin: "1.2rem 1.5rem",
          border: `2px dashed ${dragOver ? "#c8a96e" : "#2a2a2a"}`,
          borderRadius: 10, padding: "1.5rem", textAlign: "center", cursor: "pointer",
          transition: "border-color 0.2s", background: dragOver ? "#c8a96e08" : "transparent",
        }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.5" style={{ marginBottom: 8 }}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <p style={{ color: "#555", fontSize: "0.82rem" }}>
          {uploading ? "Ingesting..." : "Drop a file or click to upload"}
        </p>
        <p style={{ color: "#333", fontSize: "0.72rem", marginTop: 4 }}>PDF, TXT, MD supported</p>
        {uploadMsg && (
          <p style={{ color: uploadMsg.startsWith("✓") ? "#4caf7d" : "#e06c75", fontSize: "0.78rem", marginTop: 8 }}>
            {uploadMsg}
          </p>
        )}
        <input ref={fileRef} type="file" accept=".pdf,.txt,.md" style={{ display: "none" }}
          onChange={(e) => { if (e.target.files[0]) upload(e.target.files[0]); }} />
      </div>

      {/* Document list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 1.5rem 1.5rem" }}>
        <DocumentList documents={documents} onDelete={remove} />
      </div>
    </Modal>
  );
}
