# Current Capabilities — Updated (5)

> **Maturity Notation Used in This Document**
>
> - **[Production-Mature]** — Reliable, hardened, safe to depend on.
> - **[Partially Operational]** — Exists and functions, but with known fragility, gaps, or runtime risk.
> - **[Experimental]** — Code exists and runs, but is not stable or safe to treat as reliable infrastructure.
> - **[Planned / Deferred]** — Intentional direction; not yet implemented or deliberately delayed.
>
> **Current Pipeline Priority: Stabilize.**
> Feature expansion is deferred. Operational maturity over new capabilities.

---

## Development Pipeline

Lucchese now uses a structured multi-project AI engineering pipeline to govern how changes move from idea to production.

Pipeline stages:
- **Lucchese Main** — operational oversight, roadmap prioritization, blocker identification
- **Architecture & Design** — technical specification authority, implementation-safe blueprints
- **Implementation** — safe application of approved specs into the codebase
- **Review** — final correctness audit, production readiness verification
- **Stabilize** — operational hardening, debt reduction, observability maturity, deployment discipline

**[Partially Operational]** — The pipeline is defined and actively used. Stabilize is the currently active stage. The pipeline structure itself is sound; adherence discipline is still maturing.

---

## Functional Systems

These systems exist and operate. Not all are production-mature. Maturity is noted per subsystem.

---

### Memory

**[Partially Operational]**

- Semantic memory retrieval via ChromaDB — functional, but retrieval is biased toward semantic relevance over recency or current truth
- ChromaDB integration — operational locally; HTTP/second-machine migration is planned but deferred
- Memory ingestion — functional
- Historical export ingestion — functional; timestamps preserved
- Memory metadata storage — functional
- `RECENCY_WEIGHT` extracted as a tunable constant in `memory.py`

**Known risks:**
- Stale semantic truth is the default behavior when `profile_state` is empty. The system may present historical memories as current reality with no visible signal.
- Hot-path query expansion adds latency and cost without clearly bounded behavior.
- Retrieval does not yet prioritize recency, operational importance, or active project relevance over semantic similarity.
- Live ingestion and reclassification pipelines do not share an enforced schema. Silent schema drift between these layers is an identified and unresolved risk.

---

### Classification

**[Partially Operational]**

- `reclassify.py` pipeline complete and functional for offline/batch use
- Ontology, taxonomy, engagement, facts/style extraction, routing metadata — all operational in batch mode

**Known risks:**
- Classification infrastructure is intended to move to a second machine. That migration is deferred until the core loop is stable.
- Live ingestion and batch reclassification operate on separate paths with no enforced shared schema. Metadata written during live ingestion may diverge from what the reclassification and retrieval layers expect. This is a silent failure class.

---

### Conversation

**[Partially Operational]**

- Local LLM integration via Ollama — functional
- Streaming responses — functional
- Provider routing (local / Claude / OpenAI) — functional
- Memory-enhanced chat — functional, subject to stale-memory risks noted above

**Known risks — chat.py orchestration hotspot:**
`chat.py` has grown into a god-route orchestrator. It currently handles routing, web search, memory commands, scraping, roleplay, LLM calls, streaming, ingestion, and prompt construction within a single hot path. This is the highest-priority structural risk in the current codebase. God-route orchestration degrades gradually and fails suddenly. The combination of operational immaturity and increasing hot-path complexity makes `chat.py` the most likely first failure point under real operational stress. No new functionality should be routed through `chat.py` until decomposition work is complete.

---

### Voice

**[Experimental]**

- STT route — exists
- TTS generation — exists
- Streaming voice responses — exists
- `voice.py` now uses `build_context()` — Tier 1 and Tier 2 context injected via context_builder

**Known gaps:**
- No VAD
- No interruption handling
- No persistent session mode
- No TTL or lifecycle management for voice sessions
- No voice-aware response formatting

**Current pipeline decision:** Voice feature expansion is suspended. Partial voice features should not accumulate further complexity before the base conversation loop is hardened. Voice infrastructure is experimental, not production-mature.

---

### Operational State

**[Partially Operational]**

- SQLite state layer — exists and initializes on startup
- Tables: projects, tasks, blockers, decisions, daily state, `profile_state`
- `GET /state/profile` — functional
- `PATCH /state/profile` — functional, uses merge semantics; `clear_fields` parameter supported for explicit nulling
- State router registered in `main.py`; `init_state_db()` called on startup

**Known risks — lifecycle ownership (partially resolved):**
The state layer exists and now has startup validation — `routes/startup_validator.py` (STAB-005) confirms required tables are present and correctly structured on every process start, detects extra schema columns, and hard-stops on critical failures. Startup validation deployed; AD-013 satisfied.

Remaining gaps: there is no automated detection of schema drift between process restarts (only checked at startup), and there is no defined rollback procedure if the state layer is corrupted or becomes inconsistent. The state layer holds the Tier 1 ground truth that the entire context assembly pipeline depends on. Its operational fragility is therefore disproportionately dangerous relative to its current hardening level.

