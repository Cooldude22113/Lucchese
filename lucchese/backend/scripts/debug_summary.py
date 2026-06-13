"""
scripts/debug_summary.py
Manual dump of the "tech" category summaries (Rule 18: scripts call real modules).

    python -m scripts.debug_summary
"""

from __future__ import annotations

from memory.collections.collection_registry import get_summaries


def main() -> None:
    results = get_summaries().get(
        where={"category": "tech"},
        include=["documents", "metadatas"],
    )
    print(f"Tech summaries found: {len(results['ids'])}")
    for doc, meta in zip(results["documents"], results["metadatas"]):
        print("---")
        print(f"Category: {meta.get('category')}")
        print(doc)


if __name__ == "__main__":
    main()
