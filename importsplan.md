# Canonical Conversation Shapes + DB Ingestion (ChatGPT, Grok, Lucchese)

## Context

The ingestion pipeline is the thing that **defines the canonical shape of all conversation
data** — it is not bent to fit the existing repo. Goal of this work: study both raw exports in
[data/imports/raw/](lucchese/backend/data/imports/raw/), design one **universal, full-fidelity
normalized shape** that fits ChatGPT, Grok **and** Lucchese's own conversations, and persist
**everything in the JSONs into a relational DB** — with special emphasis on the signals that
explain user/assistant **behaviour** (searches the assistant made, URLs, tool calls, citations,
attachments, models, reasoning).

Scope guardrails from the user:
- **`conversation_store.db` IS fully written.** The importer runs plain relational `INSERT`s for
  every conversation, message, and behavioural row (tool calls, searches, URLs, attachments,
  reasoning). Filling this SQLite store is the whole deliverable.
- **No *embedding* yet — that is a different thing.** "Embedding" = turning text into numeric
  **vectors** for a **vector DB (ChromaDB)** to enable semantic search. That vector step — and
  `memory/`, `exchange_ingestor`, classification — is skipped / out of scope. Writing rows to the
  SQLite store is **not** embedding and is fully in scope.
- **IDs are cut down to a single integer.** Original UUIDs are replaced by sequential integer
  PKs; the old IDs are stored so rows can be **paired** (parent/child links re-resolved from old
  IDs to new integer IDs).
- **Universal shape.** The same tables hold ChatGPT, Grok, and (later) Lucchese conversations.

Confirmed decisions: **new universal tables** (live `conversations`/`messages` stay as-is; the live
chat path migrates onto the canonical schema as a follow-up — nothing breaks now) · **store the
full ChatGPT message tree** (branches/regenerations) with an `on_active_path` flag · **dedicated
normalized behavioural tables** (not JSON blobs).

## Raw formats (verified by introspection)

