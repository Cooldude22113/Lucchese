// Chat screen (Rule 19/20). From App.jsx ChatApp — wires the conversation list,
// chat state and the documents modal together.
import { useState, useEffect } from "react";
import Sidebar from "../layout/Sidebar";
import ChatWindow from "../components/chat/ChatWindow";
import UploadPanel from "../components/documents/UploadPanel";
import { useConversation } from "../../state/hooks/useConversation";
import { useChat } from "../../state/hooks/useChat";

export default function ChatPage() {
  const conv = useConversation();
  const chat = useChat({
    activeId: conv.activeId,
    setActiveId: conv.setActiveId,
    onConversationsChanged: conv.fetchConversations,
  });

  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [showDocs, setShowDocs] = useState(false);

  // Start on a fresh conversation greeting.
  useEffect(() => { chat.newConversation(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const title = conv.activeId
    ? conv.titleFor(conv.activeId) || "Conversation"
    : "New conversation";

  return (
    <>
      {showDocs && <UploadPanel onClose={() => setShowDocs(false)} />}

      <div style={{ display: "flex", height: "100vh" }}>
        {sidebarOpen && (
          <Sidebar
            conversations={conv.conversations}
            activeId={conv.activeId}
            onLoad={chat.loadConversation}
            onNew={chat.newConversation}
            onDelete={(e, id) => conv.deleteConversation(e, id, chat.newConversation)}
            onOpenDocs={() => setShowDocs(true)}
          />
        )}

        <ChatWindow
          title={title}
          onToggleSidebar={() => setSidebarOpen((o) => !o)}
          chat={chat}
          voice={chat}
        />
      </div>
    </>
  );
}
