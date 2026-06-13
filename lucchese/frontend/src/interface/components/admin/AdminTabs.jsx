// Admin tab bar (Rule 19/20). From AdminPanel.jsx tab row.
export const ADMIN_TABS = ["overview", "recent", "search", "summaries", "manage"];

export default function AdminTabs({ activeTab, onChange }) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: "1.5rem" }}>
      {ADMIN_TABS.map((t) => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: "0.45rem 1rem", borderRadius: 8,
          background: activeTab === t ? "#c8a96e22" : "#0f0f0f",
          border: `1px solid ${activeTab === t ? "#c8a96e44" : "#1e1e1e"}`,
          color: activeTab === t ? "#c8a96e" : "#555",
          fontSize: "0.78rem", textTransform: "capitalize",
        }}>{t}</button>
      ))}
    </div>
  );
}
