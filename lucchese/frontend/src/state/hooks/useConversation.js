// Conversation list state (Rule 19). From App.jsx ChatApp — owns the sidebar
// list and the active conversation id. Message content is owned by useChat.
import { useState, useEffect, useCallback } from "react";
import { listConversations, deleteConversation as apiDelete } from "../../api/conversationApi";

export function useConversation() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);

  const fetchConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => { fetchConversations(); }, [fetchConversations]);

  // Deletes a conversation; onActiveDeleted runs when the open one was removed.
  const deleteConversation = useCallback(async (e, id, onActiveDeleted) => {
    e.stopPropagation();
    await apiDelete(id);
    if (activeId === id) onActiveDeleted?.();
    fetchConversations();
  }, [activeId, fetchConversations]);

  const titleFor = useCallback(
    (id) => conversations.find((c) => c.id === id)?.title,
    [conversations]
  );

  return {
    conversations, activeId, setActiveId,
    fetchConversations, deleteConversation, titleFor,
  };
}