---

## Partial / In Progress

---

### Context Builder

**[Partially Operational — active stabilization target]**

- `routes/context_builder.py` exists and owns first-pass context assembly
- `ContextResult` dataclass carries Tier 1 profile state and Tier 2 memory context
- `chat.py` receives `ContextResult` in `build_system_prompt()`
- `voice.py` uses `build_context()` — same tier contract as chat
- Tier 1 current facts are injected before Tier 2 historical background memory
- Either tier can fail independently without blocking the other

**Known risks — silent context degradation (partially resolved):**
The current failure policy allows tier failures to silently degrade to empty strings in order to keep the chat route alive. This is an acceptable availability tradeoff but created invisible intelligence failure.

Context assembly observability is now deployed (STAB-001). Every main-path inference produces a structured log entry via `emit_context_log()` in the `lucchese.context` stream, recording tier population state, failure type, char counts, and result counts. Tier retrieval failures now surface as WARNING entries. The P0 observability requirement for context assembly is satisfied.

Remaining gap: `build_system_prompt()` currently accepts multiple injected context sources (ContextResult, web context, sheets context) with no enforced token budget, no explicit priority ordering beyond Tier 1 before Tier 2, and no runtime visibility into the assembled prompt. Uncontrolled context growth is a known failure mode for AI systems. This needs explicit management before the context pipeline expands further.

---

### Profile State Seeding

**[Experimental]**

- `seed_profile.py` extraction pipeline exists
- Candidate extraction from Chroma facts is functional
- Timestamps survive ingestion
- Manual confirmation workflow exists conceptually

**Known limitations:**
- Extraction quality is still unreliable
- Semantic recency does not equal current truth
- Imported historical memories can contaminate current-state inference
- `profile_state` ships empty in the current operational state — Tier 1 context is therefore absent at inference time

**Consequence:** Until `profile_state` is populated with confirmed current facts, Lucchese defaults to historical semantic memory as the primary context source. This means the model may confidently present outdated information (previous projects, old age, inactive goals) as present reality. This is not a theoretical risk — it is the current default behavior.

**Next direction (deferred pending stabilization):**
- Multi-candidate ranking
- Evidence-aware extraction
- Timestamp weighting
- Human confirmation before promotion to `profile_state`

---

### Summaries

**[Experimental]**

- Summaries collection exists in ChromaDB
- `summarize.py` exists for category summaries after reclassification
- Generation pipeline has not been confirmed as operationally integrated or tested in live use

Not safe to treat as a reliable retrieval source until confirmed operational.

---

### Memory Infrastructure (Second Machine)

**[Planned / Deferred]**

- Second machine architecture for ChromaDB HTTP server, embeddings, and classification is designed (AD-001)
- Migration deliberately deferred

**Reason for deferral:** This migration introduces a hard runtime dependency on a second machine and requires graceful degradation design that does not yet exist. Migrating before the core loop is stable and observable compounds operational risk. This work does not proceed until `chat.py` decomposition, context observability, and startup validation are complete.

---

### Observability

**[Partially Operational — active stabilization target]**

Deployed:
- `lucchese.context` structured logger — inference-time context assembly entries on every main-path chat and voice inference (STAB-001)
- `tier1_status`, `tier2_status`, `total_assembled_char_count` per inference (STAB-001)
- `context_tier_failure` WARNING entries on retrieval failures (STAB-001)
- `RotatingFileHandler` on `lucchese.context` stream — maxBytes=5 MB, backupCount=5, ~25 MB total cap (STAB-003)
- `lucchese.startup` structured logger — startup validation entries on every process start (STAB-005)
- Environment, SQLite connectivity, table presence, schema integrity, profile_state row presence, ChromaDB connectivity checked and logged at startup (STAB-005)
- Hard-stop enforcement on critical failures with explicit stderr output (STAB-005)

Remaining gaps:
- No retrieval inspection output — what ChromaDB returned, rerank scores, recency weights not yet logged
- No centralized telemetry or structured run trace
- Intercept paths in `chat.py` (action plan, scrape) produce no observability entries
- `lucchese.startup` logger has no file handler — startup failures leave no disk trace if process manager does not capture stdout (TD-004, tracked)

**Current assessment:** The minimum inference-time and startup observability baseline is now in place. The remaining gap is retrieval inspection output, which is needed before retrieval quality regressions can be diagnosed without manual intervention.

Minimum required before production maturity can be claimed:
- ~~Structured logging of context tier state at inference time~~ — **DONE (STAB-001)**
- ~~Explicit failure signals from context assembly~~ — **DONE (STAB-001)**
- ~~Startup validation with dependency and environment checks~~ — **DONE (STAB-005)**
- ~~Configuration validation on startup~~ — **DONE (STAB-005)**
- Retrieval inspection output — **NOT YET IMPLEMENTED**

