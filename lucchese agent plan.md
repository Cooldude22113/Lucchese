# Plan: Place "Lucchese Agent Team v0.1" into the purpose-driven backend

## Context

`Overview.txt` specifies a new feature — **Lucchese Agent Team v0.1**: a local
coordination layer where a mission goes in, a roster of agents (Project Manager,
Technical Architect, Implementation Planner, QA Reviewer, Changelog Auditor,
Interpreter, Memory Curator) each writes a structured report, and an Orchestrator
synthesises one decision packet. It produces **reports only** — no autonomous
code editing, git commits, or file writes to the project (v0.1 boundary).

The Overview sketches this as a single flat folder (`lucchese/agents/` with
`registry.py`, `schemas.py`, `prompt_loader.py`, `llm_client.py`,
`orchestrator.py`, `prompts/`, plus `missions/` and `reports/`). That layout
bundles model calls, prompt building, orchestration, domain models, persistence,
runtime data, and an HTTP route into one box — which directly violates the
placement rules the project already follows everywhere else (`backend/` is a
complete, rule-compliant tree: `api/`, `application/orchestration/`,
`application/services/`, `model_runtime/`, `memory/`, `storage/`, `data/`,
`observability/`, `security/`, etc.).

**Goal of this plan:** implement the Overview's behaviour, but decompose its
responsibilities across the existing `backend/` purpose systems per the rules,
reusing what already exists (notably the model client) instead of re-creating it.

## Placement decisions (Overview component → rule → location)

| Overview piece | Responsibility | Rule | Target location |
|---|---|---|---|
| `registry.py` (`AGENT_REGISTRY`, `DEFAULT_AGENT_FLOW`, `get_agent`) | Static team definition | 23 (foundational purpose system) | **`backend/agent_team/registry.py`** |
| `select_agents()` | Testable domain rule (no FastAPI/LLM) | 10 | **`backend/agent_team/agent_selection.py`** |
| `schemas.MissionRequest` | HTTP request model | 2 / quick table | **`backend/api/schemas/agents.py`** |
| `schemas.Mission`, `AgentReport`, `DecisionPacket` | Internal domain models shared downward | 21 | **`backend/agent_team/models.py`** |
| `prompt_loader.py` + `prompts/*.md` + `build_agent_prompt` + synthesis prompt text | Prompt building & templates | 5 | **`backend/model_runtime/prompt_building/agent_prompt_builder.py`** + **`.../agent_prompts/*.md`** |
| `llm_client.run_llm` (Ollama via `requests`) | Model call | 5, 21 | **REUSE** existing `backend/model_runtime/clients/llm_client.py::complete()` — do **not** add a new client |
| `run_agent()` | Reusable app action (build prompt → call model → wrap report) | 4 | **`backend/application/services/agent_runner_service.py`** |
| `coordinate_mission()` + `synthesize_decision_packet()` | Multi-system workflow (registry + selection + service + storage + logging) | 3 | **`backend/application/orchestration/agent_team_flow.py`** |
| `save_json()` / `save_markdown_report()` | Persistence mechanics | 9 | **`backend/storage/files/mission_store.py`** + **`backend/storage/files/agent_report_store.py`** |
| `missions/`, `reports/` output files (JSON + markdown) | Runtime data artefacts | 1, 24 | **`backend/data/missions/`**, **`backend/data/reports/`** (+ `paths.py` + `.gitignore`) |
| FastAPI route `POST /agents/coordinate` | Thin HTTP layer | 2 | **`backend/api/routes/agent_routes.py`** (register in `app/router.py`) |
| `LUCHESE_AGENT_MODEL` / `OLLAMA_HOST` env | Model config | config | Reuse `config/model_settings.py` (`MODEL_FAST`/`MODEL_DEEP`, `OLLAMA_URL` already exist); add an optional `AGENT_MODEL` only if a distinct model is wanted |

**Import direction (Rule 21):** `api/routes/agent_routes` → `application/orchestration/agent_team_flow` → `application/services/agent_runner_service` → `agent_team/*` + `model_runtime/*` + `storage/files/*`. `agent_team/` is a low-level purpose system: it must never import routes or flows.

## Files to create

### New purpose system: `backend/agent_team/`
Earns existence per Rule 23 (foundational to the feature, 3+ related files).
- `backend/agent_team/__init__.py`
- `backend/agent_team/registry.py` — `AGENT_REGISTRY`, `DEFAULT_AGENT_FLOW`, `get_agent()` (verbatim from Overview §2, minus `select_agents`).
- `backend/agent_team/agent_selection.py` — `select_agents(user_request, mode)` (the keyword/mode routing from Overview §2). Pure function, unit-testable.
- `backend/agent_team/models.py` — `Mission`, `AgentReport`, `DecisionPacket` (Overview §3), as pydantic models matching the existing style.

### API layer (Rule 2)
- `backend/api/schemas/agents.py` — `MissionRequest` (`user_request`, `project_context`, `mode`, `require_code_proposal`). Mirror `api/schemas/business.py` style.
- `backend/api/routes/agent_routes.py` — `router = APIRouter()`; `@router.post("/agents/coordinate")` → `await coordinate_mission(req)` → `packet.model_dump()`. Async, thin, no logic. Mirror `api/routes/business_routes.py`.

