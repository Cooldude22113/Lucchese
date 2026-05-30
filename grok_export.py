import json
import glob
from collections import Counter, defaultdict

# Counters
senders = Counter()
models = Counter()
has_thinking = 0
has_web_search = 0
has_file_attachments = 0
has_card_attachments = 0
has_agent_traces = 0
has_steps = 0
empty_messages = 0
total_responses = 0
total_conversations = 0
null_parent = 0  # root responses

# Metadata field presence
metadata_fields = Counter()
ui_layouts = Counter()
effort_levels = Counter()

# Timestamp format tracking
timestamp_formats = Counter()

for filename in glob.glob("prod-grok-*.json"):
    print(f"Processing {filename}")

    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])

    for entry in conversations:
        convo = entry.get("conversation", {})
        responses = entry.get("responses", [])
        total_conversations += 1

        for r in responses:
            total_responses += 1

            sender = r.get("sender", "unknown")
            senders[sender] += 1

            model = r.get("model", None)
            if model:
                models[model] += 1

            msg = r.get("message", "")
            if not msg:
                empty_messages += 1

            parent = r.get("parent_response_id")
            if parent is None:
                null_parent += 1

            # Timestamp format
            ct = r.get("create_time")
            if isinstance(ct, dict) and "$date" in ct:
                inner = ct["$date"]
                if isinstance(inner, dict) and "$numberLong" in inner:
                    timestamp_formats["$date.$numberLong(string)"] += 1
                elif isinstance(inner, str):
                    timestamp_formats["$date(string)"] += 1
                else:
                    timestamp_formats[f"$date(other:{type(inner).__name__})"] += 1
            elif isinstance(ct, str):
                timestamp_formats["ISO string"] += 1
            elif ct is None:
                timestamp_formats["null"] += 1
            else:
                timestamp_formats[f"other({type(ct).__name__})"] += 1

            # Optional fields
            if r.get("thinking_start_time"):
                has_thinking += 1
            if r.get("web_search_results"):
                has_web_search += 1
            if r.get("file_attachments"):
                has_file_attachments += 1
            if r.get("card_attachments_json"):
                has_card_attachments += 1
            if r.get("agent_thinking_traces"):
                has_agent_traces += 1
            if r.get("steps"):
                has_steps += 1

            # Metadata breakdown
            meta = r.get("metadata", {})
            if meta:
                for k in meta:
                    metadata_fields[k] += 1

                ui = meta.get("ui_layout", {})
                if ui:
                    ui_layouts[ui.get("reasoningUiLayout", "unknown")] += 1
                    effort_levels[ui.get("effort", "unknown")] += 1

                req_meta = meta.get("request_metadata", {})
                if req_meta:
                    models[req_meta.get("model", "unknown(req_meta)")] += 1

print("\n=== Summary ===")
print(f"Conversations:      {total_conversations}")
print(f"Total responses:    {total_responses}")
print(f"Empty messages:     {empty_messages}")
print(f"Root responses:     {null_parent}  (parent_response_id is null)")

print("\n=== Senders ===")
for s, count in senders.most_common():
    print(f"  {s}: {count}")

print("\n=== Models ===")
for m, count in models.most_common():
    print(f"  {m}: {count}")

print("\n=== Timestamp Formats ===")
for t, count in timestamp_formats.most_common():
    print(f"  {t}: {count}")

print("\n=== Optional Fields (response level) ===")
print(f"  thinking_start_time:    {has_thinking}")
print(f"  web_search_results:     {has_web_search}")
print(f"  file_attachments:       {has_file_attachments}")
print(f"  card_attachments_json:  {has_card_attachments}")
print(f"  agent_thinking_traces:  {has_agent_traces}")
print(f"  steps:                  {has_steps}")

print("\n=== Metadata Fields Present ===")
for f, count in metadata_fields.most_common():
    print(f"  {f}: {count}")

print("\n=== UI Layout Types ===")
for u, count in ui_layouts.most_common():
    print(f"  {u}: {count}")

print("\n=== Effort Levels ===")
for e, count in effort_levels.most_common():
    print(f"  {e}: {count}")