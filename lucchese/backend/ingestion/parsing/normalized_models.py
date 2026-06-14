"""
ingestion/parsing/normalized_models.py
The canonical conversation shape — the parse target and single source of truth
(Rule 8: ingestion prepares external data into a normalized form).

Parsers (chatgpt_parser, grok_parser) emit these dataclasses; the conversation
pipeline maps them to plain repository call args (Rule 21: storage never imports
ingestion). The DB DDL in storage/sqlite/conversation_store_schema.py mirrors these
field-for-field.

Behavioural records hang off each message so a parser emits one self-contained
bundle per conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedToolCall:
    tool_name: str | None = None
    command: str | None = None
    arguments: dict | None = None       # serialised to JSON on insert
    created_at: str | None = None


@dataclass
class ParsedWebSearch:
    query: str | None = None
    num_results: int | None = None
    search_source: str | None = None
    created_at: str | None = None
    # Results emitted in the same parse step can be threaded onto this search by
    # the pipeline; populated for Grok web_search cards where results follow.
    results: list["ParsedSearchResult"] = field(default_factory=list)


@dataclass
class ParsedSearchResult:
    kind: str                            # search_result|citation|tether_quote|safe_url|xpost|image
    url: str | None = None
    domain: str | None = None
    title: str | None = None
    snippet: str | None = None
    pub_date: str | None = None
    rank: int | None = None
    created_at: str | None = None


@dataclass
class ParsedAttachment:
    kind: str                            # upload|generated_image|image_asset_pointer|file
    source_asset_id: str | None = None
    name: str | None = None
    mime_type: str | None = None
    url: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    created_at: str | None = None


@dataclass
class ParsedReasoningTrace:
    kind: str                            # thinking_trace|agent_thinking_trace|step
    content: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    seq: int | None = None


@dataclass
class ParsedMessage:
    source_message_id: str
    role: str                            # user | assistant | system | tool
    source_parent_id: str | None = None  # old parent id — resolved to integer parent_id on insert
    author_name: str | None = None       # tool name (python/web/dalle/bio/canmore/...)
    content_type: str | None = None      # text|multimodal_text|code|execution_output|tether_quote|...
    text: str | None = None              # cleaned display text
    raw_text: str | None = None          # original pre-clean text (fidelity)
    model: str | None = None             # model_slug / grok model
    recipient: str | None = None         # chatgpt routing target
    status: str | None = None
    end_turn: bool | None = None
    weight: float | None = None
    sequence: int | None = None          # original order within the conversation
    on_active_path: bool = True          # on the kept thread (current_node / leaf chain)
    is_hidden: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    source_metadata: dict = field(default_factory=dict)
    tool_calls: list[ParsedToolCall] = field(default_factory=list)
    web_searches: list[ParsedWebSearch] = field(default_factory=list)
    search_results: list[ParsedSearchResult] = field(default_factory=list)
    attachments: list[ParsedAttachment] = field(default_factory=list)
    reasoning_traces: list[ParsedReasoningTrace] = field(default_factory=list)


@dataclass
class ParsedConversation:
    source: str                          # 'chatgpt' | 'grok' | 'lucchese'
    source_conversation_id: str          # original UUID — kept for pairing
    title: str | None = None
    summary: str | None = None
    created_at: str | None = None        # ISO-8601 UTC
    updated_at: str | None = None
    default_model: str | None = None
    system_prompt_name: str | None = None
    starred: bool = False
    archived: bool = False
    source_metadata: dict = field(default_factory=dict)  # full-fidelity catch-all
    messages: list[ParsedMessage] = field(default_factory=list)
