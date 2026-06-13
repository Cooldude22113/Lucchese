// Date formatting helpers (Rule 10/22: pure helper).
// Consolidates the various `toLocaleDateString("en-GB", …)` calls duplicated
// across App.jsx, AdminPanel.jsx and Home.jsx.

// "5 Jun 2024"
export function formatFullDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

// "5 Jun"
export function formatShortDate(iso) {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

// "Wednesday, 5 June" — used by the Home greeting header.
export function formatWeekday(date) {
  return date.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}
