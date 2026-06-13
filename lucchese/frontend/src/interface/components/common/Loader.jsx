// Inline spinner (Rule 19/20). The spinning ring from App.jsx DownloadDocButton
// "Generating…" state. Relies on the `spin` keyframe in styles/chat.css.
export default function Loader({ label, size = 10 }) {
  return (
    <div style={{ fontSize: "0.75rem", color: "#555", display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: size, height: size, borderRadius: "50%",
        border: "1.5px solid #c8a96e", borderTopColor: "transparent",
        animation: "spin 0.8s linear infinite",
      }} />
      {label}
    </div>
  );
}
