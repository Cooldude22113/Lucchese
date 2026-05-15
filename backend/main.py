from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import chromadb
from chromadb.utils import embedding_functions
import sqlite3
import uuid
import re
import io
from datetime import datetime, timezone
import math
from ddgs import DDGS
from pypdf import PdfReader
from sheets import get_menu_context, get_recipes
from shopify_api import create_meal_products as _create_meal_products
from elevenlabs.client import ElevenLabs
import os
import whisper
import tempfile
from dotenv import load_dotenv
load_dotenv()

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ChromaDB setup ───────────────────────────────────────────────────────────
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "all-MiniLM-L6-v2"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100

ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
chroma = chromadb.PersistentClient(path=CHROMA_PATH)

col_knowledge = chroma.get_or_create_collection("knowledge", embedding_function=ef)
col_facts     = chroma.get_or_create_collection("facts",     embedding_function=ef)
col_style     = chroma.get_or_create_collection("style",     embedding_function=ef)
col_documents = chroma.get_or_create_collection("documents", embedding_function=ef)

# ── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_FAST = "gemma2:27b"
MODEL_DEEP = "qwen2.5:32b"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

whisper_model = whisper.load_model("base")


# ── SQLite setup ─────────────────────────────────────────────────────────────
DB_PATH = "./conversations.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            title       TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id              TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            file_type   TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

init_db()

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def save_message(conversation_id: str, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    con = get_con()
    cur = con.cursor()

    cur.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO conversations (id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
            (conversation_id, now, now, None)
        )

    cur.execute(
        "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), conversation_id, role, content, now)
    )

    cur.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id)
    )

    cur.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at LIMIT 1",
        (conversation_id,)
    )
    first = cur.fetchone()
    if first:
        title = first["content"][:60] + ("..." if len(first["content"]) > 60 else "")
        cur.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))

    con.commit()
    con.close()

# ── Text chunking ─────────────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]

async def ingest_exchange(conversation_id: str, user_msg: str, assistant_reply: str):
    now = datetime.now(timezone.utc).isoformat()
    exchange_text = f"[You]: {user_msg}\n\n[Lucchese]: {assistant_reply}"

    for i, chunk in enumerate(chunk_text(exchange_text)):
        if not is_duplicate_memory(chunk, col_knowledge):
            col_knowledge.upsert(
                ids       = [f"lucchese_{conversation_id}_ex_{i}"],
                documents = [chunk],
                metadatas = [{
                    "source":     "lucchese",
                    "conv_id":    conversation_id,
                    "chunk_idx":  str(i),
                    "type":       "knowledge",
                    "created_at": now,
                }]
            )

    if len(user_msg.strip()) > 20:
        if not is_duplicate_memory(user_msg.strip(), col_facts):
            col_facts.upsert(
                ids       = [f"lucchese_fact_{conversation_id}_{uuid.uuid4().hex[:8]}"],
                documents = [user_msg.strip()],
                metadatas = [{
                    "source":     "lucchese",
                    "conv_id":    conversation_id,
                    "type":       "fact",
                    "created_at": now,
                }]
            )

    if len(user_msg.strip()) > 80:
        if not is_duplicate_memory(user_msg.strip(), col_style):
            col_style.upsert(
                ids       = [f"lucchese_style_{conversation_id}_{uuid.uuid4().hex[:8]}"],
                documents = [user_msg.strip()],
                metadatas = [{
                    "source":     "lucchese",
                    "conv_id":    conversation_id,
                    "type":       "style",
                    "created_at": now,
                }]
            )