### Orchestration (Rule 3)
- `backend/application/orchestration/agent_team_flow.py` — `coordinate_mission(request) -> DecisionPacket`: build `Mission`, call `select_agents`, persist mission via `mission_store`, loop agents through `agent_runner_service` passing accumulated reports, synthesise the packet, persist JSON + markdown. Match `chat_flow.py` conventions (module docstring citing the rule, `from __future__ import annotations`). Synthesis uses `model_runtime` for the final LLM call. Emit logs via `observability` (Rule 15).

### Services (Rule 4)
- `backend/application/services/agent_runner_service.py` — `run_agent(agent_key, mission, previous_reports) -> AgentReport`: look up agent (`registry`), build the prompt (`agent_prompt_builder`), call `llm_client.complete()`, wrap as `AgentReport`. Async (existing `complete()` is async).

### Model runtime (Rule 5)
- `backend/model_runtime/prompt_building/agent_prompt_builder.py` — `load_agent_prompt(agent_key)` (replaces `prompt_loader.py`), `build_agent_prompt(...)`, and `build_synthesis_prompt(...)`. Templates resolved relative to the module (like `system_prompt_builder.py`).
- `backend/model_runtime/prompt_building/agent_prompts/` — the seven `.md` templates verbatim from Overview §7: `project_manager.md`, `technical_architect.md`, `implementation_planner.md`, `qa_reviewer.md`, `changelog_auditor.md`, `interpreter.md`, `memory_curator.md`. These are **committed source assets**, not runtime data.

### Storage (Rule 9)
- `backend/storage/files/mission_store.py` — `save_mission(mission)` → JSON under `MISSIONS_DIR`.
- `backend/storage/files/agent_report_store.py` — `save_decision_packet_json(packet)` and `save_decision_packet_markdown(packet)` → under `REPORTS_DIR` (the markdown assembly from Overview §6 `save_markdown_report`).

## Files to modify

- `backend/config/paths.py` — add `MISSIONS_DIR = DATA_DIR / "missions"` and `REPORTS_DIR = DATA_DIR / "reports"`; add both to the `ensure_runtime_dirs()` tuple. Stores import these constants instead of hardcoding paths (Rule 1, Rule 25 step 2).
- `backend/app/router.py` — add `agent_routes` to the `api.routes` import block and to the `include_all_routers` tuple.
- `backend/.gitignore` — add `data/missions/` and `data/reports/` (Rule 24); add `.gitkeep` files so the empty dirs survive in Git (matches existing `!data/**/.gitkeep` rule).
- `config/model_settings.py` — optional: add `AGENT_MODEL = os.getenv("AGENT_MODEL", MODEL_DEEP)` if agents should use the deep model; otherwise the flow/service just pass `MODEL_DEEP`/`MODEL_FAST` to `complete()`.

## Explicitly NOT created (deviations from Overview)

- **No `backend/agents/llm_client.py`** — `model_runtime/clients/llm_client.py::complete()` already abstracts the Claude/Ollama branch and reads `config/model_settings`. Re-adding a `requests`-based Ollama client would duplicate it and break Rule 5/Rule 21.
- **No top-level `lucchese/agents/` or `lucchese/missions/` + `lucchese/reports/`** next to source — that mixes source, runtime data, and HTTP in one folder (violates Rules 1, 2, 9).
- **No autonomous coding / git / file edits** — the v0.1 boundary from the Overview. `can_modify_code`/`permission_level` stay inert metadata in the registry; when enforcement is eventually added it belongs in `backend/security/` (Rule 16), not the registry.

## Build order

1. `config/paths.py` (add `MISSIONS_DIR`/`REPORTS_DIR`) + `.gitignore` + `.gitkeep`s.
2. `agent_team/registry.py`, `agent_selection.py`, `models.py`.
3. `model_runtime/prompt_building/agent_prompts/*.md` + `agent_prompt_builder.py`.
4. `storage/files/mission_store.py` + `agent_report_store.py`.
5. `application/services/agent_runner_service.py`.
6. `application/orchestration/agent_team_flow.py`.
7. `api/schemas/agents.py` + `api/routes/agent_routes.py`; register in `app/router.py`.

## Verification

1. **Static:** `python -c "import app.factory"` (or the project's app import) from `backend/` to confirm the new route module imports and the router wires up with no circular imports.
2. **Run the API** (existing `start.bat` / uvicorn entrypoint), then:
   ```bash
   curl -X POST http://localhost:8000/agents/coordinate \
     -H "Content-Type: application/json" \
     -d '{"user_request":"Plan a memory recall visibility panel for the frontend.","project_context":"Lucchese local AI assistant; focus is trust + frontend usability.","mode":"default","require_code_proposal":false}'
   ```
   Expect a `DecisionPacket` JSON back, and new files under `backend/data/missions/<id>.json`, `backend/data/reports/<id>.json`, and `backend/data/reports/<id>.md`.
3. **Unit test (no network):** `select_agents()` routing — assert `"review"` mode, the `changelog`/`architecture` keyword branches, and the default flow return the expected agent lists. This is the one piece with no FastAPI/LLM dependency (Rule 10).
4. **Offline behaviour:** with Ollama down, confirm the flow degrades gracefully (existing `llm_client`/provider error handling) and still writes a packet noting the model error, rather than crashing the request.
