// Chat composer (Rule 19/20). From App.jsx input area — textarea + voice toggle,
// record and send buttons, hint line and audio-error line.
export default function ChatInput({
  input, setInput, onSend, onKey, inputRef,
  voiceMode, toggleVoiceMode, recording, toggleRecording,
  loading, audioError,
}) {
  return (
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
          onChange={(e) => {
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
          onClick={toggleVoiceMode}
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
            display: "flex", alignItems: "center", justifyContent: "center", transition: "background 0.2s",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill={recording ? "#fff" : "none"} stroke={recording ? "#fff" : "#444"} strokeWidth="2">
            <circle cx="12" cy="12" r="6"/>
          </svg>
        </button>

        {/* Send button */}
        <button onClick={onSend} disabled={!input.trim() || loading} style={{
          width: 34, height: 34, borderRadius: 9, flexShrink: 0,
          background: input.trim() && !loading ? "linear-gradient(135deg, #c8a96e, #8b6914)" : "#1e1e1e",
          display: "flex", alignItems: "center", justifyContent: "center", transition: "background 0.2s",
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
      {voiceMode && audioError && (
        <p style={{ textAlign: "center", fontSize: "0.72rem", color: "#e06c75", marginTop: "0.6rem" }}>
          ⚠ {audioError}
        </p>
      )}
    </div>
  );
}
