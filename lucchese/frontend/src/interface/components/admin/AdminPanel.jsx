// Admin panel body (Rule 19/20). Assembles the admin/memory sections from
// AdminPanel.jsx around the useAdmin hook. AdminPage wraps this with PageHeader.
import CollectionCard from "../memory/CollectionCard";
import RecentMemory from "../memory/RecentMemory";
import AdminStats from "./AdminStats";
import AdminTabs from "./AdminTabs";
import { SearchBar, SearchResults } from "./AdminSearch";
import { SummariesList, RebuildSummaries } from "./AdminSummaries";
import AdminDangerZone from "./AdminDangerZone";
import { useAdmin } from "../../../state/hooks/useAdmin";

export default function AdminPanel() {
  const a = useAdmin();

  return (
    <>
      <AdminStats stats={a.stats} totalEntries={a.totalEntries} />

      <AdminTabs activeTab={a.activeTab} onChange={a.setActiveTab} />

      <SearchBar search={a.search} setSearch={a.setSearch} onSearch={a.doSearch} searching={a.searching} />

      {a.loading && (
        <p style={{ color: "#444", fontSize: "0.85rem", textAlign: "center", padding: "3rem" }}>
          Loading memory data...
        </p>
      )}

      {a.activeTab === "overview" && a.stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem" }}>
          {Object.entries(a.stats).map(([name, data]) => (
            <CollectionCard key={name} name={name} data={data} />
          ))}
        </div>
      )}

      {a.activeTab === "recent" && (
        <div style={{ background: "#0f0f0f", border: "1px solid #1e1e1e", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "1rem 1.2rem", borderBottom: "1px solid #1a1a1a" }}>
            <p style={{ fontSize: "0.8rem", color: "#888" }}>Last 30 ingested facts</p>
          </div>
          {a.recent.length === 0 ? (
            <p style={{ padding: "2rem", color: "#444", fontSize: "0.8rem", textAlign: "center" }}>Nothing yet</p>
          ) : (
            a.recent.map((item, i) => <RecentMemory key={i} item={item} />)
          )}
        </div>
      )}

      {a.activeTab === "search" && <SearchResults results={a.results} search={a.search} />}

      {a.activeTab === "summaries" && (
        <SummariesList summaries={a.summaries} onGoToManage={() => a.setActiveTab("manage")} />
      )}

      {a.activeTab === "manage" && a.stats && (
        <>
          <RebuildSummaries summarising={a.summarising} summariseResult={a.summariseResult} onRebuild={a.summarise} />
          <AdminDangerZone stats={a.stats} deleting={a.deleting} onDelete={a.deleteSource} />
        </>
      )}
    </>
  );
}
