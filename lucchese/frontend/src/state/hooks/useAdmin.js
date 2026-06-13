// Admin/memory state (Rule 19). From AdminPanel.jsx — stats, recent, summaries,
// search, delete-by-source and summary rebuild.
import { useState, useEffect, useCallback } from "react";
import {
  getStats, getRecent, getSummaries, searchMemory,
  deleteBySource, rebuildSummaries,
} from "../../api/adminApi";

export function useAdmin() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [summaries, setSummaries] = useState([]);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [deleting, setDeleting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summarising, setSummarising] = useState(false);
  const [summariseResult, setSummariseResult] = useState(null);

  useEffect(() => {
    Promise.all([getStats(), getRecent(30), getSummaries()])
      .then(([s, r, su]) => {
        setStats(s);
        setRecent(r);
        setSummaries(Array.isArray(su) ? su : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const doSearch = useCallback(async () => {
    if (!search.trim()) return;
    setSearching(true);
    const data = await searchMemory(search, 10);
    setResults(data);
    setSearching(false);
    setActiveTab("search");
  }, [search]);

  const deleteSource = useCallback(async (source) => {
    if (!confirm(`Delete all ${source} entries? This cannot be undone.`)) return;
    setDeleting(source);
    await deleteBySource(source);
    setStats(await getStats());
    setDeleting(null);
  }, []);

  const summarise = useCallback(async () => {
    setSummarising(true);
    setSummariseResult(null);
    try {
      setSummariseResult(await rebuildSummaries());
    } catch {
      setSummariseResult({ error: "Failed to connect" });
    } finally {
      setSummarising(false);
    }
  }, []);

  const totalEntries = stats
    ? Object.values(stats).reduce((sum, col) => sum + col.total, 0)
    : 0;

  return {
    stats, recent, summaries, search, setSearch, results, searching,
    activeTab, setActiveTab, deleting, loading, summarising, summariseResult,
    totalEntries, doSearch, deleteSource, summarise,
  };
}
