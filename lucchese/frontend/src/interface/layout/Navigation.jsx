// Top navigation (Rule 19/20). From Home.jsx NavLink + the nav bar that hosts it.
import { gold } from "../../utils/theme";

function NavLink({ href, label, active }) {
  return (
    <a href={href} style={{
      fontSize: "0.72rem", color: active ? gold : "#555", textDecoration: "none",
      letterSpacing: 1.5, textTransform: "uppercase",
      borderBottom: active ? `1px solid ${gold}` : "1px solid transparent",
      paddingBottom: 2, transition: "color 0.2s",
    }}>{label}</a>
  );
}

export default function Navigation({ active }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      marginBottom: "3rem", paddingBottom: "1.2rem", borderBottom: `1px solid #1e1e1e`,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
        <span style={{
          fontFamily: "'Playfair Display', serif", fontSize: "1.1rem",
          background: `linear-gradient(135deg, ${gold}, #e8d5a3)`,
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
        }}>Lucchese</span>
        <span style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase" }}>Personal AI</span>
      </div>
      <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
        <NavLink href="/" label="Home" active={active === "home"} />
        <NavLink href="/chat" label="Chat" active={active === "chat"} />
        <NavLink href="/admin" label="Admin" active={active === "admin"} />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4caf7d", animation: "pulse 2s ease infinite" }} />
          <span style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 1 }}>ONLINE</span>
        </div>
      </div>
    </div>
  );
}
