import { useState, useEffect } from "react";

const API = "https://api.lucchese.app";

const gold = "#c8a96e";
const goldDim = "#8b6914";
const bg = "#0a0a0a";
const surface = "#0f0f0f";
const border = "#1e1e1e";

function useStats() {
  const [stats, setStats] = useState(null);
  const [convs, setConvs] = useState([]);
  const [docs, setDocs] = useState([]);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/admin/stats`).then(r => r.json()).catch(() => null),
      fetch(`${API}/conversations`).then(r => r.json()).catch(() => []),
      fetch(`${API}/documents`).then(r => r.json()).catch(() => []),
    ]).then(([s, c, d]) => {
      setStats(s);
      setConvs(c);
      setDocs(d);
    });
  }, []);

  return { stats, convs, docs };
}

function Card({ children, style = {}, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: surface,
        border: `1px solid ${hovered && onClick ? "#c8a96e44" : border}`,
        borderRadius: 14,
        padding: "1.4rem",
        transition: "all 0.2s ease",
        cursor: onClick ? "pointer" : "default",
        transform: hovered && onClick ? "translateY(-2px)" : "none",
        boxShadow: hovered && onClick ? "0 8px 32px #c8a96e0a" : "none",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function NavLink({ href, label, active }) {
  return (
    <a href={href} style={{
      fontSize: "0.72rem",
      color: active ? gold : "#555",
      textDecoration: "none",
      letterSpacing: 1.5,
      textTransform: "uppercase",
      borderBottom: active ? `1px solid ${gold}` : "1px solid transparent",
      paddingBottom: 2,
      transition: "color 0.2s",
    }}>{label}</a>
  );
}

function StatPill({ label, value, color }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "0.8rem 1.2rem",
      background: "#111",
      border: `1px solid ${border}`,
      borderRadius: 10,
      minWidth: 80,
    }}>
      <span style={{ fontSize: "1.4rem", fontFamily: "'Playfair Display', serif", color: color || gold }}>{value}</span>
      <span style={{ fontSize: "0.62rem", color: "#444", marginTop: 4, textTransform: "uppercase", letterSpacing: 1 }}>{label}</span>
    </div>
  );
}

function QuickAction({ icon, label, desc, href, accent }) {
  const [hovered, setHovered] = useState(false);
  return (
    <a href={href} style={{ textDecoration: "none" }}>
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          background: hovered ? "#141414" : surface,
          border: `1px solid ${hovered ? (accent || "#c8a96e44") : border}`,
          borderRadius: 12,
          padding: "1.2rem",
          transition: "all 0.2s",
          cursor: "pointer",
          transform: hovered ? "translateY(-2px)" : "none",
        }}
      >
        <div style={{ fontSize: "1.4rem", marginBottom: 10 }}>{icon}</div>
        <p style={{ fontSize: "0.85rem", color: "#e8e0d0", fontWeight: 500, fontFamily: "'DM Sans', sans-serif", marginBottom: 4 }}>{label}</p>
        <p style={{ fontSize: "0.72rem", color: "#444", lineHeight: 1.5 }}>{desc}</p>
      </div>
    </a>
  );
}

function RecentConv({ conv }) {
  const date = new Date(conv.updated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return (
    <a href="/chat" style={{ textDecoration: "none" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "0.7rem 0",
        borderBottom: `1px solid #111`,
      }}>
        <div style={{
          width: 6, height: 6, borderRadius: "50%",
          background: gold, flexShrink: 0, opacity: 0.6
        }} />
        <p style={{ flex: 1, fontSize: "0.78rem", color: "#888", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {conv.title || "Untitled"}
        </p>
        <span style={{ fontSize: "0.65rem", color: "#333", flexShrink: 0 }}>{date}</span>
      </div>
    </a>
  );
}

