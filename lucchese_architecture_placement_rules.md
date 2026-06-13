# Lucchese Architecture Placement Rules

A purpose-driven rulebook for deciding where files, folders, data, and logic belong.

> **Core principle: A file or folder exists when a responsibility needs to be changed, tested, logged, reused, or replaced independently.**

Purpose: This document explains the rules behind the Lucchese purpose-driven structure. It is designed to prevent route files, components, and utility modules from becoming overloaded with unrelated responsibilities.

Important constraint: The full structure represents the vision. Do not create every file immediately. Create the folder when the responsibility is real, and create the file when code is ready to move into it.

How to use this document

When deciding where code belongs, ask:

- What kind of responsibility is this?
- What system does this code depend on?
- What will break if this changes?
- Does it need independent logging, testing, or replacement?
- Is it source code, runtime data, or a manual script?
### Rule 1: Separate runtime data from source code

Runtime artefacts belong in data/. Source code that reads or writes those artefacts belongs elsewhere, usually storage/, memory/, documents/, or observability/.

Examples:

```text
backend/data/chroma/chroma.sqlite3
backend/data/sqlite/conversations.db
backend/data/logs/errors.log
backend/data/generated_docs/example.docx
```

Avoid:

```text
backend/chroma_db/ beside source files
backend/conversations.db beside main.py
backend/generated_docs/ beside routes/
```

### Rule 2: Keep API routes thin

api/routes/ files should receive requests, validate inputs, call an application flow or service, and return a response. They should not contain prompt building, database queries, ChromaDB internals, Shopify payloads, document generation, or model calls.

Examples:

```text
api/routes/chat_routes.py -> application/orchestration/chat_flow.py
api/routes/voice_routes.py -> application/orchestration/voice_flow.py
```

### Rule 3: Use orchestration for multi-step workflows

If a file coordinates three or more systems, it belongs in application/orchestration/. A flow describes the order of a user-facing operation without owning all the implementation details.

Examples:

```text
chat_flow.py: conversation + context + memory + model_runtime + storage + logging
voice_flow.py: audio + transcription + chat flow + TTS + storage
```

### Rule 4: Use services for reusable app actions

application/services/ exposes stable actions that routes, flows, or other systems can call. A service should hide lower-level details and prevent duplicated behaviour.

Examples:

```text
conversation_service.py
memory_service.py
document_service.py
voice_service.py
state_service.py
```

### Rule 5: Put model-facing work in model_runtime/

Anything that calls, configures, prepares for, streams from, or cleans output from an AI model belongs in model_runtime/. This includes LLMs, embeddings, rerankers, transcription, TTS providers, prompt building, streaming, and token limits.

Examples:

```text
model_runtime/providers/ollama_provider.py
model_runtime/providers/whisper_provider.py
model_runtime/clients/llm_client.py
model_runtime/prompt_building/system_prompt_builder.py
```

### Rule 6: Do not confuse context with memory

memory/ stores and retrieves knowledge. context/ assembles selected information into model-ready context for a single response.

Examples:

```text
memory/retrieval/semantic_search.py finds candidates
context/context_builder.py decides what gets injected into the prompt
```

### Rule 7: Split memory by lifecycle stage

Memory has different stages: collections, ingestion, retrieval, processing, commands, and inspection. Each stage should have its own place so failures can be isolated.

Examples:

```text
memory/collections/
memory/ingestion/
memory/retrieval/
memory/processing/
memory/commands/
memory/inspection/
```

### Rule 8: Separate ingestion from memory

Imported ChatGPT/Grok conversations are raw source material, not memory yet. ingestion/ prepares external data; memory/ingestion/ writes usable memory into the memory system.

Examples:

```text
ingestion/parsing/chatgpt_parser.py
ingestion/cleaning/text_cleaner.py
ingestion/pipelines/import_pipeline.py
memory/ingestion/exchange_ingestor.py
```

### Rule 9: Storage code is not the same as stored data

storage/ contains persistence mechanics: SQLite repositories, file stores, token stores, and runtime stores. data/ contains the actual database files, logs, uploads, imports, and generated documents.

Examples:

```text
storage/sqlite/repositories/message_repository.py
storage/files/generated_doc_store.py
data/sqlite/conversations.db
data/chroma/chroma.sqlite3
```

### Rule 10: Keep domain rules in business_logic/

If logic can be tested without FastAPI, ChromaDB, SQLite, or an LLM, and it represents a real-world rule, it belongs in business_logic/.

