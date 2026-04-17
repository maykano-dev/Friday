"""Friday - permanent lightweight memory vault.

Pure-stdlib SQLite store. No vector DB, no pandas, no torch.
Keyword extraction is a simple stopword-filtered frequency pick so it
costs essentially zero RAM.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from typing import List, Optional

_CHROMA_CLIENT = None
_CHROMA_COLLECTION = None

def _get_chroma_collection():
    global _CHROMA_CLIENT, _CHROMA_COLLECTION
    if _CHROMA_CLIENT is None:
        try:
            import chromadb
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
            os.makedirs(db_path, exist_ok=True)
            _CHROMA_CLIENT = chromadb.PersistentClient(path=db_path)
            _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(name="semantic_vault")
        except Exception as e:
            print(f"[Memory Vault] Chroma DB init failed: {e}")
    return _CHROMA_COLLECTION

def index_data(content: str, type_meta: str) -> None:
    if not str(content).strip(): return
    col = _get_chroma_collection()
    if col:
        import uuid
        try:
            col.add(
                documents=[str(content)],
                metadatas=[{"type": type_meta, "timestamp": datetime.utcnow().isoformat(timespec="seconds")}],
                ids=[str(uuid.uuid4())]
            )
        except Exception as e:
            print(f"[Memory Vault] Chroma index error: {e}")

def semantic_search(query: str, n_results: int = 3) -> List[str]:
    if not query.strip(): return []
    col = _get_chroma_collection()
    if col:
        try:
            if col.count() == 0: return []
            res = col.query(query_texts=[query], n_results=n_results)
            docs = res.get('documents', [[]])
            if docs: return docs[0]
        except Exception as e:
            print(f"[Memory Vault] Chroma search error: {e}")
    return []

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "friday_brain.db")

MAX_KEYWORDS = 3
MIN_KEYWORD_LEN = 3
TOP_RESULTS = 3

# Small hand-picked English stopword set. Kept inline so we don't pull nltk.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren as at be
    because been before being below between both but by can cant could couldnt
    did didnt do does doesnt doing dont down during each few for from further
    had hadnt has hasnt have havent having he her here hers herself him himself
    his how i id im ive if in into is isnt it its itself just lets me might more
    most must my myself no nor not now of off on once only or other ought our
    ours ourselves out over own same shant she should shouldnt so some such
    than that thats the their theirs them themselves then there theres these
    they theyre this those through to too under until up very was wasnt we
    were werent what whats when where which while who whos whom why with wont
    would wouldnt you youre your yours yourself yourselves
    also get got gonna wanna like really thing things stuff something anything
    know think feel said say told tell ask asked just
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]+")


def _extract_keywords(text: str, max_n: int = MAX_KEYWORDS) -> List[str]:
    """Return up to `max_n` salient keywords from `text`.

    Algorithm: tokenize -> lowercase -> drop stopwords and very short tokens
    -> pick by frequency, then by token length as tiebreaker.
    """
    if not text:
        return []

    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    tokens = [t for t in tokens if len(t) >= MIN_KEYWORD_LEN and t not in _STOPWORDS]
    if not tokens:
        return []

    counts = Counter(tokens)
    # Sort by frequency desc, then by length desc (longer words tend to be
    # more specific), then alphabetically for determinism.
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in ranked[:max_n]]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create friday_brain.db and the memories table if they don't exist."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                keyword_tags  TEXT    NOT NULL,
                memory_text   TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_vault (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                bug_pattern   TEXT    NOT NULL,
                fix_pattern   TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coding_tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                code          TEXT    NOT NULL,
                status        TEXT    NOT NULL,
                best_practices_summary TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS context_insights (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                insight       TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(keyword_tags)"
        )
        conn.commit()


def store_memory(text: str) -> bool:
    """Extract keywords from `text` and persist the memory. Returns True on success."""
    if not text or not text.strip():
        return False

    keywords = _extract_keywords(text)
    if not keywords:
        # Nothing distinctive to tag with -> skip rather than store junk.
        return False

    tags = ",".join(keywords)
    timestamp = datetime.utcnow().isoformat(timespec="seconds")

    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO memories (timestamp, keyword_tags, memory_text) VALUES (?, ?, ?)",
                (timestamp, tags, text.strip()),
            )
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[Friday Vault] store_memory failed: {e}")
        return False


def get_recent_memories(limit: int = 10) -> List[str]:
    """Return the most recently stored raw memory strings for offline synthesis."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT memory_text FROM memories ORDER BY id DESC LIMIT ?", 
                (limit,)
            ).fetchall()
            return [r["memory_text"] for r in rows]
    except sqlite3.Error as e:
        print(f"[Friday Vault] get_recent_memories failed: {e}")
        return []

