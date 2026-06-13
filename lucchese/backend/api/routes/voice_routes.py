"""
api/routes/voice_routes.py
Thin voice endpoints (Rule 2, Rule 13):
  POST /transcribe  — audio → text (Whisper)
  POST /tts         — text → mp3 (ElevenLabs)
  POST /voice-chat  — audio → transcribe → LLM → TTS → base64 response
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, Response

from api.schemas.voice import TTSRequest
from application.orchestration.voice_flow import run_voice_chat
from audio.transcription.transcribe_audio import transcribe_audio
from model_runtime.providers import elevenlabs_provider

router = APIRouter()


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Audio file → plain text transcript."""
    try:
        text = await transcribe_audio(file)
        return {"text": text}
    except Exception as e:
        print(f"Transcribe error: {e}")
        return {"error": str(e)}


@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    """Text → mp3 audio stream via ElevenLabs."""
    try:
        audio_bytes = elevenlabs_provider.synthesise(req.text)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/voice-chat")
async def voice_chat(file: UploadFile = File(...), conversation_id: str = None):
    """Full voice pipeline: transcribe → reason → speak."""
    if not elevenlabs_provider.is_configured():
        return JSONResponse(content={"error": "ElevenLabs not configured"}, status_code=503)
    try:
        result = await run_voice_chat(file, conversation_id)
        return JSONResponse(
            content=result,
            media_type="application/json; charset=utf-8",
        )
    except Exception as e:
        print(f"Voice chat error: {e}")
        return JSONResponse(content={"error": str(e)})
