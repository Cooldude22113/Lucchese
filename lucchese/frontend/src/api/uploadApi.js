// Upload endpoint (Rule 19): multipart document ingestion.
import { postForm } from "./client";

// POST /upload — sends a single file as multipart form data.
export async function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await postForm("/upload", form);
  return res.json();
}
