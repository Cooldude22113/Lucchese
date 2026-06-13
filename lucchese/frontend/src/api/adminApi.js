// Admin/memory endpoints (Rule 19). All require the admin key (client adds it).
import { getJSON, postJSON, del } from "./client";

export function getStats() {
  return getJSON("/admin/stats", { admin: true });
}

export function getRecent(limit = 30) {
  return getJSON(`/admin/recent?limit=${limit}`, { admin: true });
}

export function getSummaries() {
  return getJSON("/admin/summaries", { admin: true });
}

export function searchMemory(query, n = 10) {
  return getJSON(`/admin/search?q=${encodeURIComponent(query)}&n=${n}`, {
    admin: true,
  });
}

export function deleteBySource(source) {
  return del(`/admin/memory?source=${source}`, { admin: true });
}

export function rebuildSummaries() {
  return postJSON("/admin/summarise", {}, { admin: true });
}
