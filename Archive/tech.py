import chromadb
from chromadb.utils import embedding_functions
from collections import Counter

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="nomic-ai/nomic-embed-text-v1", trust_remote_code=True
)
chroma = chromadb.PersistentClient(path="./chroma_db")
col = chroma.get_or_create_collection("knowledge", embedding_function=ef)

results = col.get(where={"category": "tech"}, include=["documents", "metadatas"])
print(f"Total tech entries: {len(results['ids'])}")

# Print first 20 to get a feel
for doc in results["documents"][:20]:
    print("---")
    print(doc[:200])