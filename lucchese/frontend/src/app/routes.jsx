// Path → page map (Rule 19/21). Extracted from App.jsx's path switch. The app
// uses plain pathname routing (no router library), matching the original.
import HomePage from "../interface/pages/HomePage";
import ChatPage from "../interface/pages/ChatPage";
import AdminPage from "../interface/pages/AdminPage";
import VoicePage from "../interface/pages/VoicePage";

// Returns the page component for a given pathname.
export function resolvePage(pathname) {
  if (pathname === "/admin") return AdminPage;
  if (pathname === "/" || pathname === "/home") return HomePage;
  if (pathname === "/voice") return VoicePage;
  return ChatPage;
}
