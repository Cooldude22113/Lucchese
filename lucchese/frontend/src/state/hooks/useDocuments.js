// Document state (Rule 19). From App.jsx DocumentsPanel — list + upload + delete.
import { useState, useEffect, useCallback } from "react";
import { listDocuments, deleteDocument } from "../../api/documentApi";
import { uploadDocument } from "../../api/uploadApi";
import { isAllowedUpload } from "../../utils/validation";

export function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");

  const fetchDocs = useCallback(async () => {
    setDocuments(await listDocuments());
  }, []);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const upload = useCallback(async (file) => {
    if (!isAllowedUpload(file)) {
      setUploadMsg("Only PDF, TXT, and MD files supported.");
      return;
    }
    setUploading(true);
    setUploadMsg("Uploading and ingesting...");
    try {
      const data = await uploadDocument(file);
      setUploadMsg(`✓ ${data.filename} — ${data.chunk_count} chunks ingested`);
      fetchDocs();
    } catch {
      setUploadMsg("Upload failed. Check backend.");
    } finally {
      setUploading(false);
    }
  }, [fetchDocs]);

  const remove = useCallback(async (id) => {
    await deleteDocument(id);
    fetchDocs();
  }, [fetchDocs]);

  return { documents, uploading, uploadMsg, fetchDocs, upload, remove };
}
