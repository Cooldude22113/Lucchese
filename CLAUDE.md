# CLAUDE.md — Lucchese

Read this before doing anything else. This file is the
root context for every agent in this repository.

---

## What Lucchese Is

A local-first, Jarvis-style personal AI operating system.
Python / FastAPI backend. Not a chatbot, not a SaaS
platform, not an agent framework.

Long-term direction: persistent memory, operational
awareness, voice-first interaction, contextual continuity
across time.

**Current phase: Stabilize.**
No new capabilities. The focus is operational maturity,
observability, and hardening what exists. Any task that
adds capability rather than stability is out of scope
until this phase is complete.

---

## File Structure

```
Lucchese/
  CLAUDE.md
  backend/
    main.py                  ← server entry point,
                               logger config, router
                               registration
    seed_profile.py          ← standalone: profile
                               seeding from Chroma facts
    reclassify.py            ← standalone: batch deep
                               classification
    ingestgpt.py             ← standalone: bulk ChatGPT
                               export ingestion
    grok.py                  ← standalone: Grok export
                               ingestion
    routes/
      admin.py
      chat.py                ← ⚠ god-route, see
                               constraints
      config.py
      context_builder.py     ← owns context assembly
      conversations.py
      database.py            ← init_db(), conversation
                               schema
      deal.py                ← BTL property analyser,
                               no LLM
      documents.py
      files.py
      memory.py              ← ChromaDB, retrieval,
                               ingestion, RECENCY_WEIGHT
      roleplay.py            ← Carol persona, no TTL
      scrape.py
      shopify.py
      startup_validator.py   ← STAB-005, startup checks
      state.py               ← SQLite state layer,
                               profile_state
      voice.py               ← STT, TTS, streaming
```

---

## Non-Negotiable Architectural Constraints

**AD-011 — No new routing through chat.py**
chat.py is a god-route and must not receive any new
responsibility. Adding to chat.py is an architectural
regression. Decomposition via context_builder.py is
the only permitted direction.

**AD-009 — Human confirmation for current truth**
Historical memories must not automatically become
profile_state entries. Human confirmation is required
before any promotion to Tier 1.

**AD-014 — No new capabilities during Stabilize**
Out of scope means out of scope. Flag it and stop.

**AD-015 — No new context sources without flagging**
build_system_prompt() has no token budget. Adding
context sources without flagging this is dangerous.

**AD-016 — Do not worsen schema drift**
Live ingestion (memory.py) and reclassify.py have
diverged schemas. Do not increase the divergence.

**Tier 1 / Tier 2 — always preserved**
Tier 1: profile_state from SQLite — current truth,
        injected first, authoritative when populated
Tier 2: ChromaDB — historical memory, injected second,
        never automatically current truth

**voice.py build_context() integration — never regress**
Tier 1 and Tier 2 are correctly injected into voice
responses via build_context(). Protect this.

---

## Active Risks

- profile_state empty — tier1_status: empty_source
  on every inference. Stale Chroma memories dominate.
  This is the current default operational state.
- chat.py god-route — decomposition in progress
- Live ingestion / reclassify.py schema divergence —
  no detection tooling exists
- build_system_prompt() has no token budget
- No rollback procedure for state layer corruption
- lucchese.startup has no file handler (TD-004)
- Roleplay sessions have no TTL
- EMPTY_CONTEXT singleton is mutable (STAB-004)

---

## Active Stabilization Work

STAB-002 — profile_state seeding (primary target)
STAB-004 — ContextResult immutability
TD-001    — _PassthroughJsonFormatter duplicated
TD-002/3  — schema check connection issues (batch)
TD-004    — lucchese.startup needs file handler

---

## Code Output Rules

These apply to every agent. No exceptions.

**Never write directly to source files.**
**Never output full file rewrites.**

For every code change, output a labelled diff block:

  FILE: routes/context_builder.py
  FUNCTION / SECTION: emit_context_log()

    def emit_context_log(result: ContextResult) -> None:
  -     log_entry = {"event": "context_assembly"}
  +     log_entry = {
  +         "event":        "context_assembly",
  +         "tier1_status": result.tier1_status,
  +         "tier2_status": result.tier2_status,
  +     }
        _log.info(json.dumps(log_entry))

  - lines removed
  + lines added
  unmarked lines are unchanged context — include 2-3
  above and below each change as location anchors

Multiple changes in one file = separate labelled diff
blocks. Never combine into one large diff.

If a function needs to be read before the diff can be
produced, say which function and ask Alex to confirm.
Do not infer and rewrite.

After every file's changes state explicitly:
NOTHING ELSE IN THIS FILE IS MODIFIED.

New files only:
  NEW FILE: routes/example.py
  <full file content>

---

## Working Style

Alex types changes in manually to build muscle memory
and understand the codebase. Diffs must be precise and
readable. Location anchors matter. No padding. No
unnecessary commentary. Be direct and specific.
