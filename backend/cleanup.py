import chromadb
from chromadb.utils import embedding_functions

ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
client = chromadb.PersistentClient(path="./chroma_db")

for name in ["knowledge", "facts", "style"]:
    col = client.get_collection(name, embedding_function=ef)
    results = col.get(where={"source": "lucchese"})
    ids = results["ids"]
    print(f"{name}: {len(ids)} lucchese entries found")
    if ids:
        col.delete(ids=ids)
        print(f"{name}: deleted.")

print("Done.")