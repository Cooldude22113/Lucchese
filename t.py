import json
import glob
from collections import Counter

content_types = Counter()
roles = Counter()
multi_part = 0
empty_parts = 0
total_messages = 0

for filename in glob.glob("conversations-*.json"):
    print(f"Processing {filename}")

    with open(filename, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    for convo in conversations:
        for node in convo.get("mapping", {}).values():
            message = node.get("message")

            if not message:
                continue

            content = message.get("content", {})
            content_type = content.get("content_type", "unknown")

            role = message.get("author", {}).get("role", "unknown")
            roles[role] += 1

            content_types[content_type] += 1
            total_messages += 1

            parts = content.get("parts", [])

            if len(parts) == 0:
                empty_parts += 1

            if len(parts) > 1:
                multi_part += 1

print("\n=== Summary ===")
print("Messages:", total_messages)
print("Multi-part:", multi_part)
print("Empty parts:", empty_parts)

print("\n=== Content Types ===")
for ct, count in content_types.most_common():
    print(f"{ct}: {count}")

print("\n=== Roles ===")
print("Roles:", role)