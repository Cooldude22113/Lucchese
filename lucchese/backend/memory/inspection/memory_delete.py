"""
memory/inspection/memory_delete.py
Deletion helpers across ChromaDB collections (Rule 7/17).

Shared by conversation deletion, document deletion, and admin source purges. All
ChromaDB deletes are best-effort and logged, never raising to the caller.
"""

from __future__ import annotations

from memory.collections.collection_registry import (
    get_documents,
    get_facts,
    get_knowledge,
    get_style,
)


def purge_conversation(conversation_id: str) -> None:
    """Delete all memory entries for a conversation from knowledge/facts/style."""
    for col in (get_knowledge(), get_facts(), get_style()):
        try:
            results = col.get(where={"conv_id": conversation_id})
            if results["ids"]:
                col.delete(ids=results["ids"])
        except Exception as e:
            print(f"purge_conversation error: {e}")


def delete_document_chunks(doc_id: str) -> None:
    """Delete all chunks of an uploaded document from the documents collection."""
    try:
        results = get_documents().get(where={"doc_id": doc_id})
        if results["ids"]:
            get_documents().delete(ids=results["ids"])
    except Exception as e:
        print(f"delete_document_chunks error: {e}")


def delete_by_source(source: str) -> int:
    """Delete all entries from a given source across knowledge/facts/style. Returns count."""
    deleted = 0
    for col in (get_knowledge(), get_facts(), get_style()):
        try:
            results = col.get(where={"source": source})
            if results["ids"]:
                col.delete(ids=results["ids"])
                deleted += len(results["ids"])
        except Exception as e:
            print(f"delete_by_source error: {e}")
    return deleted