# ── Memory quality filter ─────────────────────────────────────────────────────
async def should_ingest(user_msg: str, assistant_reply: str) -> bool:
    """Ask the LLM if this exchange is worth storing in long-term memory."""
    prompt = f"""You are a memory filter for an AI assistant called Lucchese.
Decide if the following exchange contains information worth storing in long-term memory.

Worth storing: personal facts about Alex, business info, preferences, decisions, corrections, goals.
Not worth storing: greetings, vague chitchat, failed/uncertain answers, repetitive info, web search results.

Exchange:
User: {user_msg[:300]}
Assistant: {assistant_reply[:300]}

Reply with ONLY one word: YES or NO."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(OLLAMA_URL, json={
                "model": MODEL_FAST,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            })
            verdict = res.json()["message"]["content"].strip().upper()
            verdict = verdict.split()[0] if verdict else "NO"
            print(f"Ingest decision: {verdict}")
            return verdict.startswith("YES")
    except Exception:
        return False  # if unsure, don't ingest
    
    


# ── Memory deduplication ──────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.15  # lower = stricter dedup (ChromaDB uses L2 distance)

def is_duplicate_memory(text: str, collection, n=1) -> bool:
    """Returns True if a very similar chunk already exists in the collection."""
    try:
        results = collection.query(query_texts=[text], n_results=n, include=["distances"])
        if results["distances"] and results["distances"][0]:
            closest_distance = results["distances"][0][0]
            return closest_distance < SIMILARITY_THRESHOLD
    except Exception:
        pass
    return False

# ── Explicit memory commands ──────────────────────────────────────────────────
REMEMBER_PATTERNS = [
    r'\bremember that\b(.+)',
    r'\bremember:\b(.+)',
    r'\bsave this\b(.+)',
    r'\bstore this\b(.+)',
    r'\bnote that\b(.+)',
]

FORGET_PATTERNS = [
    r'\bforget that\b(.+)',
    r'\bforget\b (.+)',
    r'\bdelete that\b',
    r'\bunremember\b(.+)',
    r'\bremove that\b',
]

def detect_memory_command(message: str):
    """Returns ('remember', text), ('forget', text), or (None, None)"""
    msg = message.lower().strip()
    
    for pattern in REMEMBER_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            return ("remember", match.group(1).strip())
    
    for pattern in FORGET_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            content = match.group(1).strip() if match.lastindex else ""
            return ("forget", content)
    
    return (None, None)


async def handle_memory_command(command: str, content: str, conversation_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()

    if command == "remember":
        # Force ingest the specific content
        if not is_duplicate_memory(content, col_facts):
            col_facts.upsert(
                ids       = [f"explicit_fact_{uuid.uuid4().hex[:8]}"],
                documents = [content],
                metadatas = [{
                    "source":     "explicit",
                    "conv_id":    conversation_id,
                    "type":       "fact",
                    "created_at": now,
                }]
            )
            return f"Got it, I'll remember that: *{content}*"
        else:
            return f"I already have that stored."

    elif command == "forget":
        deleted = 0
        if content:
            # Search for the closest matching memory and delete it
            for col in [col_facts, col_knowledge, col_style]:
                try:
                    results = col.query(
                        query_texts=[content],
                        n_results=3,
                        include=["distances"]
                    )
                    if results["ids"] and results["ids"][0]:
                        for id_, dist in zip(results["ids"][0], results["distances"][0]):
                            if dist < 0.3:  # only delete if it's a close match
                                col.delete(ids=[id_])
                                deleted += 1
                except Exception:
                    pass
        
        if deleted:
            return f"Done, I've removed that from my memory."
        else:
            return f"I couldn't find anything close enough to that in my memory to remove."

# ── Document ingestion ────────────────────────────────────────────────────────
def ingest_document(doc_id: str, filename: str, text: str) -> int:
    chunks = chunk_text(text)
    now = datetime.now(timezone.utc).isoformat()

    for i, chunk in enumerate(chunks):
        col_documents.upsert(
            ids       = [f"doc_{doc_id}_chunk_{i}"],
            documents = [chunk],
            metadatas = [{
                "source":     "document",
                "doc_id":     doc_id,
                "filename":   filename,
                "chunk_idx":  str(i),
                "created_at": now,
            }]
        )

    return len(chunks)

def extract_text(file_bytes: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    else:
        return file_bytes.decode("utf-8", errors="ignore")

# ── Web search ────────────────────────────────────────────────────────────────
WEB_TRIGGERS = [
    r"\b(latest|recent|current news|today|tonight)\b",
    r"\b(news|weather|score|results?|standings?)\b",
    r"\b(search|look up|google)\b",
    r"\b(released?|launched?|announced?)\b",
    r"\b(final|winner|champion|trophy)\b",
]

def needs_web_search(message: str) -> bool:
    msg = message.lower()
    return any(re.search(p, msg) for p in WEB_TRIGGERS)

def web_search(query: str, max_results: int = 4) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return ""
        lines = ["[Web search results:]"]
        for r in results:
            title = r.get("title", "")
            body  = r.get("body", "")
            url   = r.get("href", "")
            lines.append(f"• {title}: {body} ({url})")
        return "\n".join(lines)
    except Exception:
        return ""

# ── RAG: search memory ────────────────────────────────────────────────────────
def search_memory(query: str, n=5) -> str:
    """
    Pull more candidates than needed, score each by relevance + recency,
    return only the top results above a quality threshold.
    """
    candidates = []
    now_ts = datetime.now(timezone.utc).timestamp()

    for col, label in [
        (col_knowledge, "Past conversation"),
        (col_facts,     "Things you've said"),
        (col_style,     "Your writing style"),
        (col_documents, "Your documents"),
    ]:
        try:
            hits = col.query(
                query_texts=[query],
                n_results=n,
                include=["documents", "distances", "metadatas"]
            )
            docs      = hits["documents"][0]
            distances = hits["distances"][0]
            metadatas = hits["metadatas"][0]

            for doc, dist, meta in zip(docs, distances, metadatas):
                if not doc.strip():
                    continue

                # Relevance score: convert L2 distance → 0-1 (lower distance = higher score)
                relevance = 1 / (1 + dist)

                # Recency score: memories from the last 7 days score highest
                try:
                    created_ts = datetime.fromisoformat(meta.get("created_at", "")).timestamp()
                    age_days = (now_ts - created_ts) / 86400
                    recency = math.exp(-age_days / 7)  # decays over ~7 days
                except Exception:
                    recency = 0.5

                # Boost facts/documents slightly over raw conversation chunks
                type_boost = 1.15 if label in ("Things you've said", "Your documents") else 1.0

                final_score = (relevance * 0.7 + recency * 0.3) * type_boost

                candidates.append((final_score, label, doc.strip()))

        except Exception:
            pass

    # Sort by score descending, filter low quality, take top 6
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = [(label, doc) for score, label, doc in candidates if score > 0.3][:6]

    if not top:
        return ""

    return "\n\n".join(f"[{label}]: {doc}" for label, doc in top)

# ── System prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(memory_context: str, web_context: str, sheets_context: str = "") -> str:
    base = """You are Lucchese, a personal AI assistant for Alex Hammond.