Examples:

```text
business_logic/property/deal_calculator.py
business_logic/property/sdlt.py
business_logic/meal_prep/macro_calculator.py
business_logic/roleplay/roleplay_detection.py
```

### Rule 11: Put external systems in integrations/

External API logic should be isolated from routes, chat flow, and business logic. integrations/ owns Google, Sheets, Shopify, OAuth, API clients, and token caching.

Examples:

```text
integrations/google/auth.py
integrations/sheets/recipes_reader.py
integrations/shopify/client.py
integrations/shopify/token_cache.py
```

### Rule 12: Treat documents as a lifecycle

Document handling has separate responsibilities: extraction, generation, and lifecycle management. Split them so upload logic does not become document generation logic.

Examples:

```text
documents/extraction/pdf_extractor.py
documents/generation/docx_generator.py
documents/lifecycle/download_tokens.py
```

### Rule 13: Separate audio mechanics from voice flow

Voice is a user-facing workflow. Audio is the technical layer. Audio capture, temp files, transcription, TTS chunking, and speech responses belong in audio/. The full voice workflow belongs in application/orchestration/.

Examples:

```text
audio/transcription/transcribe_audio.py
audio/speech/prepare_tts.py
application/orchestration/voice_flow.py
```

### Rule 14: Keep web search and scraping outside chat

Chat may use web results, but chat should not own web detection, search, scraping, HTML parsing, metadata extraction, or review prompt construction.

Examples:

```text
web/search/search_decision.py
web/search/ddgs_search.py
web/scraping/page_fetcher.py
web/scraping/html_text_extractor.py
```

### Rule 15: Make observability first-class

If it helps you understand, log, trace, validate, diagnose, or recover from failure, it belongs in observability/. Logging is not a side quest. It is the nervous system of the app.

Examples:

```text
observability/logging_config.py
observability/exception_handlers.py
observability/startup_validator.py
observability/request_logging.py
observability/error_reporter.py
```

### Rule 16: Security is not config

Config stores values. Security enforces rules. Authentication, permissions, secrets handling, sanitisation, and audit logic belong in security/.

Examples:

```text
config/security_settings.py stores ADMIN_API_KEY
security/admin_auth.py verifies the key
```

### Rule 17: Use inspection for read-only admin/debug visibility

inspection/ contains read-only tools that observe internals without owning the systems being observed.

Examples:

```text
inspection/admin_stats.py
inspection/recent_memory.py
inspection/log_reader.py
inspection/system_status.py
```

### Rule 18: Scripts are manual entrypoints, not core logic

scripts/ is for commands you run manually. Scripts should call real modules rather than containing the full implementation.

Examples:

```text
scripts/import_chatgpt.py calls ingestion/pipelines/import_pipeline.py
scripts/inspect_memory.py calls memory/inspection/memory_stats.py
```

### Rule 19: Frontend separates API, interface, state, audio, and utils

Frontend components should render UI. They should not own raw fetch calls, business logic, browser audio mechanics, and state orchestration all at once.

Examples:

```text
frontend/src/api/ talks to backend
frontend/src/interface/ renders UI
frontend/src/state/ owns hooks/context/stores
frontend/src/audio/ owns browser audio helpers
frontend/src/utils/ owns pure helpers
```

### Rule 20: UI may group by screen, but only inside interface/

Top-level frontend architecture stays purpose-driven. Visual components may be grouped by screen or area once they are inside interface/components/.

Examples:

```text
interface/components/chat/
interface/components/admin/
interface/components/voice/
interface/components/common/
```

### Rule 21: Keep import direction one-way

Higher-level entrypoints call lower-level purpose systems. Lower-level systems should not import API routes or orchestration files.

Examples:

```text
api/routes -> application/orchestration -> application/services -> purpose systems
```

Avoid:

```text
memory imports api.routes
storage imports chat_flow
voice imports chat_routes
config loads heavy models
```

### Rule 22: Use job-based filenames

A filename should say what responsibility lives inside before you open it.

Examples:

```text
conversation_repository.py
system_prompt_builder.py
exchange_ingestor.py
semantic_search.py
request_logger.py
```

Avoid:

```text
utils.py
helpers.py
manager.py
processor.py
stuff.py
new_final.py
```

### Rule 23: A folder must earn existence

Create a folder when there are three or more related files, or when the responsibility is foundational. Do not create empty architecture for sport.

