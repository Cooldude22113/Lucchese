#!/usr/bin/env python3
"""
system_snapshot.py
Generate a local system snapshot for the Lucchese project.
Inspect repo state, database schemas, routes, environment, and known gaps.
Safe to run repeatedly — read-only operations only.
"""

import os
import sys
import sqlite3
import json
import subprocess
from datetime import datetime
from pathlib import Path
from collections import defaultdict


def run_cmd(cmd, cwd=None):
    """Run a shell command and return output, or return error string if it fails."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_git_info():
    """Return git branch and commit hash."""
    branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    commit = run_cmd("git rev-parse HEAD")
    return {
        "branch": branch or "unknown",
        "commit": commit[:8] if commit else "unknown",
        "full_commit": commit or "unknown",
    }


def get_backend_routes():
    """Parse FastAPI routes from backend/routes files and main.py."""
    routes_dir = Path("backend/routes")
    detected_routes = []

    if not routes_dir.exists():
        return detected_routes

    # Parse each route file for @router.* decorators
    for route_file in sorted(routes_dir.glob("*.py")):
        if route_file.name == "__init__.py":
            continue
        try:
            content = route_file.read_text()
            # Simple regex patterns for FastAPI decorators
            import re
            # Match @router.get/post/put/delete("path")
            pattern = r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
            matches = re.findall(pattern, content)
            for method, path in matches:
                detected_routes.append(f"{method.upper()} /{path}")
        except Exception:
            pass

    return sorted(set(detected_routes))


def get_python_files():
    """Return list of Python scripts in backend (excluding venv, __pycache__)."""
    backend_dir = Path("backend")
    files = []
    if backend_dir.exists():
        for py_file in backend_dir.glob("*.py"):
            files.append(py_file.name)
    return sorted(files)


def get_db_schema(db_path):
    """Return schema (tables and columns) for a SQLite database, or 'unavailable'."""
    if not Path(db_path).exists():
        return "unavailable"

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cur.fetchall()

        schema = {}
        for (table_name,) in tables:
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = cur.fetchall()
            schema[table_name] = [col[1] for col in columns]

        conn.close()
        return schema
    except Exception as e:
        return f"error: {str(e)}"


def get_profile_row(db_path):
    """Return current profile_state row (id=1) with no secret values exposed."""
    if not Path(db_path).exists():
        return "unavailable"

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM profile_state WHERE id=1")
        row = cur.fetchone()
        conn.close()

        if not row:
            return "empty"

        # Convert row to dict and redact any field that looks like a secret
        profile = dict(row)
        # Don't expose actual secrets, just note if field is populated
        for key in profile:
            if profile[key] is not None and isinstance(profile[key], str):
                if len(profile[key]) > 100:
                    profile[key] = f"<populated, {len(profile[key])} chars>"
        return profile

    except Exception as e:
        return f"error: {str(e)}"


def get_chroma_collections():
    """Return ChromaDB collection counts if accessible."""
    try:
        import chromadb
        chroma_path = Path("backend/chroma_db")
        if not chroma_path.exists():
            return "unavailable"

        # Try to connect to persistent Chroma client
        client = chromadb.PersistentClient(path=str(chroma_path))
        collections = client.list_collections()

        result = {}
        for coll in collections:
            try:
                count = coll.count()
                result[coll.name] = count
            except Exception:
                result[coll.name] = "error"
        return result if result else "empty"

    except Exception:
        return "unavailable"


def get_important_scripts():
    """Detect important scripts: ingest*, reclassify, seed_profile, summarize."""
    backend_dir = Path("backend")
    important = {}

    patterns = {
        "ingest": ["ingestgpt.py", "ingest_grok_checkpoint.json"],
        "reclassify": ["reclassify.py"],
        "seed_profile": ["seed_profile.py"],
        "summarize": ["summary.py"],
    }

    for key, files in patterns.items():
        found = [f for f in files if (backend_dir / f).exists()]
        important[key] = "present" if found else "absent"

    return important


def get_env_var_names():
    """Extract env var names from .env (never return values)."""
    env_file = Path("backend/.env")
    if not env_file.exists():
        return "unavailable"

    try:
        env_vars = []
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=")[0].strip()
                    env_vars.append(key)
        return sorted(set(env_vars))
    except Exception:
        return "error reading .env"


def detect_gaps():
    """Detect known gaps: empty profile_state, missing summaries, etc."""
    gaps = []

    # Check if lucchese_state.db exists and has profile_state data
    db_path = Path("lucchese_state.db")
    if not db_path.exists():
        db_path = Path("backend/lucchese_state.db")

    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM profile_state WHERE id=1")
            count = cur.fetchone()[0]
            if count == 0:
                gaps.append("profile_state is empty (no id=1 row)")
            conn.close()
        except Exception:
            pass

    # Check if chroma_db has collections
    chroma_path = Path("backend/chroma_db")
    if chroma_path.exists():
        try:
            collections = get_chroma_collections()
            if isinstance(collections, dict) and len(collections) == 0:
                gaps.append("ChromaDB exists but has no collections")
            elif collections == "empty":
                gaps.append("ChromaDB is empty")
        except Exception:
            pass

    if not gaps:
        gaps.append("none detected")

    return gaps


def generate_snapshot():
    """Generate the complete system snapshot."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    git_info = get_git_info()

    # Find database paths
    state_db = "lucchese_state.db"
    if not Path(state_db).exists() and Path("backend/lucchese_state.db").exists():
        state_db = "backend/lucchese_state.db"

    conv_db = "backend/conversations.db"
    if not Path(conv_db).exists() and Path("conversations.db").exists():
        conv_db = "conversations.db"

    snapshot = {
        "timestamp": timestamp,
        "git": git_info,
        "backend_routes": get_backend_routes(),
        "backend_python_files": get_python_files(),
        "databases": {
            "lucchese_state": {
                "path": state_db,
                "schema": get_db_schema(state_db),
            },
            "conversations": {
                "path": conv_db,
                "schema": get_db_schema(conv_db),
            },
        },
        "profile_state_row": get_profile_row(state_db),
        "chroma_collections": get_chroma_collections(),
        "important_scripts": get_important_scripts(),
        "environment_variables": get_env_var_names(),
        "detected_gaps": detect_gaps(),
    }

    return snapshot, timestamp


