"""
routes/conversations.py
───────────────────────
Conversation history and feedback endpoints:

  GET    /conversations                   — list all conversations
  GET    /conversations/{conversation_id} — get all messages in a conversation
  DELETE /conversations/{conversation_id} — delete conversation from SQLite + ChromaDB
  POST   /feedback                        — thumbs up/down on a reply (triggers ingest or purge)

Delete is a two-phase operation — it removes from both SQLite (messages, conversations)
and ChromaDB (knowledge, facts, style) so memory doesn't persist after a conversation
is explicitly deleted.

Feedback wires directly into the memory system:
  - "good" rating  → ingest_exchange (stores the exchange as memory)
  - "bad" rating   → delete from col_knowledge by conv_id (purge if already stored)
"""

from fastapi import APIRouter
from pydantic import BaseModel
from routes.memory import ingest_exchange
from routes.memory import col_knowledge, col_facts, col_style
from routes.database import (
    delete_conversation_messages,
    list_conversations  as db_list_conversations,
    get_conversation    as db_get_conversation,
)

router = APIRouter()

# ── Request model ─────────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    conversation_id: str
    user_message:    str
    assistant_reply: str
    rating:          str   # "good" | "bad"


# ── GET /conversations ────────────────────────────────────────────────────────
@router.get("/conversations")
def list_conversations():
    return db_list_conversations()


# ── GET /conversations/{conversation_id} ──────────────────────────────────────
@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    return db_get_conversation(conversation_id)


# ── DELETE /conversations/{conversation_id} ───────────────────────────────────
@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """
    Fully remove a conversation — SQLite records and any associated ChromaDB memory.
    ChromaDB deletion is best-effort; SQLite deletion always runs.
    """
    # Phase 1 — purge from ChromaDB
    for col in [col_knowledge, col_facts, col_style]: 
        try:
            results = col.get(where={"conv_id": conversation_id})
            if results["ids"]:
                col.delete(ids=results["ids"])
        except Exception as e:
            print(f"delete_conversation chroma error: {e}")

    # Phase 2 — purge from SQLite
    delete_conversation_messages(conversation_id)


    return {"deleted": conversation_id}


# ── POST /feedback ────────────────────────────────────────────────────────────
@router.post("/feedback")
async def feedback(req: FeedbackRequest):
    """
    Thumbs up/down feedback on a specific exchange.

    good → ingest the exchange into memory (if not already stored)
    bad  → delete any memory already ingested from this conversation
    """
    if req.rating == "good":
        await ingest_exchange(
            req.conversation_id,
            req.user_message,
            req.assistant_reply,
        )
        return {"ingested": True}

    # bad rating — try to remove if already ingested
    try:
        results = col_knowledge.get(where={"conv_id": req.conversation_id})
        if results["ids"]:
            col_knowledge.delete(ids=results["ids"])
    except Exception as e:
        print(f"feedback delete error: {e}")

    return {"ingested": False}