---

## Known Current Issues

---

### chat.py God-Route Orchestration

`chat.py` is the highest-priority structural risk in the codebase. It is a single hot-path handling routing, web search, memory commands, scraping, roleplay, LLM calls, streaming, ingestion, and prompt construction. This accumulation of responsibility was identified in the external repository audit as the most likely first failure point under real operational stress. The context builder architecture was intended to begin extracting responsibility from `chat.py`. That work must continue and accelerate. No new subsystems should be routed through `chat.py` before decomposition is underway.

---

### Stale Semantic Truth (Default Behavior)

The system has the plumbing to inject confirmed current state first via the Tier 1/Tier 2 architecture, but `profile_state` currently ships empty. Until populated with confirmed current facts, the model receives historical Chroma memories as its primary context and has no reliable mechanism to distinguish what is still true from what was true at some point in the past.

Examples of currently unresolved stale-truth risk:
- Outdated age
- Outdated project focus
- Outdated course status
- Superseded goals or priorities

This is the default operational state of the system right now.

---

### Retrieval Prioritization

Retrieval currently prioritizes semantic relevance more heavily than:
- Recency
- Operational importance
- Current truth
- Active project context

No memory consolidation or superseded-truth handling exists yet.

---

### Context Assembly — No Token Budget or Priority Enforcement

`build_system_prompt()` assembles context from multiple sources with no enforced token budget and no explicit priority ordering beyond Tier 1 before Tier 2. As additional context sources are added, uncontrolled prompt growth becomes an increasingly likely failure mode.

Current intended priority order (partially implemented):
1. Confirmed profile state
2. Active projects / tasks / blockers
3. Recent decisions / daily state
4. Relevant summaries
5. Semantic memories
6. Recent conversation

Steps 2–6 are not yet enforced by the context assembly pipeline.

---

### Schema Drift Between Ingestion and Reclassification

Live ingestion and the batch reclassification pipeline do not share an enforced schema. As both evolve independently, metadata stored during live ingestion may become misaligned with metadata expected by reclassification and retrieval layers. This creates a class of silent failure that is difficult to detect without dedicated schema validation tooling. No such tooling currently exists.

---

## Current Stabilization Priorities

Stabilize is the active pipeline stage. Work is constrained to:

1. ~~**Context assembly observability**~~ — **COMPLETE (STAB-001, STAB-003)** structured logging of tier population state and failures at inference time; log rotation deployed
2. **chat.py decomposition** — begin extracting responsibility from the god-route orchestrator
3. **profile_state seeding** — populate Tier 1 with confirmed current facts; human confirmation required before promotion
4. ~~**Startup validation**~~ — **COMPLETE (STAB-005)** dependency checks, environment validation, state layer integrity confirmation on startup
5. ~~**Failure reporting**~~ — **COMPLETE (STAB-001)** explicit, visible failure signals from context builder and memory retrieval; no silent degradation without logging
6. **Schema unification** — enforce a shared schema contract between live ingestion and reclassification pipelines

**Deferred work (until core stabilization is complete):**
- Second machine migration
- Voice feature expansion
- Summaries operationalization
- Memory consolidation
- New agentic or cognitive subsystems

---

## Long-Term Direction

Lucchese is evolving from:
- memory-enabled chatbot

toward:
- persistent personal AI operating system

The current transition point is:
- operational stabilization → production maturity → expanded cognitive infrastructure

The external repository audit confirmed this assessment directly: the design intent is mature, the implementation trajectory is not yet mature. Lucchese is a talented prototype with architecture ahead of its runtime discipline. The gap between conceptual capability and production-mature capability is the defining risk of the current phase.

---

## Latest Integration Notes

Implemented recently:
- `routes/context_builder.py` introduced as the owner of context assembly
- `profile_state` added to `state.py` as a single-row current-truth table
- `GET /state/profile` and `PATCH /state/profile` added; merge semantics; `clear_fields` supported
- `chat.py` now injects Tier 1 current facts before Tier 2 background memory
- `main.py` now registers/initializes state properly
- `RECENCY_WEIGHT` extracted in `memory.py` as a tunable constant
- `voice.py` now uses `build_context()` — Tier 1 and Tier 2 injected via context_builder
- STAB-001 — `emit_context_log()` added to `context_builder.py`; `lucchese.context` logger configured in `main.py`; every main-path chat and voice inference is now observable
- STAB-003 — `RotatingFileHandler` added to `lucchese.context` logger; `lucchese.context.log` written to disk with 5 MB rotation cap
- STAB-005 — `routes/startup_validator.py` introduced; `run_startup_validation()` called from `main.py` after `init_db()` and `init_state_db()`; `lucchese.startup` logger active; AD-013 satisfied

**Important caveat:**
Tier 1 profile context remains empty until `profile_state` is manually populated or seeded from confirmed memories. All recently integrated plumbing is architecturally correct but operationally inactive without populated state data.
