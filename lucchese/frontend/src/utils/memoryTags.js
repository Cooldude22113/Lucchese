// Memory tag colour maps (Rule 22/23: pure reference data).
// From AdminPanel.jsx — shared by the admin and memory components that render
// source/category pills and bars.

export const CATEGORY_COLORS = {
  food: "#e8a87c",
  business: "#c8a96e",
  operations: "#7cb8e8",
  fitness: "#7ce8a8",
  health: "#e87cb8",
  career: "#a87ce8",
  personal: "#e8d87c",
  tech: "#7ce8e8",
  general: "#666",
};

export const SOURCE_COLORS = {
  grok: "#ff6b6b",
  chatgpt: "#19c37d",
  lucchese: "#c8a96e",
  explicit: "#7ce8a8",
  document: "#7cb8e8",
  unknown: "#666",
};

export const categoryColor = (key) => CATEGORY_COLORS[key] || "#666";
export const sourceColor = (key) => SOURCE_COLORS[key] || "#666";
