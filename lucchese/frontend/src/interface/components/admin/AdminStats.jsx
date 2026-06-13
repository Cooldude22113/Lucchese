// Memory totals header (Rule 19/20). From AdminPanel.jsx total-stat block.
export default function AdminStats({ stats, totalEntries }) {
  if (!stats) return null;
  return (
    <div style={{
      background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12,
      padding: "1.2rem 1.5rem", marginBottom: "1.5rem",
      display: "flex", gap: "2rem", alignItems: "center",
    }}>
      <div>
        <p style={{ fontSize: "2rem", fontFamily: "'Playfair Display', serif", color: "#c8a96e" }}>
          {totalEntries.toLocaleString()}
        </p>
        <p style={{ fontSize: "0.72rem", color: "#555", marginTop: 2 }}>Total memory entries</p>
      </div>
      {Object.entries(stats).map(([name, data]) => (
        <div key={name} style={{ borderLeft: "1px solid #1a1a1a", paddingLeft: "2rem" }}>
          <p style={{ fontSize: "1.2rem", color: "#e8e0d0", fontFamily: "'Playfair Display', serif" }}>
            {data.total.toLocaleString()}
          </p>
          <p style={{ fontSize: "0.72rem", color: "#555", marginTop: 2, textTransform: "capitalize" }}>{name}</p>
        </div>
      ))}
    </div>
  );
}