# Alias to prevent external module tracebacks
add_memory = store_memory


def retrieve_memory(user_query: str) -> List[str]:
    """Return up to TOP_RESULTS memory_text strings most relevant to `user_query`.

    Relevance = number of extracted keywords that appear (via LIKE) in either
    the memory_text or the keyword_tags of a row. Ties broken by recency.
    """
    keywords = _extract_keywords(user_query)
    if not keywords:
        return []

    # Build a dynamic "score = (kw1 hit) + (kw2 hit) + ..." expression so the
    # DB ranks rows for us in a single query. Still pure SQLite.
    score_terms = []
    where_terms = []
    params: List[str] = []
    for kw in keywords:
        like = f"%{kw}%"
        score_terms.append(
            "(CASE WHEN memory_text LIKE ? OR keyword_tags LIKE ? THEN 1 ELSE 0 END)"
        )
        params.extend([like, like])
        where_terms.append("memory_text LIKE ? OR keyword_tags LIKE ?")
        params.extend([like, like])

    score_expr = " + ".join(score_terms)
    where_expr = " OR ".join(where_terms)

    sql = (
        f"SELECT memory_text, ({score_expr}) AS score "
        f"FROM memories "
        f"WHERE {where_expr} "
        f"ORDER BY score DESC, id DESC "
        f"LIMIT ?"
    )
    params.append(TOP_RESULTS)

    try:
        with _connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as e:
        print(f"[Friday Vault] retrieve_memory failed: {e}")
        return []

    return [r["memory_text"] for r in rows if r["score"] > 0]


def store_knowledge(bug_pattern: str, fix_pattern: str) -> bool:
    """Store a resolved bug and its fix in the knowledge vault."""
    if not bug_pattern or not fix_pattern:
        return False
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO knowledge_vault (timestamp, bug_pattern, fix_pattern) VALUES (?, ?, ?)",
                (timestamp, bug_pattern.strip(), fix_pattern.strip()),
            )
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[Friday Vault] store_knowledge failed: {e}")
        return False


def log_coding_task(code: str, status: str) -> int:
    """Log a coding execution result. Status usually 'Success' or 'Failed'."""
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "INSERT INTO coding_tasks (timestamp, code, status) VALUES (?, ?, ?)",
                (timestamp, code.strip(), status.strip()),
            )
            conn.commit()
            return cursor.lastrowid or 0
    except sqlite3.Error as e:
        print(f"[Friday Vault] log_coding_task failed: {e}")
        return 0


def get_unprocessed_failed_tasks() -> List[dict]:
    """Fetch un-summarized failed tasks for the learning engine."""
    try:
        with _connect() as conn:
            # We also treat 'Complex' as un-summarized if we add that later, but
            # currently we look for 'Failed' with no summary.
            rows = conn.execute(
                "SELECT id, code, status FROM coding_tasks "
                "WHERE status = 'Failed' AND best_practices_summary IS NULL "
                "ORDER BY id ASC LIMIT 5"
            ).fetchall()
            return [{"id": r["id"], "code": r["code"], "status": r["status"]} for r in rows]
    except sqlite3.Error as e:
        print(f"[Friday Vault] get_unprocessed_failed_tasks failed: {e}")
        return []


def mark_task_processed(task_id: int, summary: str) -> bool:
    """Update a coding task with its generated summary."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE coding_tasks SET best_practices_summary = ? WHERE id = ?",
                (summary, task_id),
            )
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[Friday Vault] mark_task_processed failed: {e}")
        return False


def inject_context_insight(insight: str) -> bool:
    """Store an LLM-synthesized context insight into long-term memory."""
    if not insight or not insight.strip():
        return False
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO context_insights (timestamp, insight) VALUES (?, ?)",
                (timestamp, insight.strip()),
            )
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[Friday Vault] inject_context_insight failed: {e}")
        return False


def get_latest_context_insight() -> Optional[str]:
    """Retrieve the single most recent context insight."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT insight FROM context_insights ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return row["insight"]
            return None
    except sqlite3.Error as e:
        print(f"[Friday Vault] get_latest_context_insight failed: {e}")
        return None


# Ensure the DB + table exist as soon as the module is imported, so callers
# don't have to remember to call init_db() first.
init_db()


if __name__ == "__main__":
    # Tiny self-test / seed routine.
    store_memory("My birthday is on March 14th and I love chocolate cake.")
    store_memory("I work as a software engineer focused on offline AI tools.")
    store_memory("My dog's name is Luna and she is a border collie.")
    print("Query: when is my birthday?")
    for m in retrieve_memory("when is my birthday?"):
        print(" -", m)
    print("Query: tell me about my dog")
    for m in retrieve_memory("tell me about my dog"):
        print(" -", m)
