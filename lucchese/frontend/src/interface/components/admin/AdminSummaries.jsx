// Memory summaries (Rule 19/20). From AdminPanel.jsx "summaries" tab list and
// the "Rebuild Summaries" action used in the "manage" tab.
import { categoryColor } from "../../../utils/memoryTags";
import { formatFullDate } from "../../../utils/dates";

// The list of generated summaries (summaries tab).
export function SummariesList({ summaries, onGoToManage }) {
  if (summaries.length === 0) {
    return (
      <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, padding: "2.5rem" }}>
        <p style={{ fontSize: "0.8rem", color: "#444", textAlign: "center" }}>
          No summaries yet — go to{" "}
          <span style={{ color: "#c8a96e", cursor: "pointer" }} onClick={onGoToManage}>
            Manage → Rebuild Summaries
          </span>
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {summaries.map((item, i) => {
        const catColor = categoryColor(item.category);
        const date = item.last_updated ? formatFullDate(item.last_updated) : null;
        return (
          <div key={i} style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, padding: "1.2rem 1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.8rem" }}>
              <span style={{ fontSize: "0.62rem", padding: "2px 6px", borderRadius: 4, background: `${catColor}22`, color: catColor, border: `1px solid ${catColor}44`, textTransform: "capitalize" }}>{item.category}</span>
              {date && <span style={{ fontSize: "0.65rem", color: "#444" }}>Generated {date}</span>}
            </div>
            <p style={{ fontSize: "0.82rem", color: "#ccc", lineHeight: 1.6 }}>{item.summary}</p>
            {item.entry_count && <p style={{ fontSize: "0.65rem", color: "#444", marginTop: "0.6rem" }}>{item.entry_count} entries</p>}
          </div>
        );
      })}
    </div>
  );
}

// The "Rebuild Summaries" panel (manage tab).
export function RebuildSummaries({ summarising, summariseResult, onRebuild }) {
  return (
    <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, padding: "1.2rem 1.5rem", marginBottom: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.6rem" }}>
        <div>
          <p style={{ fontSize: "0.85rem", color: "#e8e0d0", textAlign: "left" }}>Memory Summaries</p>
          <p style={{ fontSize: "0.72rem", color: "#555", marginTop: 2 }}>
            Synthesises your memory clusters into coherent summaries by category
          </p>
        </div>
        <button
          onClick={onRebuild}
          disabled={summarising}
          style={{
            padding: "0.5rem 1.2rem",
            background: summarising ? "#1a1a1a" : "linear-gradient(135deg, #c8a96e, #8b6914)",
            border: "none", borderRadius: 8,
            color: summarising ? "#555" : "#0a0a0a",
            fontSize: "0.78rem", fontWeight: 600,
            cursor: summarising ? "not-allowed" : "pointer", whiteSpace: "nowrap",
          }}
        >
          {summarising ? "Building... (takes 1-2 min)" : "Rebuild Summaries"}
        </button>
      </div>
      {summariseResult && !summariseResult.error && (
        <div style={{ marginTop: "0.8rem", fontSize: "0.72rem", color: "#555" }}>
          ✓ {summariseResult.total_categories} categories processed
        </div>
      )}
      {summariseResult?.error && (
        <p style={{ marginTop: "0.8rem", fontSize: "0.72rem", color: "#e06c75" }}>{summariseResult.error}</p>
      )}
    </div>
  );
}
