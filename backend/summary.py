import chromadb
from chromadb.utils import embedding_functions

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="nomic-ai/nomic-embed-text-v1", trust_remote_code=True
)
chroma = chromadb.PersistentClient(path="./chroma_db")
col = chroma.get_or_create_collection("summaries", embedding_function=ef)

results = col.get(
    where={"category": "tech"},
    include=["documents", "metadatas"]
)

print(f"Tech summaries found: {len(results['ids'])}")
for doc, meta in zip(results["documents"], results["metadatas"]):
    print("---")
    print(f"Category: {meta.get('category')}")
    print(doc)