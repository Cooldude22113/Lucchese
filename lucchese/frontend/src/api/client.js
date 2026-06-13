// Shared backend client (Rule 19: api/ talks to backend; Rule 21: one-way deps).
// Every domain api module goes through these helpers so base-URL joining,
// headers and response parsing live in exactly one place.

import { API_URL, ADMIN_KEY } from "../app/appConfig";

function url(path) {
  return `${API_URL}${path}`;
}

function adminHeaders(extra = {}) {
  return { "X-Admin-Key": ADMIN_KEY, ...extra };
}

async function parse(res) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

// ── JSON ────────────────────────────────────────────────────────────────────
export async function getJSON(path, { admin = false } = {}) {
  const res = await fetch(url(path), {
    headers: admin ? adminHeaders() : undefined,
  });
  return parse(res);
}

export async function postJSON(path, body, { admin = false } = {}) {
  const res = await fetch(url(path), {
    method: "POST",
    headers: admin
      ? adminHeaders({ "Content-Type": "application/json" })
      : { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function del(path, { admin = false } = {}) {
  const res = await fetch(url(path), {
    method: "DELETE",
    headers: admin ? adminHeaders() : undefined,
  });
  return parse(res);
}

// ── Multipart upload ─────────────────────────────────────────────────────────
export async function postForm(path, formData) {
  return fetch(url(path), { method: "POST", body: formData });
}

// ── Raw helpers (callers that need the Response itself) ──────────────────────
export async function postRaw(path, body) {
  return fetch(url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function downloadUrl(path) {
  return url(path);
}

// ── NDJSON stream reader ─────────────────────────────────────────────────────
// Lifted from App.jsx send(): reads a streamed response line by line and
// invokes onChunk for every parsed JSON object. Transport only — callers decide
// what to do with each chunk.
export async function streamNDJSON(path, body, onChunk) {
  const res = await postRaw(path, body);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        onChunk(JSON.parse(line));
      } catch {
        continue;
      }
    }
  }
}
