// App-wide configuration values (Rule 16/19: config stores values).
// Replaces the duplicated `const API = …` / `VITE_ADMIN_KEY` reads that were
// scattered across App.jsx, AdminPanel.jsx, Home.jsx and Voice.jsx.

export const API_URL = import.meta.env.VITE_API_URL || "https://api.lucchese.app";

export const ADMIN_KEY = import.meta.env.VITE_ADMIN_KEY;
