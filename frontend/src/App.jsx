import { useState, useRef, useEffect } from "react";
import AdminPanel from "./AdminPanel";
import Home from "./Home";
import ReactMarkdown from "react-markdown";
import Voice from "./Voice";

const API = "https://api.lucchese.app";

function Message({ role, content, isLatest, exchange, onFeedback }) {
  const isUser = role === "user";
  const [rated, setRated] = useState(null);

  const giveFeedback = async (rating) => {
    setRated(rating);
    if (exchange) {
      await fetch(`${API}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...exchange, rating }),
      });
    }
  };

  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: "1.5rem",
      animation: "fadeUp 0.3s ease forwards",
    }}>
      {!isUser && (
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "linear-gradient(135deg, #c8a96e, #8b6914)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700, color: "#0a0a0a",
          marginRight: 10, flexShrink: 0, marginTop: 2,
          fontFamily: "'Playfair Display', serif",
        }}>L</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", maxWidth: "70%" }}>
        <div style={{
          padding: "0.85rem 1.1rem",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "linear-gradient(135deg, #c8a96e22, #c8a96e11)" : "#141414",
          border: isUser ? "1px solid #c8a96e44" : "1px solid #222",
          color: "#e8e0d0",
          fontSize: "0.92rem",
          lineHeight: 1.7,
          fontFamily: "'DM Sans', sans-serif",
          wordBreak: "break-word",
        }}>
          <div className="message-content">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        </div>
        {!isUser && isLatest && (
          <div style={{ display: "flex", gap: 6, marginTop: 6, paddingLeft: 4 }}>
            <button
              onClick={() => giveFeedback("good")}
              title="Good response — save to memory"
              style={{
                opacity: rated ? (rated === "good" ? 1 : 0.3) : 0.4,
                transition: "opacity 0.2s",
                color: rated === "good" ? "#4caf7d" : "#555",
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill={rated === "good" ? "#4caf7d" : "none"} stroke="currentColor" strokeWidth="2">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
                <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
              </svg>
            </button>
            <button
              onClick={() => giveFeedback("bad")}
              title="Bad response — remove from memory"
              style={{
                opacity: rated ? (rated === "bad" ? 1 : 0.3) : 0.4,
                transition: "opacity 0.2s",
                color: rated === "bad" ? "#e06c75" : "#555",
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill={rated === "bad" ? "#e06c75" : "none"} stroke="currentColor" strokeWidth="2">
                <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
                <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
              </svg>
            </button>
            {exchange?.auto_ingested && !rated && (
              <span style={{ fontSize: "0.65rem", color: "#333", alignSelf: "center", marginLeft: 2 }}>auto-saved</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: "1.5rem" }}>
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        background: "linear-gradient(135deg, #c8a96e, #8b6914)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, fontWeight: 700, color: "#0a0a0a",
        marginRight: 10, flexShrink: 0,
        fontFamily: "'Playfair Display', serif",
      }}>L</div>
      <div style={{
        padding: "0.85rem 1.2rem",
        borderRadius: "18px 18px 18px 4px",
        background: "#141414", border: "1px solid #222",
        display: "flex", gap: 5, alignItems: "center",
      }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: "50%",
            background: "#c8a96e",
            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

function DocumentsPanel({ onClose }) {
  const [documents, setDocuments]   = useState([]);
  const [uploading, setUploading]   = useState(false);
  const [uploadMsg, setUploadMsg]   = useState("");
  const [dragOver, setDragOver]     = useState(false);
  const fileRef = useRef(null);

  useEffect(() => { fetchDocs(); }, []);

  const fetchDocs = async () => {
    const res = await fetch(`${API}/documents`);
    const data = await res.json();
    setDocuments(data);
  };

  const uploadFile = async (file) => {
    if (!file) return;
    const allowed = ["application/pdf", "text/plain", "text/markdown"];
    if (!allowed.includes(file.type) && !file.name.endsWith(".md") && !file.name.endsWith(".txt") && !file.name.endsWith(".pdf")) {
      setUploadMsg("Only PDF, TXT, and MD files supported.");
      return;
    }
    setUploading(true);
    setUploadMsg("Uploading and ingesting...");
    const form = new FormData();
    form.append("file", file);
    try {
      const res  = await fetch(`${API}/upload`, { method: "POST", body: form });
      const data = await res.json();
      setUploadMsg(`✓ ${data.filename} — ${data.chunk_count} chunks ingested`);
      fetchDocs();
    } catch (e) {
      setUploadMsg("Upload failed. Check backend.");
    } finally {
      setUploading(false);
    }
  };

  const deleteDoc = async (id) => {
    await fetch(`${API}/documents/${id}`, { method: "DELETE" });
    fetchDocs();
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };
  

  const formatDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#000000aa",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 100,
    }} onClick={onClose}>
      <div style={{
        background: "#0f0f0f", border: "1px solid #222",
        borderRadius: 16, width: 500, maxHeight: "80vh",
        display: "flex", flexDirection: "column",
        overflow: "hidden",
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{
          padding: "1.2rem 1.5rem",
          borderBottom: "1px solid #1a1a1a",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: "1.1rem", color: "#e8e0d0" }}>Documents</h2>
            <p style={{ fontSize: "0.73rem", color: "#555", marginTop: 2 }}>PDFs and text files Lucchese can search</p>
          </div>
          <button onClick={onClose} style={{ color: "#555", padding: 4 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            margin: "1.2rem 1.5rem",
            border: `2px dashed ${dragOver ? "#c8a96e" : "#2a2a2a"}`,
            borderRadius: 10,
            padding: "1.5rem",
            textAlign: "center",
            cursor: "pointer",
            transition: "border-color 0.2s",
            background: dragOver ? "#c8a96e08" : "transparent",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.5" style={{ marginBottom: 8 }}>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <p style={{ color: "#555", fontSize: "0.82rem" }}>
            {uploading ? "Ingesting..." : "Drop a file or click to upload"}
          </p>
          <p style={{ color: "#333", fontSize: "0.72rem", marginTop: 4 }}>PDF, TXT, MD supported</p>
          {uploadMsg && (
            <p style={{ color: uploadMsg.startsWith("✓") ? "#4caf7d" : "#e06c75", fontSize: "0.78rem", marginTop: 8 }}>
              {uploadMsg}
            </p>
          )}
          <input ref={fileRef} type="file" accept=".pdf,.txt,.md" style={{ display: "none" }}
            onChange={e => { if (e.target.files[0]) uploadFile(e.target.files[0]); }} />
        </div>

        {/* Document list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "0 1.5rem 1.5rem" }}>
          {documents.length === 0 ? (
            <p style={{ color: "#333", fontSize: "0.78rem", textAlign: "center", padding: "1rem 0" }}>
              No documents uploaded yet
            </p>
          ) : (
            documents.map(doc => (
              <div key={doc.id} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "0.7rem 0",
                borderBottom: "1px solid #161616",
              }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 6,
                  background: "#1a1a1a", border: "1px solid #222",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c8a96e" strokeWidth="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: "0.82rem", color: "#ccc", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {doc.filename}
                  </p>
                  <p style={{ fontSize: "0.7rem", color: "#444", marginTop: 2 }}>
                    {doc.chunk_count} chunks · {formatDate(doc.created_at)}
                  </p>
                </div>
                <button onClick={() => deleteDoc(doc.id)} style={{ color: "#444", padding: 4, flexShrink: 0 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6l-1 14H6L5 6"/>
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const path = window.location.pathname;
  
  if (path === "/admin") return <AdminPanel />;
  if (path === "/" || path === "/home") return <Home />;
  if (path === "/voice") return <Voice />;

  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId]           = useState(null);
  const [messages, setMessages]           = useState([]);
  const [input, setInput]                 = useState("");
  const [loading, setLoading]             = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [showDocs, setShowDocs]           = useState(false);
  const [lastExchange, setLastExchange] = useState(null);
  const [voiceMode, setVoiceMode]     = useState(false);
  const [recording, setRecording]     = useState(false);
  const mediaRecorderRef              = useRef(null);
  const audioChunksRef                = useRef([]);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => { fetchConversations(); }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API}/conversations`);
      setConversations(await res.json());
    } catch (e) {}
  };

  const loadConversation = async (id) => {
    const res  = await fetch(`${API}/conversations/${id}`);
    const data = await res.json();
    setMessages(data.map(m => ({ role: m.role, content: m.content })));
    setActiveId(id);
  };

  const newConversation = () => {
    setActiveId(null);
    setMessages([{ role: "assistant", content: "Good to see you, Alex. What's on your mind?" }]);
  };

  const deleteConversation = async (e, id) => {
    e.stopPropagation();
    await fetch(`${API}/conversations/${id}`, { method: "DELETE" });
    if (activeId === id) newConversation();
    fetchConversations();
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history, conversation_id: activeId }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullReply = "";
      let metaReceived = false;
      let bubbleAdded = false;
      // ── TTS streaming vars ──
      let ttsBuffer = "";
      const ttsQueue = [];
      let ttsPlaying = false;

      const drainTTSQueue = async () => {
        if (ttsPlaying) return;
        ttsPlaying = true;
        while (ttsQueue.length > 0) {
          await playAudio(ttsQueue.shift());
        }
        ttsPlaying = false;
      };

      const flushTTSSentence = (force = false) => {
        const sentenceEnd = /[.!?]\s/g;
        let match;
        let lastIndex = 0;
        while ((match = sentenceEnd.exec(ttsBuffer)) !== null) {
          const sentence = ttsBuffer.slice(lastIndex, match.index + 1).trim();
          if (sentence) ttsQueue.push(sentence);
          lastIndex = match.index + 2;
        }
        if (lastIndex > 0) ttsBuffer = ttsBuffer.slice(lastIndex);
        if (force && ttsBuffer.trim()) {
          ttsQueue.push(ttsBuffer.trim());
          ttsBuffer = "";
        }
        if (voiceMode) drainTTSQueue();
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const chunk = JSON.parse(line);

            if (chunk.type === "meta") {
              console.log("meta received, bubbleAdded:", bubbleAdded, "messages length:", messages.length);
              if (!activeId) setActiveId(chunk.conversation_id);
              if (!bubbleAdded) {
                setMessages(prev => [...prev, { role: "assistant", content: "" }]);
                bubbleAdded = true;
              }
            }

            if (chunk.type === "token") {
              fullReply += chunk.content;
              ttsBuffer += chunk.content;
              flushTTSSentence();
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", content: fullReply };
                return updated;
              });
            }

            if (chunk.type === "done") {
              setLastExchange({
                conversation_id: activeId,
                user_message: text,
                assistant_reply: fullReply,
                auto_ingested: chunk.auto_ingested,
              });
              flushTTSSentence(true);
              fetchConversations();
            }
          } catch (e) {
            continue;
          }
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: "assistant", content: "Something went wrong connecting to the backend." }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const toggleRecording = async () => {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = [
          "audio/webm;codecs=opus",
          "audio/webm",
          "audio/mp4",
          "audio/ogg;codecs=opus",
          "",
        ].find(m => m === "" || MediaRecorder.isTypeSupported(m));

        const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = e => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data);
        };

        mediaRecorder.onstop = async () => {
          const blob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType || "audio/webm" });
          const form = new FormData();
          const ext = mediaRecorder.mimeType?.includes("mp4") ? "mp4" : mediaRecorder.mimeType?.includes("ogg") ? "ogg" : "webm";
          form.append("file", blob, `recording.${ext}`);
          try {
            const res = await fetch(`${API}/transcribe`, { method: "POST", body: form });
            const data = await res.json();
            if (data.text) setInput(data.text);
          } catch (err) {
            console.error("Transcribe error:", err);
          }
          stream.getTracks().forEach(t => t.stop());
        };

        mediaRecorder.start();
        setRecording(true);
      } catch (err) {
        console.error("Mic error:", err);
        alert("Microphone access denied or unavailable.");
      }
    }
  };

  // Play audio via AudioContext (works on mobile/iOS)
  const playAudioBlob = async (blob) => {
    try {
      const arrayBuffer = await blob.arrayBuffer();
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const decoded = await audioCtx.decodeAudioData(arrayBuffer);
      const source = audioCtx.createBufferSource();
      source.buffer = decoded;
      source.connect(audioCtx.destination);
      source.start(0);
      return new Promise(resolve => { source.onended = resolve; });
    } catch (err) {
      console.error("Audio play error:", err);
    }
  };

  // TTS a sentence chunk
  const playAudio = async (text) => {
    if (!voiceMode || !text.trim()) return;
    try {
      const res = await fetch(`${API}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      await playAudioBlob(blob);
    } catch (err) {
      console.error("playAudio error:", err);
    }
  };

  const formatDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

  // WAV encoder helper - add this outside the App component
  function encodeWAV(audioBuffer) {
    const numChannels = 1;
    const sampleRate = audioBuffer.sampleRate;
    const samples = audioBuffer.getChannelData(0);
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, samples.length * 2, true);

    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      offset += 2;
    }
    return buffer;
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0a0a0a; color: #e8e0d0; font-family: 'DM Sans', sans-serif; height: 100vh; overflow: hidden; }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%,100% { opacity: 0.3; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.1); } }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
        textarea { resize: none; outline: none; border: none; background: transparent; color: #e8e0d0; font-family: 'DM Sans', sans-serif; font-size: 0.95rem; width: 100%; line-height: 1.6; }
        textarea::placeholder { color: #444; }
        button { cursor: pointer; border: none; outline: none; background: none; }
        button:disabled { opacity: 0.4; cursor: not-allowed; }
        .conv-item:hover { background: #161616 !important; }
        .conv-item.active { background: #1a1a1a !important; border-left: 2px solid #c8a96e !important; }
        .del-btn { opacity: 0; transition: opacity 0.2s; }
        .conv-item:hover .del-btn { opacity: 1; }
        .message-content p { margin-bottom: 0.5rem; }
        .message-content p:last-child { margin-bottom: 0; }
        .message-content strong { color: #c8a96e; }
        .message-content ul, .message-content ol { padding-left: 1.2rem; margin-bottom: 0.5rem; }
        .message-content li { margin-bottom: 0.3rem; }
        .message-content h1, .message-content h2, .message-content h3 { color: #e8e0d0; margin-bottom: 0.4rem; margin-top: 0.6rem; font-family: 'Playfair Display', serif; }
        .message-content code { background: #1a1a1a; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; color: #c8a96e; }
        .message-content { text-align: left; }
        .message-content p { margin-bottom: 0.6rem; }
      `}</style>

      {showDocs && <DocumentsPanel onClose={() => setShowDocs(false)} />}

      <div style={{ display: "flex", height: "100vh" }}>

        {/* Sidebar */}
        {sidebarOpen && (
          <div style={{
            width: 240, background: "#0d0d0d",
            borderRight: "1px solid #1a1a1a",
            display: "flex", flexDirection: "column", flexShrink: 0,
          }}>
            <div style={{ padding: "1.2rem 1rem 0.8rem", borderBottom: "1px solid #1a1a1a" }}>
              <a href="/" style={{ textDecoration: "none" }}>
                <p style={{
                  fontFamily: "'Playfair Display', serif", fontSize: "1rem",
                  background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
                  WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                  marginBottom: "0.8rem",
                }}>Lucchese</p>
              </a>
              <button onClick={newConversation} style={{
                width: "100%", padding: "0.55rem 0.8rem",
                background: "#161616", border: "1px solid #2a2a2a",
                borderRadius: 8, color: "#888", fontSize: "0.8rem",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                New conversation
              </button>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
              {conversations.length === 0 && (
                <p style={{ color: "#333", fontSize: "0.75rem", padding: "1rem", textAlign: "center" }}>No conversations yet</p>
              )}
              {conversations.map(conv => (
                <div key={conv.id}
                  className={`conv-item${activeId === conv.id ? " active" : ""}`}
                  onClick={() => loadConversation(conv.id)}
                  style={{
                    padding: "0.65rem 1rem", cursor: "pointer",
                    borderLeft: "2px solid transparent",
                    display: "flex", alignItems: "center", gap: 8,
                    transition: "background 0.15s",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: "0.78rem", color: "#bbb", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {conv.title || "Untitled"}
                    </p>
                    <p style={{ fontSize: "0.68rem", color: "#444", marginTop: 2 }}>{formatDate(conv.updated_at)}</p>
                  </div>
                  <button className="del-btn" onClick={(e) => deleteConversation(e, conv.id)} style={{ color: "#555", padding: 2, flexShrink: 0 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                  </button>
                </div>
              ))}
            </div>

            {/* Documents button */}
            <div style={{ padding: "0.8rem 1rem", borderTop: "1px solid #1a1a1a" }}>
              <button onClick={() => setShowDocs(true)} style={{
                width: "100%", padding: "0.55rem 0.8rem",
                background: "#161616", border: "1px solid #2a2a2a",
                borderRadius: 8, color: "#888", fontSize: "0.8rem",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
                Documents
              </button>
            </div>
          </div>
        )}

        {/* Main chat */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{
            padding: "1rem 1.5rem", borderBottom: "1px solid #1a1a1a",
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <button onClick={() => setSidebarOpen(o => !o)} style={{ color: "#555", padding: 4 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            </button>
            <span style={{ fontSize: "0.75rem", color: "#444", letterSpacing: 2, textTransform: "uppercase" }}>
              {activeId ? conversations.find(c => c.id === activeId)?.title || "Conversation" : "New conversation"}
            </span>
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4caf7d", boxShadow: "0 0 6px #4caf7d88" }} />
              <span style={{ fontSize: "0.72rem", color: "#555", letterSpacing: 1 }}>ONLINE</span>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "2rem 2rem 1rem", maxWidth: 760, width: "100%", margin: "0 auto", alignSelf: "center", boxSizing: "border-box" }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", marginTop: "4rem" }}>
                <p style={{
                  fontFamily: "'Playfair Display', serif", fontSize: "1.8rem",
                  background: "linear-gradient(135deg, #c8a96e, #e8d5a3)",
                  WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                  marginBottom: "0.5rem",
                }}>Lucchese</p>
                <p style={{ color: "#444", fontSize: "0.85rem" }}>Select a conversation or start a new one</p>
              </div>
            )}
            {messages.map((m, i) => (
              <Message
                key={i}
                {...m}
                isLatest={i === messages.length - 1 && m.role === "assistant"}
                exchange={i === messages.length - 1 && m.role === "assistant" ? lastExchange : null}
              />
            ))}
            {loading && !(messages[messages.length - 1]?.role === "assistant") && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          <div style={{ padding: "1rem 2rem 1.5rem", maxWidth: 760, width: "100%", margin: "0 auto", alignSelf: "center", boxSizing: "border-box" }}>
            <div style={{
              display: "flex", alignItems: "flex-end", gap: 10,
              background: "#111", border: "1px solid #2a2a2a",
              borderRadius: 14, padding: "0.75rem 0.75rem 0.75rem 1.1rem",
            }}>
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                }}
                onKeyDown={onKey}
                placeholder="Message Lucchese..."
                style={{ maxHeight: 120 }}
              />
              {/* Voice mode toggle */}
              <button
                  onClick={() => setVoiceMode(v => !v)}
                  title={voiceMode ? "Voice mode on" : "Voice mode off"}
                  style={{
                      width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                      background: voiceMode ? "linear-gradient(135deg, #c8a96e, #8b6914)" : "#1e1e1e",
                      display: "flex", alignItems: "center", justifyContent: "center",
                  }}
              >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={voiceMode ? "#0a0a0a" : "#444"} strokeWidth="2">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                      <line x1="12" y1="19" x2="12" y2="23"/>
                      <line x1="8" y1="23" x2="16" y2="23"/>
                  </svg>
              </button>

              {/* Record button */}
             <button
                  onClick={toggleRecording}
                  title={recording ? "Tap to stop" : "Tap to speak"}
                  style={{
                      width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                      background: recording ? "linear-gradient(135deg, #e06c75, #c0392b)" : "#1e1e1e",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      transition: "background 0.2s",
                  }}
              >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill={recording ? "#fff" : "none"} stroke={recording ? "#fff" : "#444"} strokeWidth="2">
                      <circle cx="12" cy="12" r="6"/>
                  </svg>
              </button>
              <button onClick={send} disabled={!input.trim() || loading} style={{
                width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                background: input.trim() && !loading ? "linear-gradient(135deg, #c8a96e, #8b6914)" : "#1e1e1e",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "background 0.2s",
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={input.trim() && !loading ? "#0a0a0a" : "#444"} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
            <p style={{ textAlign: "center", fontSize: "0.68rem", color: "#2a2a2a", marginTop: "0.6rem", letterSpacing: 1 }}>
              SHIFT+ENTER FOR NEW LINE · ENTER TO SEND
            </p>
          </div>
        </div>
      </div>
    </>
  );
}