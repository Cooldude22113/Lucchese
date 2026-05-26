import chromadb
import random

client = chromadb.PersistentClient(path="./chroma_db")
col_knowledge = client.get_collection("knowledge")
col_facts     = client.get_collection("facts")
col_style     = client.get_collection("style")

print(f"\nKnowledge: {col_knowledge.count()} total")
print(f"Facts    : {col_facts.count()} total")
print(f"Style    : {col_style.count()} total")

# Count classified vs unclassified
done   = col_knowledge.get(where={"routing_done": {"$eq": "true"}},   limit=1)
undone = col_knowledge.get(where={"routing_done": {"$eq": "false"}},  limit=1)
print(f"\nRouting done  : check log for running total")
print(f"Facts so far  : {col_facts.count()}")
print(f"Style so far  : {col_style.count()}")

# Sample from a specific tier — change this to explore
FILTER_TIER = "[personal]"   # try: health, business, finance, philosophy, society

OFFSET = 0  # change to 10, 20, 30 etc to page through entries

results = col_knowledge.get(
    where   = {"$and": [
        {"routing_done":  {"$eq": "true"}},
        {"primary_tier1": {"$eq": FILTER_TIER}},
    ]},
    limit   = 0,
    offset  = OFFSET,
    include = ["metadatas"],
)

print(f"\n── Sample from tier1='{FILTER_TIER}' ({len(results['metadatas'])} shown) ──")
for meta in results["metadatas"]:
    print(f"\n{'─'*60}")
    print(f"Title    : {meta.get('title', '')}")
    print(f"Source   : {meta.get('source','')} | Era: {meta.get('era','')}")
    print(f"Tier     : {meta.get('primary_tier1','')}/{meta.get('primary_tier2','')}/{meta.get('primary_tier3','')}")
    print(f"Ontology : {meta.get('ontology','')} | {meta.get('source_type','')}")
    print(f"Personal : {meta.get('is_personal','')} | Engagement: {meta.get('engagement','')}")
    print(f"Text     : {meta.get('user_text_raw','')[:500]}")
    print(f"Created  : {meta.get('created_at','')}")
    print(f"Ingested : {meta.get('ingested_at','')}")

# Show sample facts if any exist
if col_facts.count() > 0:
    facts = col_facts.get(limit=100, include=["documents", "metadatas"])
    print(f"\n── Sample facts ({col_facts.count()} total) ──")
    for doc, meta in zip(facts["documents"], facts["metadatas"]):
        print(f"\n  [{meta.get('source','')} | {meta.get('primary_tier1','')}]")
        print(f"  Created : {meta.get('created_at','')}")
        print(f"  Ingested: {meta.get('ingested_at','')}")
        print(f"  {doc[:200]}")

if col_style.count() > 0:
    styles = col_style.get(limit=0, include=["documents", "metadatas"])
    print(f"\n── Sample style ({col_style.count()} total) ──")
    for doc, meta in zip(styles["documents"], styles["metadatas"]):
        print(f"\n  [{meta.get('source','')} | {meta.get('primary_tier1','')}]")
        print(f"  {doc[:300]}")

# Check for same text in different tier classes
print("\n── Checking for same text in different tier classes ──")

from collections import defaultdict

scan = col_knowledge.get(
    where   = {"routing_done": {"$eq": "true"}},
    limit   = 500,
    include = ["metadatas"],
)

text_to_tiers = defaultdict(set)
for meta in scan["metadatas"]:
    text = meta.get("user_text_raw", "")[:100]
    tier = meta.get("primary_tier1", "")
    if text and tier:
        text_to_tiers[text].add(tier)

conflicts = {t: tiers for t, tiers in text_to_tiers.items() if len(tiers) > 1}
if conflicts:
    print(f"Found {len(conflicts)} texts in multiple tiers:")
    for text, tiers in list(conflicts.items())[:10]:
        print(f"\n  Text  : {text}")
        print(f"  Tiers : {tiers}")
else:
    print("No conflicts found.")