Alex runs PTPreps — a meal prep business based in the UK that sells high protein prepared meals in standard and bulking portions, available as one-time purchases or subscriptions via Shopify. Meals rotate regularly and are listed on the Google Sheets data you have access to.
Alex is also a personal trainer, into bodybuilding and martial arts, and is building this AI tool to automate his business operations.
Be direct, smart, and conversational. Match Alex's tone.
Don't repeat yourself or over-explain.
Never guess or fabricate information about PTPreps, recipes, or macros — only use the Google Sheets data provided. If something isn't in the data, say so.
If you don't know something current like sports results, news, or prices — say so honestly.
When you use web search results, cite them naturally.
For ANY question about meals, ingredients, macros, or allergens — ONLY use the Google Sheets data provided. If a meal is not in the Sheets data, say "I don't have that meal in our current menu." Never use memory or training knowledge for food/menu questions."""

    sections = [base]

    if memory_context:
        sections.append(f"""Relevant context from Alex's memory and documents:
---
{memory_context}
---
Use this to inform your response where relevant, but don't quote it back verbatim.""")

    if sheets_context:
        sections.append(f"""Live data from PTPREPS Google Sheets:
---
{sheets_context}
---
Use this for any questions about recipes, ingredients, macros, or allergens.""")

    if web_context:
        sections.append(f"""Current information from the web:
---
{web_context}
---
Use ONLY this data for current events. Do not mix with your training knowledge.""")

    return "\n\n".join(sections)

