import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_collection("knowledge")
print(f"Knowledge entries: {col.count()}")
col2 = client.get_collection("summaries")
print(f"Summaries: {col2.count()}")