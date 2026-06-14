"""
storage/sqlite/repositories/conversation_store/
Per-table repositories for the canonical conversation store (Rule 9, Rule 23).

Each module owns insert/lookup for one table in conversation_store.db, using
storage.sqlite.connection.session(CONVERSATION_STORE_DB). Repositories accept plain
args/dicts and never import from ingestion/ — storage stays decoupled from the
pipeline (Rule 21).
"""
