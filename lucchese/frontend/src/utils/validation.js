// Input validation helpers (Rule 10/22: pure helper).
// From App.jsx DocumentsPanel.uploadFile — only PDF/TXT/MD uploads are allowed.

const ALLOWED_MIME = ["application/pdf", "text/plain", "text/markdown"];
const ALLOWED_EXT = [".pdf", ".txt", ".md"];

export function isAllowedUpload(file) {
  if (!file) return false;
  if (ALLOWED_MIME.includes(file.type)) return true;
  return ALLOWED_EXT.some((ext) => file.name.endsWith(ext));
}