def snapshot_to_markdown(snapshot, timestamp):
    """Convert snapshot dict to formatted markdown."""
    md = []
    md.append("# Lucchese System Snapshot\n")
    md.append(f"Generated: `{snapshot['timestamp']}`\n")

    # Usage instructions
    md.append("## Usage\n")
    md.append(
        "This snapshot was generated by `backend/system_snapshot.py`.\n"
        "Run it again anytime to refresh:\n"
        "```bash\n"
        "cd backend && python system_snapshot.py\n"
        "```\n"
    )

    # Git info
    md.append("## Git Info\n")
    md.append(f"- **Branch**: `{snapshot['git']['branch']}`\n")
    md.append(f"- **Commit**: `{snapshot['git']['commit']}`\n")
    md.append(f"- **Full commit**: `{snapshot['git']['full_commit']}`\n")

    # Backend routes
    md.append("\n## FastAPI Routes Detected\n")
    routes = snapshot["backend_routes"]
    if routes:
        for route in routes:
            md.append(f"- `{route}`\n")
    else:
        md.append("*(none detected)*\n")

    # Python files
    md.append("\n## Backend Python Files\n")
    files = snapshot["backend_python_files"]
    if files:
        for f in files:
            md.append(f"- `{f}`\n")
    else:
        md.append("*(none found)*\n")

    # Databases
    md.append("\n## Databases\n")
    for db_name, db_info in snapshot["databases"].items():
        md.append(f"\n### {db_name} (`{db_info['path']}`)\n")
        schema = db_info["schema"]
        if schema == "unavailable":
            md.append("**Status**: unavailable (file not found)\n")
        elif isinstance(schema, str) and schema.startswith("error"):
            md.append(f"**Status**: {schema}\n")
        elif isinstance(schema, dict):
            md.append(f"**Tables**: {len(schema)}\n")
            for table, columns in sorted(schema.items()):
                md.append(f"\n#### {table}\n")
                md.append(f"Columns: {', '.join(f'`{c}`' for c in columns)}\n")
        else:
            md.append(f"**Status**: {schema}\n")

    # Profile state
    md.append("\n## Profile State Row\n")
    profile = snapshot["profile_state_row"]
    if profile == "unavailable":
        md.append("**Status**: unavailable (database not found)\n")
    elif profile == "empty":
        md.append("**Status**: empty (no id=1 row in profile_state table)\n")
    elif isinstance(profile, dict):
        md.append("**Current profile_state (id=1)**:\n")
        for key, value in sorted(profile.items()):
            if value is None:
                md.append(f"- `{key}`: null\n")
            else:
                md.append(f"- `{key}`: {value}\n")
    else:
        md.append(f"**Status**: {profile}\n")

    # ChromaDB collections
    md.append("\n## ChromaDB Collections\n")
    chroma = snapshot["chroma_collections"]
    if chroma == "unavailable":
        md.append("**Status**: unavailable (chromadb package or chroma_db folder not found)\n")
    elif chroma == "empty":
        md.append("**Status**: empty (no collections)\n")
    elif isinstance(chroma, dict):
        for coll_name, count in sorted(chroma.items()):
            md.append(f"- `{coll_name}`: {count} items\n")
    else:
        md.append(f"**Status**: {chroma}\n")

    # Important scripts
    md.append("\n## Important Scripts\n")
    scripts = snapshot["important_scripts"]
    for script, status in sorted(scripts.items()):
        md.append(f"- `{script}`: {status}\n")

    # Environment variables
    md.append("\n## Environment Variables\n")
    env_vars = snapshot["environment_variables"]
    if env_vars == "unavailable":
        md.append("**Status**: .env file not found\n")
    elif isinstance(env_vars, str):
        md.append(f"**Status**: {env_vars}\n")
    else:
        if env_vars:
            for var in env_vars:
                md.append(f"- `{var}`\n")
        else:
            md.append("*(none found)*\n")

    # Detected gaps
    md.append("\n## Known Gaps\n")
    gaps = snapshot["detected_gaps"]
    for gap in gaps:
        md.append(f"- {gap}\n")

    return "\n".join(md)


def main():
    """Generate snapshot and write to docs/system_snapshot.md."""
    try:
        os.chdir(Path(__file__).parent.parent)  # Change to repo root
    except Exception:
        pass  # Already at root

    snapshot, timestamp = generate_snapshot()

    # Write JSON snapshot (optional, for debugging)
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)

    md_path = output_dir / "system_snapshot.md"
    md_content = snapshot_to_markdown(snapshot, timestamp)

    with open(md_path, "w") as f:
        f.write(md_content)

    print(f"[OK] Snapshot written to {md_path}")
    print(f"Timestamp: {snapshot['timestamp']}")
    print(f"Git: {snapshot['git']['branch']} @ {snapshot['git']['commit']}")


if __name__ == "__main__":
    main()
