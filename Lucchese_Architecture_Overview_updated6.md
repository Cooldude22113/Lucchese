# Lucchese Architecture Overview

## Current High-Level Architecture

Lucchese currently consists of several major subsystems.

**Important distinction:** The architecture described here represents the conceptual design intent. Operational maturity — meaning deployment discipline, observability, failure handling, and runtime stability — is still significantly behind the architecture's ambitions. These are not the same thing, and the gap between them is the primary risk Lucchese now faces.

---

## Development Pipeline

Lucchese uses a structured multi-project AI engineering pipeline to manage architectural integrity across the system's evolution.

Pipeline stages:

- **Lucchese Main** — operational oversight, strategic continuity, roadmap prioritization, blocker identification
- **Architecture & Design** — technical specification authority, implementation-safe blueprints, data flow design
- **Implementation** — safe application of approved specifications into the real codebase
- **Review** — final correctness audit, production readiness verification, architectural compliance
- **Stabilize** — operational hardening, technical debt reduction, deployment discipline, observability maturity

The Stabilize layer was formally introduced in response to increasing complexity outpacing operational clarity. Its purpose is not feature development. It exists to prevent the system from accumulating fragility faster than it accumulates reliability.

Current pipeline priority: **Stabilize is the active stage.** Feature expansion is deferred until operational maturity improves.

---

## 1. Conversation Layer

Handles:
- text conversations
- streaming responses
- voice routes
- provider routing
- chat history

Primary responsibility:
- user interaction loop

Models:
- local Ollama models
- optional Claude/OpenAI integration

### Known Risk: chat.py Orchestration Hotspot

`chat.py` has grown into a god-route orchestrator. It currently handles routing, web search, memory commands, external integrations, scraping, roleplay, LLM calls, streaming, ingestion, and prompt construction within a single hot path.

This is the highest-priority structural risk in the current codebase. God-route orchestration of this kind degrades gradually and then fails suddenly. The combination of operational immaturity and increasing hot-path complexity makes `chat.py` the most likely first failure point under real operational stress.

The context builder architecture was intended to extract responsibility from `chat.py`. That work needs to continue and accelerate, not be bypassed by new feature additions routed through the same path.

---

## 2. Memory Infrastructure

Primary storage:
- ChromaDB

Memory types:
- knowledge
- facts
- style
- summaries
- documents

Capabilities:
- semantic retrieval
- metadata filtering
- classification metadata
- reranking
- memory ingestion

Current limitation:
- semantic retrieval works, but still requires current-state/profile seeding to prevent stale memories being presented as current truth
- retrieval still favors semantic relevance over current truth unless Tier 1 profile state is populated
- hot-path query expansion adds latency and cost without clearly bounded behavior

### Temporal Truth Problem

Lucchese now has enough historical memory to expose a persistent architectural challenge:

**semantic relevance does not equal current truth.**

Imported memories may describe:
- past goals
- superseded beliefs
- inactive projects
- completed courses
- outdated identity information

Without a populated current-state layer, the model may confidently present historical information as present reality. This is not a theoretical concern — it is the default behavior when `profile_state` is empty.

The system is transitioning from memory retrieval toward temporal reasoning and operational continuity. The profile_state + context_builder architecture is the correct structural response. The risk is that this transition stalls while other subsystems continue expanding.

### Schema Drift Risk

A live/batch schema divergence has been identified. The ingestion pipeline and the reclassification pipeline do not share a single enforced schema. As both systems evolve independently, metadata stored during live ingestion may become misaligned with metadata expected by the reclassification and retrieval layers. This creates a class of silent failure that is difficult to detect without dedicated schema validation.

---

## 3. Classification Pipeline

Current architecture:
- ingestion separated from reclassification
- reclassify.py performs deep classification after ingestion

Classification categories include:
- ontology
- taxonomy
- source_type
- engagement
- facts/style routing

Current direction:
- move classification infrastructure to second machine

