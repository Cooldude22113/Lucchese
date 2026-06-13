// Chat state + streaming + voice mode (Rule 19). From App.jsx ChatApp.
// Owns the message list, the streamed send(), mic dictation and streamed TTS.
// Transport lives in chatApi/voiceApi; audio mechanics in audio/*.
import { useState, useRef, useEffect, useCallback } from "react";
import { streamChat } from "../../api/chatApi";
import { getConversation } from "../../api/conversationApi";
import { transcribe, tts } from "../../api/voiceApi";
import { startRecording } from "../../audio/recorder";
import { playBlob, createPlaybackQueue } from "../../audio/playback";
import { takeSentences } from "../../utils/formatMessage";
import { AUDIO_ERRORS } from "../../utils/errors";

const GREETING = "Good to see you, Alex. What's on your mind?";

export function useChat({ activeId, setActiveId, onConversationsChanged }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastExchange, setLastExchange] = useState(null);

  // Voice-mode (chat) state
  const [voiceMode, setVoiceMode] = useState(false);
  const [recording, setRecording] = useState(false);
  const [audioError, setAudioError] = useState(null);
  const recorderRef = useRef(null);

  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Conversation loading (sets message content) ────────────────────────────
  const loadConversation = useCallback(async (id) => {
    const data = await getConversation(id);
    setMessages(data.map((m) => ({ role: m.role, content: m.content })));
    setActiveId(id);
  }, [setActiveId]);

  const newConversation = useCallback(() => {
    setActiveId(null);
    setMessages([{ role: "assistant", content: GREETING }]);
  }, [setActiveId]);

  // ── TTS playback of a sentence ──────────────────────────────────────────────
  const speakSentence = useCallback(async (sentence) => {
    if (!voiceMode || !sentence.trim()) return;
    try {
      setAudioError(null);
      const res = await tts(sentence);
      if (!res.ok) { setAudioError(AUDIO_ERRORS.ttsUnavailable); return; }
      const blob = await res.blob();
      await playBlob(blob, {
        onError: (kind) =>
          setAudioError(kind === "decode" ? AUDIO_ERRORS.decode : AUDIO_ERRORS.playRetry),
      });
    } catch {
      setAudioError(AUDIO_ERRORS.playRetry);
    }
  }, [voiceMode]);

  // ── Send a message (streamed reply + streamed TTS) ──────────────────────────
  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    let ttsBuffer = "";
    const queue = createPlaybackQueue(speakSentence);
    const flush = (force = false) => {
      const { sentences, rest } = takeSentences(ttsBuffer, force);
      ttsBuffer = rest;
      if (voiceMode) sentences.forEach((s) => queue.enqueue(s));
    };

    let fullReply = "";
    let bubbleAdded = false;

    try {
      await streamChat({ message: text, history, conversation_id: activeId }, (chunk) => {
        if (chunk.type === "meta") {
          if (!activeId) setActiveId(chunk.conversation_id);
          if (!bubbleAdded) {
            setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
            bubbleAdded = true;
          }
        }
        if (chunk.type === "token") {
          fullReply += chunk.content;
          ttsBuffer += chunk.content;
          flush();
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: fullReply };
            return updated;
          });
        }
        if (chunk.type === "done") {
          setLastExchange({
            conversation_id: activeId,
            user_message: text,
            assistant_reply: fullReply,
            auto_ingested: chunk.auto_ingested,
          });
          flush(true);
          onConversationsChanged?.();
        }
      });
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Something went wrong connecting to the backend." }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [input, loading, messages, activeId, setActiveId, voiceMode, speakSentence, onConversationsChanged]);

  const onKey = useCallback((e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }, [send]);

  // ── Mic dictation (fills the input box via /transcribe) ─────────────────────
  const toggleRecording = useCallback(async () => {
    if (recording) {
      setRecording(false);
      try {
        const { blob, ext } = await recorderRef.current.stop();
        const data = await transcribe(blob, ext);
        if (data.text) setInput(data.text);
      } catch (err) {
        console.error("Transcribe error:", err);
      }
    } else {
      try {
        recorderRef.current = await startRecording();
        setRecording(true);
      } catch (err) {
        console.error("Mic error:", err);
        alert("Microphone access denied or unavailable.");
      }
    }
  }, [recording]);

  const toggleVoiceMode = useCallback(() => setVoiceMode((v) => !v), []);

  return {
    // chat bundle
    messages, input, setInput, loading, lastExchange,
    send, onKey, loadConversation, newConversation, bottomRef, inputRef,
    // voice bundle
    voiceMode, toggleVoiceMode, recording, toggleRecording, audioError,
  };
}
