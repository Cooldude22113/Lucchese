import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./app/App.jsx";

// Global styles (replaces the inline <style> blocks from the old monoliths and
// the unused Vite boilerplate index.css).
import "./interface/styles/tokens.css";
import "./interface/styles/base.css";
import "./interface/styles/chat.css";
import "./interface/styles/voice.css";
import "./interface/styles/home.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