This migration is deferred until core loop stabilization is complete.

---

## 4. Operational State Layer

Technology:
- SQLite

Purpose:
- track current operational truth
- active projects
- tasks
- blockers
- decisions
- daily state
- confirmed profile_state

Current status:
- `state.py` route exists
- state router registered in `main.py`
- `init_state_db()` called on startup alongside `init_db()`
- `profile_state` table exists as a single-row table using `CHECK (id = 1)`
- `GET /state/profile` exists
- `PATCH /state/profile` uses merge semantics — omitted fields are preserved; explicit field clearing supported via `clear_fields` parameter

This layer is intended to solve:
- outdated semantic truth
- operational continuity
- project awareness
- current priorities
- confirmed current facts about Alex

### Lifecycle Ownership — Partially Resolved

Startup validation is now deployed (STAB-005). `routes/startup_validator.py` confirms required state tables are present and correctly structured, validates the environment, and checks ChromaDB connectivity on every process start. Hard-stop on critical failures. AD-013 satisfied.

Remaining gap: no defined rollback procedure if the state layer becomes corrupted between process starts. The layer holds the Tier 1 truth that the entire context assembly depends on — rollback discipline is still an active operational risk.

---

## 5. Voice Pipeline

Current status:
- partial implementation

Capabilities:
- STT
- TTS
- streaming responses
- Tier 1 and Tier 2 context now injected into voice responses via `context_builder`

Known gaps:
- VAD
- interruption handling
- session continuity
- voice-aware formatting
- latency optimization
- no TTL or lifecycle management for roleplay/voice sessions

Long-term goal:
- voice-first interaction mode

**Current pipeline decision:** Voice feature expansion is suspended pending core stabilization. Partial voice features should not accumulate further complexity before the base conversation loop is hardened.

---

## 6. Summaries Layer

Purpose:
- compress large memory collections
- reduce retrieval load
- improve contextual continuity

Current status:
- collection exists
- `summarize.py` exists for category summaries after reclassification
- generation pipeline still needs confirmed operational use and testing
- not yet operationally integrated

---

## 7. Context Builder

Current status:
- `routes/context_builder.py` exists
- owns first-pass context assembly
- returns an internal `ContextResult` dataclass
- calls `get_profile_state()` and `search_memory()` independently
- either Tier 1 state retrieval or Tier 2 Chroma retrieval can fail without blocking the other
- `chat.py` now accepts a `ContextResult | None` in `build_system_prompt()`
- `voice.py` now correctly uses `build_context()` — Tier 1 and Tier 2 injected via the same tier contract as chat

Context tiers:
1. Tier 1 — `profile_state` / current facts, injected first as ground truth
2. Tier 2 — ChromaDB memory context, injected after current facts as background knowledge

Current limitation:
- `profile_state` currently ships empty unless manually populated or seeded
- therefore old semantic memories can still dominate until profile state is filled

### Observability — Deployed (STAB-001)

Context assembly observability is now in place. `emit_context_log()` runs on every main-path chat and voice inference, emitting a structured entry to the `lucchese.context` stream that records tier population state, failure types, char counts, and result counts. Tier retrieval failures surface as WARNING entries before user-visible degradation. The failure mode is now observable; the degradation policy (empty string fallback to keep the route alive) is unchanged.

The P0 observability requirement for context assembly is satisfied. The remaining risk is that token growth in `build_system_prompt()` is still not bounded or enforced — uncontrolled prompt growth as additional context sources are added remains a known failure mode.

Next planned responsibility:
- seed `profile_state` from imported Chroma memories using timestamps, classification metadata, and human confirmation
- expand to include active projects, tasks, and blockers after profile state seeding is operationalized

---

## 8. Observability

