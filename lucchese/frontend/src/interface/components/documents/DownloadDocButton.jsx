// Generate-and-download a Word doc (Rule 19/20). From App.jsx DownloadDocButton.
// Network calls go through documentApi.
import { useState } from "react";
import { generateDoc, docDownloadUrl } from "../../../api/documentApi";
import Loader from "../common/Loader";

export default function DownloadDocButton({ content, title }) {
  const [status, setStatus] = useState("idle"); // idle | loading | ready | error
  const [token, setToken] = useState(null);
  const [filename, setFilename] = useState(null);

  const generate = async () => {
    setStatus("loading");
    try {
      const data = await generateDoc({ content, title });
      if (data.error) throw new Error(data.error);
      setToken(data.token);
      setFilename(data.filename);
      setStatus("ready");
    } catch (e) {
      console.error("Doc generation error:", e);
      setStatus("error");
    }
  };

  const download = () => {
    window.open(docDownloadUrl(token), "_blank");
  };

  if (status === "idle") return (
    <button
      onClick={generate}
      style={{
        display: "flex", alignItems: "center", gap: 6, marginTop: 10,
        padding: "0.45rem 1rem", borderRadius: 8,
        background: "linear-gradient(135deg, #c8a96e22, #c8a96e11)",
        border: "1px solid #c8a96e55", color: "#c8a96e",
        fontSize: "0.78rem", fontWeight: 500, cursor: "pointer", transition: "opacity 0.2s",
      }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      Save as Word Doc
    </button>
  );

  if (status === "loading") return (
    <div style={{ marginTop: 10 }}>
      <Loader label="Generating document..." />
    </div>
  );

  if (status === "error") return (
    <div style={{ marginTop: 10, fontSize: "0.75rem", color: "#e06c75" }}>
      ✗ Failed to generate document
    </div>
  );

  return (
    <button
      onClick={download}
      style={{
        display: "flex", alignItems: "center", gap: 6, marginTop: 10,
        padding: "0.45rem 1rem", borderRadius: 8,
        background: "linear-gradient(135deg, #c8a96e, #8b6914)",
        border: "none", color: "#0a0a0a",
        fontSize: "0.78rem", fontWeight: 600, cursor: "pointer",
      }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      Download {filename}
    </button>
  );
}