export default function Home() {
  const { stats, convs, docs } = useStats();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 60000);
    return () => clearInterval(t);
  }, []);

  const totalMemory = stats ? Object.values(stats).reduce((s, c) => s + c.total, 0) : null;
  const hour = time.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const dayStr = time.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=DM+Sans:wght@300;400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${bg}; color: #e8e0d0; font-family: 'DM Sans', sans-serif; min-height: 100vh; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
        .fade-1 { animation: fadeUp 0.5s ease 0.1s both; }
        .fade-2 { animation: fadeUp 0.5s ease 0.2s both; }
        .fade-3 { animation: fadeUp 0.5s ease 0.3s both; }
        .fade-4 { animation: fadeUp 0.5s ease 0.4s both; }
        .fade-5 { animation: fadeUp 0.5s ease 0.5s both; }
      `}</style>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>

        {/* Nav */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: "3rem",
          paddingBottom: "1.2rem",
          borderBottom: `1px solid ${border}`,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
            <span style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: "1.1rem",
              background: `linear-gradient(135deg, ${gold}, #e8d5a3)`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}>Lucchese</span>
            <span style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase" }}>Personal AI</span>
          </div>
          <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
            <NavLink href="/" label="Home" active />
            <NavLink href="/chat" label="Chat" />
            <NavLink href="/admin" label="Admin" />
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4caf7d", animation: "pulse 2s ease infinite" }} />
              <span style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 1 }}>ONLINE</span>
            </div>
          </div>
        </div>

        {/* Hero greeting */}
        <div className="fade-1" style={{ marginBottom: "2.5rem" }}>
          <p style={{ fontSize: "0.72rem", color: "#444", letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>{dayStr}</p>
          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: "clamp(2rem, 4vw, 3rem)",
            fontWeight: 400,
            lineHeight: 1.2,
            color: "#e8e0d0",
          }}>
            {greeting}, Alex.
          </h1>
          <p style={{ fontSize: "0.9rem", color: "#444", marginTop: 8 }}>
            {convs.length > 0
              ? `${convs.length} conversations · ${totalMemory?.toLocaleString() ?? "—"} memories stored`
              : "Ready when you are."}
          </p>
        </div>

        {/* Memory stats */}
        {stats && (
          <div className="fade-2" style={{ marginBottom: "2.5rem" }}>
            <p style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase", marginBottom: "1rem" }}>Memory</p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <StatPill label="Total" value={totalMemory?.toLocaleString() ?? "—"} color={gold} />
              <StatPill label="Knowledge" value={stats.knowledge?.total?.toLocaleString() ?? "—"} color="#7cb8e8" />
              <StatPill label="Facts" value={stats.facts?.total?.toLocaleString() ?? "—"} color="#7ce8a8" />
              <StatPill label="Style" value={stats.style?.total?.toLocaleString() ?? "—"} color="#e8a87c" />
              <StatPill label="Documents" value={docs.length} color="#a87ce8" />
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="fade-3" style={{ marginBottom: "2.5rem" }}>
          <p style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase", marginBottom: "1rem" }}>Quick Access</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem" }}>
            <QuickAction
              icon="💬"
              label="Chat with Lucchese"
              desc="Ask anything, get answers from your memory and knowledge base"
              href="/chat"
              accent="#c8a96e44"
            />
            <QuickAction
              icon="🏠"
              label="Deal Analyser"
              desc="Type 'analyse deal:' in chat to run property numbers instantly"
              href="/chat"
              accent="#7cb8e844"
            />
            <QuickAction
              icon="🎭"
              label="Practice Pitch"
              desc="Type 'practice pitch' in chat to practise with Carol"
              href="/chat"
              accent="#e8a87c44"
            />
            <QuickAction
              icon="📊"
              label="Memory Admin"
              desc="View, search and manage everything Lucchese knows"
              href="/admin"
              accent="#7ce8a844"
            />
            <QuickAction
              icon="📄"
              label="Documents"
              desc={`${docs.length} document${docs.length !== 1 ? "s" : ""} uploaded — add more via chat`}
              href="/chat"
              accent="#a87ce844"
            />
            <QuickAction
              icon="🎙️"
              label="Voice Mode"
              desc="Hands-free voice conversation with Lucchese"
              href="/voice"
              accent="#c8a96e44"
            />
          </div>
        </div>

        {/* Two column — recent convs + property tools */}
        <div className="fade-4" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "2.5rem" }}>

          {/* Recent conversations */}
          <Card>
            <p style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase", marginBottom: "1rem" }}>Recent Conversations</p>
            {convs.length === 0 ? (
              <p style={{ fontSize: "0.78rem", color: "#333", padding: "1rem 0" }}>No conversations yet</p>
            ) : (
              convs.slice(0, 6).map(c => <RecentConv key={c.id} conv={c} />)
            )}
            {convs.length > 6 && (
              <a href="/chat" style={{ fontSize: "0.72rem", color: "#444", textDecoration: "none", display: "block", marginTop: "0.8rem" }}>
                + {convs.length - 6} more →
              </a>
            )}
          </Card>

          {/* Property tools */}
          <Card>
            <p style={{ fontSize: "0.65rem", color: "#333", letterSpacing: 2, textTransform: "uppercase", marginBottom: "1rem" }}>Property Tools</p>

            <div style={{ marginBottom: "1.2rem" }}>
              <p style={{ fontSize: "0.8rem", color: "#e8e0d0", fontWeight: 500, marginBottom: 4 }}>Deal Analyser</p>
              <p style={{ fontSize: "0.72rem", color: "#555", lineHeight: 1.6 }}>
                In chat: <span style={{ color: gold, fontFamily: "monospace" }}>analyse deal: 3 bed Romford £320k, £1,200/month rent</span>
              </p>
            </div>

            <div style={{ marginBottom: "1.2rem" }}>
              <p style={{ fontSize: "0.8rem", color: "#e8e0d0", fontWeight: 500, marginBottom: 4 }}>Pitch Practice (Carol)</p>
              <p style={{ fontSize: "0.72rem", color: "#555", lineHeight: 1.6 }}>
                In chat: <span style={{ color: gold, fontFamily: "monospace" }}>practice pitch</span> — then type <span style={{ color: gold, fontFamily: "monospace" }}>end practice</span> for feedback
              </p>
            </div>

            <div style={{ marginBottom: "1.2rem" }}>
              <p style={{ fontSize: "0.8rem", color: "#e8e0d0", fontWeight: 500, marginBottom: 4 }}>Property Guide</p>
              <p style={{ fontSize: "0.72rem", color: "#555", lineHeight: 1.6 }}>
                Uploaded to Lucchese — ask anything about Essex property, HMO compliance, remortgaging, strategies
              </p>
            </div>

            <div>
              <p style={{ fontSize: "0.8rem", color: "#e8e0d0", fontWeight: 500, marginBottom: 4 }}>Family Summary Doc</p>
              <p style={{ fontSize: "0.72rem", color: "#555", lineHeight: 1.6 }}>
                Print-ready document for family meetings — covers equity release, Essex examples, risk, costs
              </p>
            </div>
          </Card>
        </div>

        {/* Footer */}
        <div className="fade-5" style={{
          borderTop: `1px solid ${border}`,
          paddingTop: "1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <p style={{ fontSize: "0.65rem", color: "#2a2a2a", letterSpacing: 1 }}>
            LUCCHESE · PERSONAL AI · {new Date().getFullYear()}
          </p>
          <div style={{ display: "flex", gap: 20 }}>
            <a href="/chat" style={{ fontSize: "0.65rem", color: "#333", textDecoration: "none", letterSpacing: 1 }}>CHAT →</a>
            <a href="/admin" style={{ fontSize: "0.65rem", color: "#333", textDecoration: "none", letterSpacing: 1 }}>ADMIN →</a>
          </div>
        </div>

      </div>
    </>
  );
}