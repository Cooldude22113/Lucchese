// Chat column shell (Rule 19/20). The right-hand chat pane from App.jsx:
// top bar (Header) + message list + composer.
import Header from "../../layout/Header";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatWindow({ title, onToggleSidebar, chat, voice }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Header title={title} onToggleSidebar={onToggleSidebar} />
      <MessageList
        messages={chat.messages}
        loading={chat.loading}
        lastExchange={chat.lastExchange}
        bottomRef={chat.bottomRef}
      />
      <ChatInput
        input={chat.input}
        setInput={chat.setInput}
        onSend={chat.send}
        onKey={chat.onKey}
        inputRef={chat.inputRef}
        loading={chat.loading}
        voiceMode={voice.voiceMode}
        toggleVoiceMode={voice.toggleVoiceMode}
        recording={voice.recording}
        toggleRecording={voice.toggleRecording}
        audioError={voice.audioError}
      />
    </div>
  );
}
