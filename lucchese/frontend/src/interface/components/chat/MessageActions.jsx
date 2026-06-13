// Thumbs up/down feedback row (Rule 19/20). From App.jsx Message.
// Sends the rating through chatApi and remembers the local choice.
import { useState } from "react";
import { sendFeedback } from "../../../api/chatApi";

export default function MessageActions({ exchange }) {
  const [rated, setRated] = useState(null);

  const giveFeedback = async (rating) => {
    setRated(rating);
    if (exchange) await sendFeedback(exchange, rating);
  };

  return (
    <div style={{ display: "flex", gap: 6, marginTop: 6, paddingLeft: 4 }}>
      <button
        onClick={() => giveFeedback("good")}
        title="Good response — save to memory"
        style={{ opacity: rated ? (rated === "good" ? 1 : 0.3) : 0.4, transition: "opacity 0.2s", color: rated === "good" ? "#4caf7d" : "#555" }}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill={rated === "good" ? "#4caf7d" : "none"} stroke="currentColor" strokeWidth="2">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
        </svg>
      </button>
      <button
        onClick={() => giveFeedback("bad")}
        title="Bad response — remove from memory"
        style={{ opacity: rated ? (rated === "bad" ? 1 : 0.3) : 0.4, transition: "opacity 0.2s", color: rated === "bad" ? "#e06c75" : "#555" }}
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
  );
}