Examples:

```text
Foundational folders: api, config, storage, observability, security, data
```

### Rule 24: Ignore runtime files in Git

Commit code, docs, tests, config examples, and scripts. Do not commit local DBs, vector DBs, logs, generated docs, raw private imports, cache, temp files, or secrets.

Examples:

```text
backend/data/chroma/
backend/data/sqlite/*.db
backend/data/generated_docs/
backend/data/imports/raw/
backend/data/logs/
backend/.env
frontend/node_modules/
backend/venv/
```

### Rule 25: Build the skeleton gradually

The full tree represents the vision. Start by moving responsibilities that already exist. Do not create 100 empty files just because the map says they may exist one day.

Examples:

```text
1. Move runtime files into data/
2. Create config/paths.py
3. Create frontend api/client.js
4. Move logging setup into observability/
5. Move prompt building out of chat route
6. Create memory_service.py facade
7. Split storage/database access
```

## Quick Decision Table

| Question | Put it in |
| --- | --- |
| Is it an HTTP endpoint? | backend/api/routes/ |
| Is it a request or response model? | backend/api/schemas/ |
| Does it coordinate a full workflow? | backend/application/orchestration/ |
| Is it a reusable app action? | backend/application/services/ |
| Does it call or configure an AI model? | backend/model_runtime/providers/ or clients/ |
| Does it build prompts? | backend/model_runtime/prompt_building/ |
| Does it assemble model-ready context? | backend/context/ |
| Does it store, search, or process memories? | backend/memory/ |
| Does it import old or raw external data? | backend/ingestion/ |
| Does it read or write DBs, files, tokens, sessions? | backend/storage/ |
| Is it an actual DB, log, upload, import, or generated file? | backend/data/ |
| Does it handle document extraction/generation/lifecycle? | backend/documents/ |
| Does it handle audio/transcription/TTS mechanics? | backend/audio/ |
| Does it talk to Shopify, Sheets, Google, or external APIs? | backend/integrations/ |
| Is it property, meal prep, or roleplay domain logic? | backend/business_logic/ |
| Is it logging, errors, health, startup validation, metrics? | backend/observability/ |
| Is it auth, secrets, permissions, validation, audit? | backend/security/ |
| Is it admin/debug read-only visibility? | backend/inspection/ |
| Is it manually run from the terminal? | backend/scripts/ |
| Is it frontend backend communication? | frontend/src/api/ |
| Is it frontend visual UI? | frontend/src/interface/ |
| Is it frontend state, hooks, context, stores? | frontend/src/state/ |
| Is it frontend browser audio code? | frontend/src/audio/ |
| Is it a pure frontend helper? | frontend/src/utils/ |

## Target Import Direction

Keep dependencies flowing from entrypoints toward lower-level purpose systems:

```text
api/routes
  -> application/orchestration
    -> application/services
      -> purpose systems
         -> storage/data/model_runtime/integrations/etc.
```

Avoid reverse dependencies such as:

```text
memory imports api.routes
storage imports application flow
voice imports chat_routes
config imports heavy model providers
```

## Git Ignore Guidance

Runtime data should generally not be committed. Keep folder structure with .gitkeep files if needed.

```text
backend/data/chroma/
backend/data/sqlite/*.db
backend/data/generated_docs/
backend/data/imports/raw/
backend/data/logs/
backend/data/audio/
backend/data/cache/
backend/data/temp/
backend/.env
frontend/node_modules/
backend/venv/
```

## Recommended Migration Order

1. Move runtime files into backend/data/.
1. Create backend/config/paths.py and stop hardcoding relative paths.
1. Create frontend/src/api/client.js and move raw fetch strings out of components.
1. Move logging setup from main.py into backend/observability/.
1. Move system prompt building out of route files into model_runtime/prompt_building/.
1. Create application/services/memory_service.py as a facade over the existing memory module.
1. Split database access into storage/sqlite/connection.py, schema.py, and repositories/.
1. Move document generation and upload extraction into documents/.
1. Move Shopify and Sheets clients into integrations/.
1. Only then start deeper memory and ingestion refactors.
## Final Notes

- The structure is a map, not a demand to create every file immediately.
- Prefer moving real existing code into the new structure over creating empty placeholders.
- If a file becomes scary to edit, it probably owns too many responsibilities.
- If a failure is hard to log clearly, the boundary is probably wrong.
- If a file name does not explain its job, rename it before it breeds confusion.
