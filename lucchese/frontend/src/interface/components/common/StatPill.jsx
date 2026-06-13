// Stat pill (Rule 19/20). From Home.jsx StatPill.
import { gold, border } from "../../../utils/theme";

export default function StatPill({ label, value, color }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "0.8rem 1.2rem",
      background: "#111",
      border: `1px solid ${border}`,
      borderRadius: 10,
      minWidth: 80,
    }}>
      <span style={{ fontSize: "1.4rem", fontFamily: "'Playfair Display', serif", color: color || gold }}>{value}</span>
      <span style={{ fontSize: "0.62rem", color: "#444", marginTop: 4, textTransform: "uppercase", letterSpacing: 1 }}>{label}</span>
    </div>
  );
}
