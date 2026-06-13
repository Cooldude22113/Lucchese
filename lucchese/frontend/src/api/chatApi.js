// Chat endpoints (Rule 19). Streaming transport lives in client.streamNDJSON.
import { streamNDJSON, postJSON } from "./client";

// POST /chat — streamed NDJSON reply. onChunk receives each parsed event
// ({ type: "meta" | "token" | "done", ... }).
export function streamChat({ message, history, conversation_id }, onChunk) {
  return streamNDJSON("/chat", { message, history, conversation_id }, onChunk);
}

// POST /feedback — thumbs up/down on an exchange.
export function sendFeedback(exchange, rating) {
  return postJSON("/feedback", { ...exchange, rating });
}
