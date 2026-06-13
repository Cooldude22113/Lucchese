// Conversation endpoints (Rule 19).
import { getJSON, del } from "./client";

export function listConversations() {
  return getJSON("/conversations");
}

export function getConversation(id) {
  return getJSON(`/conversations/${id}`);
}

export function deleteConversation(id) {
  return del(`/conversations/${id}`);
}
