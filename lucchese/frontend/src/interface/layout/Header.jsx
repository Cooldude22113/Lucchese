// Chat top bar (Rule 19/20). From App.jsx — sidebar toggle, current title and
// the ONLINE indicator.
export default function Header({ title, onToggleSidebar }) {
  return (
    <div style={{ padding: "1rem 1.5rem", borderBottom: "1px solid #1a1a1a", display: "flex", alignItems: "center", gap: 12 }}>
      <button onClick={onToggleSidebar} style={{ color: "#555", padding: 4 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <span style={{ fontSize: "0.75rem", color: "#444", letterSpacing: 2, textTransform: "uppercase" }}>
        {title}
      </span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4caf7d", boxShadow: "0 0 6px #4caf7d88" }} />
        <span style={{ fontSize: "0.72rem", color: "#555", letterSpacing: 1 }}>ONLINE</span>
      </div>
    </div>
  );
}
