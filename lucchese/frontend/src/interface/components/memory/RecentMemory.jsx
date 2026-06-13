// Recent memory row (Rule 19/20). From AdminPanel.jsx RecentMemory.
import { categoryColor, sourceColor } from "../../../utils/memoryTags";
import { formatFullDate } from "../../../utils/dates";

export default function RecentMemory({ item }) {
  const catColor = categoryColor(item.category);
  const srcColor = sourceColor(item.source);
  const date = item.created_at ? formatFullDate(item.created_at) : "No date";

  return (
    <div style={{ padding: "0.8rem 1rem", borderBottom: "1px solid #141414", display: "flex", gap: 10, alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: "0.8rem", color: "#ccc", lineHeight: 1.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.text}</p>
        <div style={{ display: "flex", gap: 6, marginTop: 5, alignItems: "center" }}>
          <span style={{ fontSize: "0.62rem", padding: "2px 6px", borderRadius: 4, background: `${srcColor}22`, color: srcColor, border: `1px solid ${srcColor}44` }}>{item.source}</span>
          <span style={{ fontSize: "0.62rem", padding: "2px 6px", borderRadius: 4, background: `${catColor}22`, color: catColor, border: `1px solid ${catColor}44` }}>{item.category}</span>
          <span style={{ fontSize: "0.62rem", color: "#444" }}>{date}</span>
        </div>
      </div>
    </div>
  );
}