**ChatGPT** `conversations-*.json` (7 files) — JSON **array** of conversations. Conversation keys
include `id`/`conversation_id`, `title`, `create_time`/`update_time` (epoch float), `current_node`,
`default_model_slug`, `is_starred`, `is_archived`, `gizmo_type`, `memory_scope`, and `mapping`
(node_id → `{id, message, parent, children}`, a **tree**). Per-message: `author.{role,name}`
(roles user/assistant/system/**tool**; tool `name` ∈ python, web, myfiles_browser, dalle.text2im,
bio, canmore.*, research_kickoff_tool), `recipient` (routing target), `content.content_type`
(text, multimodal_text, code, execution_output, tether_quote, tether_browsing_display,
system_error), and `metadata` carrying **model_slug**, **citations**/**content_references**,
**search_result_groups** (`entries[].{url,title,snippet,domain,pub_date}`), **safe_urls**,
**command**, **attachments** (`{id,name,mime_type,size,width,height}`), `finish_details`,
`is_visually_hidden_from_conversation`. `tether_quote` = `{url,domain,title,text}`;
`multimodal_text.parts` = strings + `image_asset_pointer` dicts.

**Grok** `prod-grok-backend.json` — `{conversations:[{conversation, responses}]}`, 210 items.
`conversation`: `id`, `title`, `summary`, ISO `create_time`/`modify_time`, `system_prompt_name`,
`starred`, `leaf_response_id`, `asset_ids`, `temporary`, `media_types`. `responses[].response`:
`_id`, `message`, `sender` (**human / assistant / ASSISTANT** — casing varies), `model`
(grok-4-auto, grok-3, grok-4), `create_time` = Mongo `{"$date":{"$numberLong":"<ms>"}}`,
`parent_response_id` (**threading**), `metadata` (`request_metadata.{model,mode,effort}`,
`ui_layout`, `llm_info`), and behavioural arrays: **web_search_results**
(`{url,title,preview,site_name,favicon,...}`), **agent_thinking_traces**/**steps**/**thinking_trace**
(embed `<xai:tool_usage_card><xai:tool_name>web_search</xai:tool_name><xai:tool_args>{"query":…,"num_results":…}</xai:tool_args>`),
**file_attachments** (asset id strings), **generated_image_urls**, **xpost_ids**, `query`/`query_type`.
Message text embeds `<grok:render type="render_inline_citation">` (1179) and
`render_searched_image` (273) cards. ~2 conversations have empty `responses`.

## The canonical shape (normalized model)

Dataclasses defined in **`ingestion/parsing/normalized_models.py`** — the parse target and the
single source of truth for the shape (the DB DDL mirrors it field-for-field). Behavioural records
hang off each message so a parser emits one self-contained bundle.

```python
@dataclass
class ParsedConversation:
    source: str                      # 'chatgpt' | 'grok' | 'lucchese'
    source_conversation_id: str      # original UUID — kept for pairing
    title: str | None
    summary: str | None
    created_at: str                  # ISO-8601 UTC
    updated_at: str | None
    default_model: str | None
    system_prompt_name: str | None
    starred: bool
    archived: bool
    source_metadata: dict            # full-fidelity catch-all (everything not promoted)
    messages: list[ParsedMessage]

@dataclass
class ParsedMessage:
    source_message_id: str
    source_parent_id: str | None     # old parent id — resolved to integer parent_id on insert
    role: str                        # user | assistant | system | tool
    author_name: str | None          # tool name (python/web/dalle/bio/canmore/...)
    content_type: str                # text|multimodal_text|code|execution_output|tether_quote|...
    text: str | None                 # cleaned display text
    raw_text: str | None             # original pre-clean text (fidelity)
    model: str | None                # model_slug / grok model
    recipient: str | None            # chatgpt routing target
    status: str | None
    end_turn: bool | None
    weight: float | None
    on_active_path: bool             # on the kept thread (current_node / leaf chain)
    is_hidden: bool
    created_at: str | None
    updated_at: str | None
    source_metadata: dict
    tool_calls:        list[ParsedToolCall]
    web_searches:      list[ParsedWebSearch]
    search_results:    list[ParsedSearchResult]
    attachments:       list[ParsedAttachment]
    reasoning_traces:  list[ParsedReasoningTrace]

# behavioural records (abbreviated)
ParsedToolCall(tool_name, command, arguments: dict, created_at)
ParsedWebSearch(query, num_results, search_source, created_at)
ParsedSearchResult(kind, url, domain, title, snippet, pub_date, rank)   # kind: search_result|citation|tether_quote|safe_url|xpost|image
ParsedAttachment(kind, source_asset_id, name, mime_type, url, size, width, height)  # kind: upload|generated_image|image_asset_pointer|file
ParsedReasoningTrace(kind, content, started_at, ended_at, seq)          # kind: thinking_trace|agent_thinking_trace|step
```

Storage stays decoupled from ingestion (Rule 21): the pipeline maps these dataclasses to plain
repository call args, so `storage/` never imports `ingestion/`.

## The DB (same shapes) — new `conversation_store.db`

A **new** SQLite file `backend/data/sqlite/conversation_store.db` (constant `CONVERSATION_STORE_DB`
in `config/paths.py`), kept separate from the legacy `conversations.db` so integer-id canonical
tables don't collide with the live TEXT-id tables. At migration time this becomes the single
conversation store. DDL lives in **`storage/sqlite/conversation_store_schema.py`**
(`init_conversation_store_db()` + `EXPECTED_STORE_TABLES`, mirroring the existing
[schema.py](lucchese/backend/storage/sqlite/schema.py) pattern).

```sql
conversations(
  id INTEGER PK AUTOINCREMENT, source TEXT, source_conversation_id TEXT,
  title, summary, created_at, updated_at, default_model, system_prompt_name,
  starred INT, archived INT, message_count INT, source_metadata TEXT/*JSON*/, imported_at,
  UNIQUE(source, source_conversation_id))

messages(
  id INTEGER PK AUTOINCREMENT, conversation_id INT→conversations,
  source_message_id TEXT, parent_id INT→messages /*resolved from old id*/,
  role, author_name, content_type, text, raw_text, model, recipient, status,
  end_turn INT, weight REAL, sequence INT, on_active_path INT, is_hidden INT,
  created_at, updated_at, source_metadata TEXT/*JSON*/,
  UNIQUE(conversation_id, source_message_id))
  -- INDEX(conversation_id), INDEX(parent_id)

tool_calls(id PK, conversation_id→, message_id→, source, tool_name, command, arguments/*JSON*/, created_at)
web_searches(id PK, conversation_id→, message_id→, source, query, num_results INT, search_source, created_at)
search_results(id PK, conversation_id→, message_id→, web_search_id→web_searches,
               source, kind, url, domain, title, snippet, pub_date, rank INT, created_at)  -- INDEX(domain)
attachments(id PK, conversation_id→, message_id→, source, kind, source_asset_id,
            name, mime_type, url, size INT, width INT, height INT, created_at)
reasoning_traces(id PK, conversation_id→, message_id→, source, kind, content, started_at, ended_at, seq INT)

id_map(source, entity_type /*conversation|message*/, source_id, new_id INT,
       PRIMARY KEY(source, entity_type, source_id))         -- pairing + idempotency
import_runs(id PK, source, started_at, finished_at, files/*JSON*/,
            conversations_imported INT, messages_imported INT, errors INT, report/*JSON*/)
```

## ID strategy ("one number", paired by old id)

1. Insert the conversation → SQLite assigns the integer `id`; record `id_map(source,'conversation',old_uuid,new_id)`.
2. Insert each message **without** `parent_id` first; record `id_map(source,'message',old_node_id,new_id)`.
3. After all messages for the conversation are inserted, **resolve** `parent_id` for each by looking
   up `id_map[old parent id]` and `UPDATE`. This is the "paired based on the old ids" step — works
   for both ChatGPT `parent` and Grok `parent_response_id`, including branches.
4. **Idempotency/resume:** `UNIQUE(source, source_conversation_id)` + `id_map`; importer skips any
   conversation whose `(source, id)` already exists. Re-running imports nothing new.

## Source → canonical mapping (what populates each table)

| Canonical | ChatGPT origin | Grok origin |
|---|---|---|
| conversations.* | `id`/`title`/`create_time`/`update_time`/`default_model_slug`/`is_starred`/`is_archived`; rest → `source_metadata` | `conversation.{id,title,summary,create_time,modify_time,system_prompt_name,starred}`; rest → `source_metadata` |
| messages (full tree) | every `mapping` node with a `message`; `parent` = node parent; `on_active_path` = node on `current_node`→root walk | every `responses[].response`; `parent_id` = `parent_response_id`; `on_active_path` = leaf_response_id chain |
| messages.text / raw_text | `content.parts`/`text` joined; raw kept | `message` cleaned of `<grok:render>`/`<xai:*>`; raw kept |
| tool_calls | `author.name` + `recipient` + `metadata.command` (+ `code` text as args) | `<xai:tool_usage_card>` (tool_name + tool_args) from steps/thinking traces |
| web_searches | `metadata.search_result_groups` presence + `search_source`/`client_reported_search_source` | `<xai:tool_usage_card tool_name=web_search>` args `{query,num_results}`; `query`/`query_type` |
| search_results | `search_result_groups[].entries[]` (url/title/snippet/domain/pub_date), `tether_quote`, `safe_urls`, citations | `web_search_results[]` (url/title/preview/site_name), `render_inline_citation` cards, `xpost_ids` |
| attachments | `metadata.attachments[]`, `multimodal_text` `image_asset_pointer` parts (dalle) | `file_attachments[]`, `generated_image_urls[]`, `asset_ids` |
| reasoning_traces | (none) | `thinking_trace`, `agent_thinking_traces[]`, `steps[]` (+ thinking_start/end_time) |

## Files (placement per the rules)

**Config (Rule 1, 16)**
- Modify `config/paths.py` — add `CONVERSATION_STORE_DB`, `IMPORTS_DIR`/`IMPORTS_RAW_DIR`/`IMPORTS_PROCESSED_DIR`; add the dirs to `ensure_runtime_dirs()`.
- New `config/ingestion_settings.py` — tunables: `CHATGPT_GLOB="conversations-*.json"`, `GROK_FILENAME="prod-grok-backend.json"`, batch size, `ARCHIVE_AFTER_IMPORT`.

**Storage (Rule 9)** — canonical store, decoupled from legacy
- New `storage/sqlite/conversation_store_schema.py` — DDL above + `init_conversation_store_db()` + `EXPECTED_STORE_TABLES`.
- New subpackage `storage/sqlite/repositories/conversation_store/` (Rule 23): `conversations.py`, `messages.py`, `tool_calls.py`, `web_searches.py`, `search_results.py`, `attachments.py`, `reasoning_traces.py`, `id_map.py`, `import_runs.py` — each owns insert/lookup for its table, using `connection.session(CONVERSATION_STORE_DB)`. Repos accept plain args/dicts (no ingestion imports).
- New `storage/files/import_store.py` — `list_raw_files()` (glob raw dir), optional `archive()` to `IMPORTS_PROCESSED_DIR`.

**Ingestion — sources (Rule 8: load raw)**
- `ingestion/sources/json_source.py` (UTF-8 `load_json`), `chatgpt_source.py` (yield raw convs across the 7 files), `grok_source.py` (yield `{conversation, responses}`).

**Ingestion — parsing (Rule 8: raw → normalized; isolate format quirks)**
- `ingestion/parsing/normalized_models.py` — the dataclasses above.
- `ingestion/parsing/chatgpt_parser.py` — walk `mapping`, emit every node as `ParsedMessage`, set `parent`/`on_active_path` (current_node walk), dispatch by `content_type`.
- `ingestion/parsing/chatgpt_content.py` — interpret content + `metadata` → text + behavioural records (search_result_groups/citations/safe_urls/attachments/command/code).
- `ingestion/parsing/grok_parser.py` — normalise `sender` casing → role; Mongo `$date`→ISO; thread via `parent_response_id`/`leaf_response_id`.
- `ingestion/parsing/grok_tags.py` — parse/strip `<xai:tool_usage_card>` (→ web_searches/tool_calls), `render_inline_citation` (→ search_results), `render_searched_image` (→ attachments).
- `ingestion/parsing/metadata_parser.py` (shared field/timestamp helpers: `epoch_to_iso`, `mongo_date_to_iso`), `parse_errors.py` (`ParseError`, `UnknownFormatError`).

**Ingestion — cleaning (Rule 8)**
- `text_cleaner.py` (orchestrates), `noise_filter.py` (strip render/xai tags, collapse blank lines), `normaliser.py` (Unicode NFC, smart quotes, trim, fix the `�`/`�`-style mojibake seen in tether_quote text), `duplicate_cleaner.py` (collapse consecutive dupes), `pii_filter.py` (conservative — Alex's own data; keep minimal).

**Ingestion — status (bookkeeping)**
- `status/import_job.py` (`ImportJob`), `import_report.py` (`ImportReport` → dict), `import_errors.py` (per-item capture), `import_status.py` (reads `import_runs`/`id_map` for the status endpoint).

**Ingestion — pipelines (Rule 8 + Rule 3)**
- `pipelines/conversation_pipeline.py` — one `ParsedConversation` → clean → persist conversation, messages, behavioural rows via the store repos → resolve `parent_id` from `id_map` → return counts.
- `pipelines/import_pipeline.py` — for `source` ∈ {chatgpt, grok, all}: source→parser→conversation_pipeline under one `import_runs` row, skipping already-imported convs, producing the `ImportReport`.

**Application (Rule 4 / Rule 3)**
- `application/services/import_service.py` — `async run_import(source="all") -> dict`; `import_status() -> dict`.
- `application/orchestration/import_flow.py` — `run_import_flow(source)`: `ensure_runtime_dirs()` + `init_conversation_store_db()`, log start/finish (`logging.getLogger(__name__)`), call service, return report.

**API (Rule 2) + Script (Rule 18)**
- Modify `api/routes/admin_routes.py` — `POST /admin/import` (`source: str = "all"`, `Depends(verify_admin_key)`) and `GET /admin/import/status`. (Matches the query-param admin style; `admin_routes` already registered in `app/router.py`.)
- `scripts/import_chatgpt.py` — unified argparse entrypoint: `python -m scripts.import_chatgpt [--source chatgpt|grok|all] [--dry-run] [--log PATH]`. Calls `import_service.run_import`; `--dry-run` parses + counts without writing; `--log` via `observability.log_context.enable_log`.

**Reused as-is:** `storage.sqlite.connection.session/connect`, `config.paths.ensure_runtime_dirs`, `security.admin_auth.verify_admin_key`, `observability.log_context.enable_log`.

## Edge cases

- Grok `sender` casing (`assistant`/`ASSISTANT`/`human`) lower-cased; `human`→`user`.
- Empty-`responses` Grok convs → conversation row persisted (it's context), zero messages.
- ChatGPT tool/system/hidden nodes stored (full fidelity) with `role`/`is_hidden`/`content_type`; non-text content kept verbatim in `raw_text` + spun-off behavioural rows.
- Timestamps: ChatGPT epoch float and Grok Mongo `$date.$numberLong` (ms) → ISO-8601 UTC; null `create_time` tolerated.
- Branches: every node stored with `parent_id`; `on_active_path` distinguishes kept thread from regenerations.
- Encoding: read/write UTF-8 explicitly (the earlier `cp1252` error was console-only, not data). Normalise `�` artefacts.
- `.gitignore`: `data/imports/raw/`, `data/imports/processed/`, and `data/sqlite/conversation_store.db` are runtime data (Rule 24) — keep ignored.

## Implementation order

1. `config/paths.py` + `config/ingestion_settings.py`.
2. `conversation_store_schema.py` + the `conversation_store/` repositories + `id_map` resolution + `import_store.py`.
3. `ingestion/parsing/` (models → chatgpt + content → grok + tags → metadata/errors).
4. `ingestion/cleaning/`.
5. `ingestion/sources/`.
6. `ingestion/status/` + `pipelines/` (conversation_pipeline → import_pipeline).
7. `import_service.py` + `import_flow.py`.
8. `admin_routes.py` endpoints + `scripts/import_chatgpt.py`.

## Verification (DB-only; no embedding)

Run from `lucchese/backend` with the venv active.

1. **Dry run:** `python -m scripts.import_chatgpt --source grok --dry-run` (and `--source chatgpt`) → prints conversations/messages/behavioural counts + skipped empties, no writes.
2. **Real run:** `python -m scripts.import_chatgpt --source all` → `ImportReport` with per-source totals.
3. **Shape/fidelity SQL** (`sqlite3 data/sqlite/conversation_store.db`):
   - `SELECT source, COUNT(*) FROM conversations GROUP BY source;`
   - `SELECT role, COUNT(*) FROM messages GROUP BY role;` and `SELECT COUNT(*) FROM messages WHERE on_active_path=0;` (branches captured)
   - **Behaviour:** `SELECT tool_name, COUNT(*) FROM tool_calls GROUP BY 1;` · `SELECT query, num_results FROM web_searches LIMIT 20;` · `SELECT domain, COUNT(*) FROM search_results GROUP BY 1 ORDER BY 2 DESC LIMIT 20;` · `SELECT kind, COUNT(*) FROM attachments GROUP BY 1;`
   - **Pairing:** pick a conversation, verify `messages.parent_id` forms a valid chain and `id_map` resolves old→new.
4. **Idempotency:** re-run step 2 → report shows all conversations skipped; row counts unchanged.
5. **API:** `POST /admin/import?source=grok` with `X-Admin-Key`; then `GET /admin/import/status`.
6. **Spot checks:** a Grok message stored clean of `<grok:render>`/`<xai:*>` with its `web_searches`/`search_results` populated; a ChatGPT conversation with code/image nodes showing `tool_calls` + `attachments`; an empty-`responses` Grok conversation present with 0 messages.
