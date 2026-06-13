// Message text helpers (Rule 10/22: pure helper).
// Splits assistant text into sentence chunks for streaming TTS — the logic that
// drove flushTTSSentence() in App.jsx send(). Audio playback itself lives in
// audio/playback.js; this is just the pure text-splitting part.

// Pulls complete sentences off the front of `buffer`, returning the sentences
// found and the remaining (incomplete) tail. With force=true, any leftover tail
// is flushed as a final sentence.
export function takeSentences(buffer, force = false) {
  const sentenceEnd = /[.!?]\s/g;
  const sentences = [];
  let match;
  let lastIndex = 0;

  while ((match = sentenceEnd.exec(buffer)) !== null) {
    const sentence = buffer.slice(lastIndex, match.index + 1).trim();
    if (sentence) sentences.push(sentence);
    lastIndex = match.index + 2;
  }

  let rest = lastIndex > 0 ? buffer.slice(lastIndex) : buffer;
  if (force && rest.trim()) {
    sentences.push(rest.trim());
    rest = "";
  }

  return { sentences, rest };
}
