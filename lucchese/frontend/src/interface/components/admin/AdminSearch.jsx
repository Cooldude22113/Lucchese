// Memory search bar + results (Rule 19/20). From AdminPanel.jsx search bar and
// the "search" tab results list.
import { categoryColor, sourceColor } from "../../../utils/memoryTags";
import { formatFullDate } from "../../../utils/dates";

export function SearchBar({ search, setSearch, onSearch, searching }) {
  return (
    <div style={{
      display: "flex", gap: 8, marginBottom: "1.5rem",
      background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 10, padding: "0.6rem 1rem",
    }}>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSearch()}
        placeholder="Search memory..."
        style={{ flex: 1, fontSize: "0.85rem" }}
      />
      <button onClick={onSearch} disabled={searching} style={{
        padding: "0.35rem 0.8rem", background: "linear-gradient(135deg, #c8a96e, #8b6914)",
        borderRadius: 7, fontSize: "0.75rem", color: "#0a0a0a", fontWeight: 600, opacity: searching ? 0.5 : 1,
      }}>
        {searching ? "..." : "Search"}
      </button>
    </div>
  );
}

export function SearchResults({ results, search }) {
  return (
    <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, overflow: "hidden" }}>
      <div style={{ padding: "1rem 1.2rem", borderBottom: "1px solid #1a1a1a" }}>
        <p style={{ fontSize: "0.8rem", color: "#888" }}>
          {results.length > 0 ? `${results.length} results for "${search}"` : "Run a search above"}
        </p>
      </div>
      {results.map((item, i) => {
        const src = sourceColor(item.source);
        const cat = categoryColor(item.category);
        return (
          <div key={i} style={{ padding: "0.8rem 1rem", borderBottom: "1px solid #141414" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <div style={{ display: "flex", gap: 6 }}>
                <span style={{ fontSize: "0.62rem", padding: "2px 6px", borderRadius: 4, background: `${src}22`, color: src, border: `1px solid ${src}44` }}>{item.source}</span>
                <span style={{ fontSize: "0.62rem", padding: "2px 6px", borderRadius: 4, background: `${cat}22`, color: cat, border: `1px solid ${cat}44` }}>{item.category}</span>
              </div>
              <span style={{ fontSize: "0.65rem", color: "#c8a96e" }}>{(item.relevance * 100).toFixed(0)}% match</span>
            </div>
            <p style={{ fontSize: "0.8rem", color: "#bbb", lineHeight: 1.5 }}>{item.text}</p>
            {item.created_at && (
              <p style={{ fontSize: "0.65rem", color: "#444", marginTop: 4 }}>{formatFullDate(item.created_at)}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
