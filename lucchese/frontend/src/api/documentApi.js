// Document endpoints (Rule 19): listing, deletion, generation and download.
import { getJSON, del, postJSON, downloadUrl } from "./client";

export function listDocuments() {
  return getJSON("/documents");
}

export function deleteDocument(id) {
  return del(`/documents/${id}`);
}

// POST /generate-doc — returns { token, filename } (or { error }).
export function generateDoc({ content, title }) {
  return postJSON("/generate-doc", { content, title });
}

// Browser-openable URL for a generated document token.
export function docDownloadUrl(token) {
  return downloadUrl(`/download/${token}`);
}
