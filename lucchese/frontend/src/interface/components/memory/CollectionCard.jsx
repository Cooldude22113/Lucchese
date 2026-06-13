// Memory collection card (Rule 19/20). From AdminPanel.jsx CollectionCard —
// per-collection totals with source/category breakdown bars.
import { useState } from "react";
import StatBar from "../common/StatBar";
import { SOURCE_COLORS, CATEGORY_COLORS } from "../../../utils/memoryTags";

export default function CollectionCard({ name, data }) {
  const [tab, setTab] = useState("source");
  const counts = tab === "source" ? data.by_source : data.by_category;
  const colors = tab === "source" ? SOURCE_COLORS : CATEGORY_COLORS;

  return (
    <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, padding: "1.2rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <div>
          <p style={{ fontFamily: "'Playfair Display', serif", fontSize: "0.9rem", color: "#e8e0d0", textTransform: "capitalize" }}>{name}</p>
          <p style={{ fontSize: "0.7rem", color: "#555", marginTop: 2 }}>{data.total.toLocaleString()} entries</p>
        </div>
        <div style={{
          width: 44, height: 44, borderRadius: "50%",
          background: "linear-gradient(135deg, #c8a96e22, #c8a96e11)",
          border: "1px solid #c8a96e33",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "0.85rem", fontWeight: 700, color: "#c8a96e",
          fontFamily: "'Playfair Display', serif",
        }}>
          {data.total > 999 ? `${(data.total / 1000).toFixed(1)}k` : data.total}
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: "1rem" }}>
        {["source", "category"].map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "0.3rem 0.7rem", borderRadius: 6,
            background: tab === t ? "#c8a96e22" : "transparent",
            border: `1px solid ${tab === t ? "#c8a96e44" : "#222"}`,
            color: tab === t ? "#c8a96e" : "#555",
            fontSize: "0.7rem", textTransform: "capitalize", cursor: "pointer",
          }}>{t}</button>
        ))}
      </div>

      {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([key, val]) => (
        <StatBar key={key} label={key} value={val} total={data.total} color={colors[key]} />
      ))}
    </div>
  );
}