Deployed:
- `lucchese.context` structured logger — inference-time context assembly entries on every main-path chat and voice inference (STAB-001)
- `tier1_status`, `tier2_status`, `total_assembled_char_count` per inference (STAB-001)
- `RotatingFileHandler` on `lucchese.context` — 5 MB cap, 5 backups (STAB-003)
- `lucchese.startup` structured logger — startup validation entries on every process start (STAB-005)
- Environment, SQLite, schema, profile_state row, ChromaDB checked and logged at startup (STAB-005)

Remaining gaps:
- No retrieval inspection output — ChromaDB results, rerank scores, recency weights not yet logged
- No centralized telemetry or structured run trace
- Intercept paths in `chat.py` (action plan, scrape) produce no observability entries
- `lucchese.startup` logger has no file handler (TD-004, tracked)

The gap between Lucchese's architectural ambitions and its observability infrastructure has narrowed significantly. Inference-time and startup visibility are now in place. Retrieval inspection is the remaining blocker before debugging is no longer largely blind for AI quality regressions.

Minimum required — updated status:
- ~~structured logging of context tier state at inference time~~ — **DONE (STAB-001)**
- ~~explicit failure signals from context assembly~~ — **DONE (STAB-001)**
- ~~startup validation logging~~ — **DONE (STAB-005)**
- ~~configuration and environment validation on startup~~ — **DONE (STAB-005)**
- retrieval inspection output — **NOT YET IMPLEMENTED**

---

## 9. Infrastructure Direction

Main machine:
- conversation models
- generation
- voice interaction

Second machine:
- ChromaDB HTTP server
- embeddings
- classification model
- memory infrastructure

Purpose:
- isolate memory workload
- reduce hot-path contention
- improve scalability

**Current pipeline decision:** Second machine migration is deferred. This infrastructure change introduces a new runtime dependency (the second machine becomes a hard failure point) and requires graceful degradation design that does not yet exist. Migrating before the core loop is stable and observable creates compounded operational risk.

---

## 10. Current Data Flow for Chat Context

Current intended flow:

```txt
/chat request
  → build_context(query)
      → get_profile_state() from SQLite
      → search_memory() from ChromaDB
  → build_system_prompt(ContextResult, web_context, sheets_context)
      → Tier 1 current facts injected first
      → Tier 2 historical memory injected second
  → LLM generation
```

Known gap:
The pipeline exists, but profile_state needs confirmed data. Without populated profile_state, the model still relies mainly on historical Chroma retrieval.

Structural concern:
`build_system_prompt()` in `chat.py` receives multiple injected context sources — ContextResult, web context, sheets context, and potentially others — with no enforced token budget, no ordered priority policy beyond Tier 1 before Tier 2, and no visibility into what the assembled prompt actually contains at runtime. Uncontrolled context growth is a known failure mode for AI systems. This needs explicit management before the context pipeline expands further.

---

## 11. Operational Maturity Assessment

Lucchese's architecture is conceptually sound. The Tier 1/Tier 2 memory distinction, local-first design, Chroma/SQLite separation, explicit profile-state layer, context builder separation, and written architectural awareness are all genuine strengths.

Operationally, the system is not yet mature. The following risks are active:

**Structural risks:**
- `chat.py` as god-route orchestrator
- ~~silent context degradation with no observability signal~~ — **observable (STAB-001); degradation policy unchanged**
- schema drift between live ingestion and reclassification
- ~~no startup validation or dependency checks~~ — **resolved (STAB-005)**
- no rollback procedures
- no centralized failure reporting

**Memory risks:**
- stale semantic truth as the default when `profile_state` is empty
- retrieval bias toward semantic relevance over temporal accuracy
- no memory consolidation or superseded-truth handling

**Operational risks:**
- no run trace or inference observability
- insufficient debugging visibility into context assembly
- roleplay and voice sessions without lifecycle management
- deployment procedures undocumented
- operational runbooks absent

The current development priority is reducing these risks before expanding capabilities further. Operational discipline is not in competition with architectural vision — it is the prerequisite for it.
