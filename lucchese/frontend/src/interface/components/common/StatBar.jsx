// Labelled progress bar (Rule 19/20). From AdminPanel.jsx StatBar.
export default function StatBar({ label, value, total, color }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: "0.75rem", color: "#aaa", textTransform: "capitalize" }}>{label}</span>
        <span style={{ fontSize: "0.75rem", color: "#666" }}>{value}</span>
      </div>
      <div style={{ height: 3, background: "#1a1a1a", borderRadius: 2 }}>
        <div style={{
          height: "100%", borderRadius: 2,
          width: `${pct}%`,
          background: color || "#c8a96e",
          transition: "width 0.6s ease",
        }} />
      </div>
    </div>
  );
}
