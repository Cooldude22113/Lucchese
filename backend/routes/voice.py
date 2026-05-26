"""
routes/voice.py
───────────────
Voice-related endpoints:
  POST /transcribe     — audio file → text (Whisper)
  POST /tts            — text → mp3 audio (ElevenLabs)
  POST /voice-chat     — audio file → transcribe → LLM → TTS → base64 response

Depends on shared state injected from main.py via init_voice_state().
Shares search_memory / should_ingest / ingest_exchange / save_message
with the chat route — those are passed in via state, not re-implemented here.
"""

import re
import os
import base64
import tempfile
import uuid
import httpx

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from routes.config import OLLAMA_URL, MODEL_FAST, CHAT_PROVIDER, ANTHROPIC_API_KEY, whisper_model, el_client, ELEVENLABS_VOICE_ID
from routes.memory import search_memory, should_ingest, ingest_exchange
from routes.database import save_message, get_conversation_history
from routes.chat import build_system_prompt

router = APIRouter()

# ── Audio transcription helper ────────────────────────────────────────────────
async def transcribe_audio(file: UploadFile) -> str:
    """Write upload to a temp file, run Whisper, return transcript."""
    contents     = await file.read()
    content_type = file.content_type or ""

    if   "mp4" in content_type or "m4a" in content_type: suffix = ".mp4"
    elif "ogg" in content_type:                           suffix = ".ogg"
    elif "wav" in content_type:                           suffix = ".wav"
    else:                                                 suffix = ".webm"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            tmp.write(contents)
        result = whisper_model.transcribe(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return result["text"].strip()


# ── /transcribe ───────────────────────────────────────────────────────────────
@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Audio file → plain text transcript."""
    try:
        text = await transcribe_audio(file)
        return {"text": text}
    except Exception as e:
        print(f"Transcribe error: {e}")
        return {"error": str(e)}


# ── /tts ──────────────────────────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str

@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    """Text → mp3 audio stream via ElevenLabs."""
    try:
        audio = el_client.text_to_speech.convert(
            voice_id      = ELEVENLABS_VOICE_ID,
            text          = req.text,
            model_id      = "eleven_turbo_v2_5",
            output_format = "mp3_44100_128",
        )
        audio_bytes = b"".join(audio)
        return Response(
            content    = audio_bytes,
            media_type = "audio/mpeg",
            headers    = {"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        return {"error": str(e)}


# ── TTS helper: clean text and chunk into speakable segments ──────────────────
def _prepare_tts_chunks(text: str) -> list[str]:
    """
    Strip non-latin characters (emojis etc), split on sentence boundaries,
    then merge short sentences so ElevenLabs gets natural-length chunks (>80 chars).
    """
    clean     = re.sub(r'[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF]+', ' ', text).strip()
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]

    merged, buf = [], ""
    for s in sentences:
        buf = (buf + " " + s).strip()
        if len(buf) > 80:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)

    return merged


# ── /voice-chat ───────────────────────────────────────────────────────────────
@router.post("/voice-chat")
async def voice_chat(file: UploadFile = File(...), conversation_id: str = None):
    """
    Full voice pipeline:
      1. Transcribe audio → text (Whisper)
      2. Pull memory context (RAG)
      3. Get LLM reply (Ollama)
      4. Save + optionally ingest to memory
      5. Convert reply to speech (ElevenLabs)
      6. Return transcript, reply text, and base64 audio
    """
    try:
        # 1. Transcribe
        user_text = await transcribe_audio(file)
        if not user_text:
            return JSONResponse(content={"error": "no speech detected"})

        conv_id = conversation_id or str(uuid.uuid4())

        # 2. Build context
        memory = await search_memory(user_text)

        system = build_system_prompt(memory, "", "")

        # Load last 20 messages for continuity
        history = get_conversation_history(conv_id, limit=20)

        messages = [{"role": "system", "content": system}]
        messages += history
        messages.append({"role": "user", "content": user_text})

        # 3. LLM reply — respects CHAT_PROVIDER setting
        if CHAT_PROVIDER == "claude":
            system_prompt = messages[0]["content"] if messages[0]["role"] == "system" else ""
            chat_messages = [m for m in messages if m["role"] != "system"]
            async with httpx.AsyncClient(timeout=300) as client:
                res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    json={
                        "model":      "claude-sonnet-4-6",
                        "max_tokens": 1024,
                        "system":     system_prompt,
                        "messages":   chat_messages,
                    }
                )
            reply_text = res.json()["content"][0]["text"]
        else:
            async with httpx.AsyncClient(timeout=300) as client:
                res = await client.post(
                    OLLAMA_URL,
                    json={
                        "model":    MODEL_FAST,
                        "messages": messages,
                        "stream":   False,
                    }
                )
            reply_text = res.json()["message"]["content"]


        # 4. Save + ingest
        save_message(conv_id, "user",      user_text)
        save_message(conv_id, "assistant", reply_text)
        if should_ingest(user_text, reply_text):
            await ingest_exchange(conv_id, user_text, reply_text)

        # 5. TTS — chunk reply and collect audio
        chunks      = _prepare_tts_chunks(reply_text)
        audio_bytes = b""
        for chunk in chunks:
            try:
                for piece in el_client.text_to_speech.convert(
                    voice_id      = ELEVENLABS_VOICE_ID,
                    text          = chunk,
                    model_id      = "eleven_turbo_v2_5",
                    output_format = "mp3_44100_128",
                ):
                    audio_bytes += piece
            except Exception as e:
                print(f"TTS chunk error: {e}")

        # 6. Return
        return JSONResponse(
            content={
                "transcript": user_text,
                "reply":      reply_text,
                "conv_id":    conv_id,
                "audio_b64":  base64.b64encode(audio_bytes).decode("utf-8"),
            },
            media_type="application/json; charset=utf-8",
        )

    except Exception as e:
        print(f"Voice chat error: {e}")
        return JSONResponse(content={"error": str(e)})
