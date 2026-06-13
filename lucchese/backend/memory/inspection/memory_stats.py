"""
memory/inspection/memory_stats.py
Read-only collection counts and metadata breakdowns (Rule 17).
"""

from __future__ import annotations

from memory.inspection.memory_dump import COLLECTIONS, get_col


def cmd_stats(client):
    print(f"\n{'='*70}")
    print("  COLLECTION COUNTS")
    print(f"{'='*70}")
    for name in COLLECTIONS:
        col = get_col(client, name)
        count = col.count() if col else 0
        label = "(not found)" if not col else f"{count:,}"
        print(f"  {name:<14}: {label}")

    col_k = get_col(client, "knowledge")
    if not col_k or col_k.count() == 0:
        return

    print(f"\n{'='*70}")
    print("  KNOWLEDGE BREAKDOWN  (scanning full collection - may take a moment)")
    print(f"{'='*70}")

    try:
        all_entries = col_k.get(limit=100_000, include=["metadatas"])
        metas = all_entries["metadatas"]

        routing_counts = {"done": 0, "pending": 0, "other": 0}
        tier_counts: dict = {}
        source_counts: dict = {}
        ontology_counts: dict = {}

        for m in metas:
            rd = m.get("routing_done", "")
            if rd == "true":
                routing_counts["done"] += 1
            elif rd == "false":
                routing_counts["pending"] += 1
            else:
                routing_counts["other"] += 1

            t = m.get("primary_tier1", "unknown")
            tier_counts[t] = tier_counts.get(t, 0) + 1

            s = m.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

            o = m.get("ontology", "")
            if o:
                ontology_counts[o] = ontology_counts.get(o, 0) + 1

        print(f"\nRouting done   : {routing_counts['done']:,}")
        print(f"Routing pending: {routing_counts['pending']:,}")

        print("\n-- Tier1 distribution --")
        for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
            print(f"  {tier:<25}: {count:,}")

        print("\n-- Source distribution --")
        for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            print(f"  {src:<20}: {count:,}")

        if ontology_counts:
            print("\n-- Ontology distribution (knowledge) --")
            for ont, count in sorted(ontology_counts.items(), key=lambda x: -x[1]):
                print(f"  {ont:<20}: {count:,}")

    except Exception as e:
        print(f"  Error scanning knowledge: {e}")

    col_f = get_col(client, "facts")
    if col_f and col_f.count() > 0:
        print(f"\n{'='*70}")
        print("  FACTS BREAKDOWN")
        print(f"{'='*70}")
        try:
            all_facts = col_f.get(limit=100_000, include=["metadatas"])
            fmetas = all_facts["metadatas"]

            f_ontology: dict = {}
            f_tier: dict = {}
            f_personal = {"true": 0, "false": 0, "unknown": 0}
            f_source: dict = {}

            for m in fmetas:
                o = m.get("ontology", "")
                f_ontology[o or "none"] = f_ontology.get(o or "none", 0) + 1

                t = m.get("primary_tier1", "unknown")
                f_tier[t] = f_tier.get(t, 0) + 1

                p = str(m.get("is_personal", "")).lower()
                if p == "true":
                    f_personal["true"] += 1
                elif p == "false":
                    f_personal["false"] += 1
                else:
                    f_personal["unknown"] += 1

                s = m.get("source", "unknown")
                f_source[s] = f_source.get(s, 0) + 1

            print("\n-- Ontology distribution (facts) --")
            for ont, count in sorted(f_ontology.items(), key=lambda x: -x[1]):
                print(f"  {ont:<20}: {count:,}")

            print("\n-- Tier1 distribution (facts) --")
            for tier, count in sorted(f_tier.items(), key=lambda x: -x[1]):
                print(f"  {tier:<25}: {count:,}")

            print("\n-- is_personal (facts) --")
            print(f"  true   : {f_personal['true']:,}")
            print(f"  false  : {f_personal['false']:,}")
            print(f"  unknown: {f_personal['unknown']:,}")

            print("\n-- Source distribution (facts) --")
            for src, count in sorted(f_source.items(), key=lambda x: -x[1]):
                print(f"  {src:<20}: {count:,}")

        except Exception as e:
            print(f"  Error scanning facts: {e}")
