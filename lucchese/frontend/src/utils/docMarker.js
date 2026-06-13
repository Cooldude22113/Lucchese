// Document-generation marker parsing (Rule 10/22: pure helper).
// From App.jsx Message: the assistant can embed `[GENERATE_DOC: Title]` in its
// reply to offer a downloadable Word doc. These helpers detect it and strip it
// from the text shown to the user.

export const DOC_MARKER = /\[GENERATE_DOC:\s*([^\]]+)\]/i;

// Returns the doc title if the marker is present, otherwise null.
export function extractDocTitle(content) {
  const match = content.match(DOC_MARKER);
  return match ? match[1].trim() : null;
}

// Removes the marker and collapses the gap it leaves behind.
export function stripDocMarker(content) {
  return content
    .replace(DOC_MARKER, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