# ── Request models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:         str
    history:         Optional[list] = []
    conversation_id: Optional[str]  = None
    deep:            Optional[bool] = False

class ShopifyMealRequest(BaseModel):
    meal_name: str

# ── Shopify helpers ───────────────────────────────────────────────────────────
def calc_macros(meal):
    totals = {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0}
    for i in meal['ingredients']:
        try:
            totals["kcal"]    += float(i['kcal'] or 0)
            totals["protein"] += float(i['protein'] or 0)
            totals["carbs"]   += float(i['carbs'] or 0)
            totals["fat"]     += float(i['fat'] or 0)
        except:
            pass
    return totals

def normalise_meal_name(name: str) -> str:
    return name.lower().replace(' & ', ' and ').replace('&', 'and').strip()

# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())

    # ── Shopify command intercept ─────────────────────────────────────────────
    shopify_match = re.search(r'shopify add (.+)|add (.+) to shopify', req.message.lower())
    if shopify_match:
        meal_name = (shopify_match.group(1) or shopify_match.group(2)).strip()
        standard_recipes = get_recipes('Standard Recipe')
        bulking_recipes  = get_recipes('Bulking Recipes')
        matched = next((m for m in standard_recipes if normalise_meal_name(m) == normalise_meal_name(meal_name)), None)
        if not matched:
            reply = f"Couldn't find '{meal_name}' in the recipe sheet. Check the exact meal name and try again."
        else:
            standard_macros = calc_macros(standard_recipes[matched])
            bulking_macros  = calc_macros(bulking_recipes[matched]) if matched in bulking_recipes else standard_macros
            created = await _create_meal_products(matched, standard_macros, bulking_macros)
            reply = f"Done! Created 4 products for {matched} on Shopify:\n"
            for p in created: reply += f"  ✓ {p['title']}\n"
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        return {"reply": reply, "conversation_id": conversation_id, "web_search_used": False}

    # ── Memory command intercept ──────────────────────────────────────────────
    command, content = detect_memory_command(req.message)
    if command:
        reply = await handle_memory_command(command, content, conversation_id)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        return {
            "reply": reply,
            "conversation_id": conversation_id,
            "web_search_used": False,
            "auto_ingested": command == "remember",
        }

    # ── Normal chat flow ──────────────────────────────────────────────────────
    did_search = needs_web_search(req.message)
    web        = web_search(req.message) if did_search else ""
    memory     = "" if did_search else search_memory(req.message)
    sheets     = get_menu_context(req.message)

    messages = [{"role": "system", "content": build_system_prompt(memory, web, sheets)}]
    messages += req.history
    messages.append({"role": "user", "content": req.message})

    save_message(conversation_id, "user", req.message)

    async def stream_response():
        full_reply = []

        # First chunk carries metadata so frontend knows the conversation_id
        yield json.dumps({
            "type": "meta",
            "conversation_id": conversation_id,
            "web_search_used": did_search,
        }) + "\n"

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", OLLAMA_URL, json={
                "model": MODEL_DEEP if req.deep else MODEL_FAST,
                "messages": messages,
                "stream": True,
            }) as response:
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_reply.append(token)
                            yield json.dumps({"type": "token", "content": token}) + "\n"
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue

        # Done — save and run post-processing
        reply = "".join(full_reply)
        save_message(conversation_id, "assistant", reply)

        user_corrections = ['we already', 'actually', "that's wrong", 'not quite',
                            'to clarify', "we don't", 'we do', 'i am', "i'm not"]
        force_ingest = any(s in req.message.lower() for s in user_corrections)

        if force_ingest:
            auto_ingest = True
            await ingest_exchange(conversation_id, req.message, reply)
        elif not did_search:
            auto_ingest = await should_ingest(req.message, reply)
            if auto_ingest:
                await ingest_exchange(conversation_id, req.message, reply)
        else:
            auto_ingest = False

        yield json.dumps({"type": "done", "auto_ingested": auto_ingest}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/x-ndjson")

# ── Shopify endpoint ──────────────────────────────────────────────────────────
@app.post("/shopify/add-meal")
async def add_meal_to_shopify(req: ShopifyMealRequest):
    meal_name = req.meal_name.strip()
    standard_recipes = get_recipes('Standard Recipe')
    bulking_recipes  = get_recipes('Bulking Recipes')

    matched = next((m for m in standard_recipes if normalise_meal_name(m) == normalise_meal_name(meal_name)), None)
    if not matched:
        return {"error": f"Meal '{meal_name}' not found in Standard Recipe sheet"}

    standard_macros = calc_macros(standard_recipes[matched])
    bulking_macros  = calc_macros(bulking_recipes[matched]) if matched in bulking_recipes else standard_macros
    created = await _create_meal_products(matched, standard_macros, bulking_macros)

    return {
        "success": True,
        "meal": matched,
        "standard_macros": standard_macros,
        "bulking_macros": bulking_macros,
        "products_created": created,
    }

# ── Upload endpoint ───────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    contents = await file.read()
    filename = file.filename or "unknown"

    text = extract_text(contents, filename)
    if not text.strip():
        return {"error": "Could not extract text from file"}, 400

    doc_id      = uuid.uuid4().hex
    chunk_count = ingest_document(doc_id, filename, text)

    now = datetime.now(timezone.utc).isoformat()
    file_type = "pdf" if filename.lower().endswith(".pdf") else "text"
    con = get_con()
    con.execute(
        "INSERT INTO documents (id, filename, file_type, chunk_count, created_at) VALUES (?, ?, ?, ?, ?)",
        (doc_id, filename, file_type, chunk_count, now)
    )
    con.commit()
    con.close()

    return {
        "doc_id":      doc_id,
        "filename":    filename,
        "chunk_count": chunk_count,
        "message":     f"Ingested {chunk_count} chunks from {filename}",
    }

@app.get("/documents")
def list_documents():
    con = get_con()
    rows = con.execute(
        "SELECT id, filename, file_type, chunk_count, created_at FROM documents ORDER BY created_at DESC"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    results = col_documents.get(where={"doc_id": doc_id})
    if results["ids"]:
        col_documents.delete(ids=results["ids"])

    con = get_con()
    con.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    con.commit()
    con.close()

    return {"deleted": doc_id}

# ── History endpoints ─────────────────────────────────────────────────────────
@app.get("/conversations")
def list_conversations():
    con = get_con()
    rows = con.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    con = get_con()
    rows = con.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
        (conversation_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    # Remove from ChromaDB memory
    for col in [col_knowledge, col_facts, col_style]:
        try:
            results = col.get(where={"conv_id": conversation_id})
            if results["ids"]:
                col.delete(ids=results["ids"])
        except:
            pass

    # Remove from SQLite
    con = get_con()
    con.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    con.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    con.commit()
    con.close()
    return {"deleted": conversation_id}

# ── Feedback endpoint ─────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    conversation_id: str
    user_message: str
    assistant_reply: str
    rating: str  # "good" or "bad"

@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    if req.rating == "good":
        await ingest_exchange(req.conversation_id, req.user_message, req.assistant_reply)
        return {"ingested": True}
    else:
        # On bad rating, try to remove if already ingested
        try:
            results = col_knowledge.get(where={"conv_id": req.conversation_id})
            if results["ids"]:
                col_knowledge.delete(ids=results["ids"])
        except:
            pass
        return {"ingested": False}

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(tmp_fd, "wb") as tmp:
                tmp.write(contents)
            result = whisper_model.transcribe(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return {"text": result["text"].strip()}
    except Exception as e:
        return {"error": str(e)}


# ── Text to Speech endpoint ───────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str

@app.post("/tts")
async def text_to_speech(req: TTSRequest):
    try:
        audio = el_client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=req.text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        audio_bytes = b"".join(audio)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"}
        )
    except Exception as e:
        return {"error": str(e)}

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "knowledge": col_knowledge.count(),
        "facts":     col_facts.count(),
        "style":     col_style.count(),
        "documents": col_documents.count(),
    }