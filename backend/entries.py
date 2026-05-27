# check_counts.py

from routes.memory import col_knowledge, col_facts, col_style

print("knowledge:", col_knowledge.count())
print("facts:", col_facts.count())
print("style:", col_style.count())