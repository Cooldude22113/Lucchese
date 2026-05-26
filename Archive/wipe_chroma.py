import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
for name in ['knowledge', 'facts', 'style', 'documents', 'summaries']:
    try:
        client.delete_collection(name)
        print(f'Deleted {name}')
    except Exception as e:
        print(f'{name} not found: {e}')
print('Done')