// Admin page header (Rule 19/20). From AdminPanel.jsx top header — brand,
// subtitle and a back link.
export default function PageHeader({ subtitle, backHref = "http://localhost:5173", backLabel = "← Back to chat" }) {
  return (
    <div style={{ marginBottom: "2rem", display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
      <div>
        <a href="/" style={{ textDecoration: "none" }}>
          <p style={{
            fontFamily: "'Playfair Display', serif", fontSize: "1rem",
            background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
            marginBottom: "0.8rem",
          }}>Lucchese</p>
        </a>
        {subtitle && (
          <p style={{ fontSize: "0.75rem", color: "#444", letterSpacing: 2, textTransform: "uppercase", marginTop: 2 }}>
            {subtitle}
          </p>
        )}
      </div>
      <a href={backHref} style={{ fontSize: "0.75rem", color: "#555", textDecoration: "none", display: "flex", alignItems: "center", gap: 5 }}>
        {backLabel}
      </a>
    </div>
  );
}
