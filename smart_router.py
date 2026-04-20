"""Zara - Smart Model Router (Zero-Cost Edition)

Routes requests to the best FREE endpoint based on availability:
- Groq API (free tier: 30 req/min, 14,400 req/day)
- Local Ollama with tiny model (qwen2.5:1.5b - runs on CPU)
- DuckDuckGo search (free web research)
- Cached responses (avoid repeat API calls)

Author: Zara Enhancement Package
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List


class ModelEndpoint(Enum):
    """Available FREE endpoints."""
    GROQ = "groq"
    OLLAMA_TINY = "ollama_tiny"
    CACHE = "cache"
    DUCKDUCKGO = "ddg"
    LOCAL_FALLBACK = "fallback"


@dataclass
class EndpointStatus:
    """Current status of an endpoint."""
    endpoint: ModelEndpoint
    is_available: bool = True
    rate_limited_until: Optional[datetime] = None
    consecutive_failures: int = 0
    total_requests: int = 0


class SmartRouter:
    """
    Routes requests to the best free endpoint with:
    - Groq rate limit awareness
    - Response caching
    - Graceful degradation to tiny local model
    """

    GROQ_REQUESTS_PER_MINUTE = 30
    CACHE_DB_PATH = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "response_cache.db")
    CACHE_TTL_HOURS = 24

    def __init__(self):
        self.status: Dict[ModelEndpoint, EndpointStatus] = {
            endpoint: EndpointStatus(endpoint=endpoint)
            for endpoint in ModelEndpoint
        }
        self._request_log: List[datetime] = []
        self._init_cache_db()
        self._check_ollama_available()

    def _init_cache_db(self) -> None:
        """Initialize the response cache database."""
        try:
            with sqlite3.connect(self.CACHE_DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS response_cache (
                        query_hash TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        response TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        hit_count INTEGER DEFAULT 1
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_created ON response_cache(created_at)")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_hit_count ON response_cache(hit_count)")
        except Exception as e:
            print(f"[Router] Cache DB init failed: {e}")

    def _check_ollama_available(self) -> None:
        """Check if Ollama with tiny model is available."""
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                models = [m.get("name", "")
                          for m in resp.json().get("models", [])]
                if any("1.5b" in m.lower() or "tiny" in m.lower() for m in models):
                    self.status[ModelEndpoint.OLLAMA_TINY].is_available = True
                    print("[Router] Ollama tiny model available")
                else:
                    print("[Router] Run: ollama pull qwen2.5:1.5b")
                    self.status[ModelEndpoint.OLLAMA_TINY].is_available = False
            else:
                self.status[ModelEndpoint.OLLAMA_TINY].is_available = False
        except Exception:
            self.status[ModelEndpoint.OLLAMA_TINY].is_available = False
            print("[Router] Ollama not running (install for offline fallback)")

    def _check_groq_rate_limits(self) -> bool:
        """Check if we're within Groq free tier limits."""
        now = datetime.now()

        if self.status[ModelEndpoint.GROQ].rate_limited_until:
            if now > self.status[ModelEndpoint.GROQ].rate_limited_until:
                self.status[ModelEndpoint.GROQ].is_available = True
                self.status[ModelEndpoint.GROQ].rate_limited_until = None
                print("[Router] Groq rate limit cooldown expired. Re-enabling.")
            else:
                return False

        self._request_log = [
            t for t in self._request_log if t > now - timedelta(minutes=1)]

        if len(self._request_log) >= self.GROQ_REQUESTS_PER_MINUTE:
            self.status[ModelEndpoint.GROQ].rate_limited_until = now + \
                timedelta(minutes=1)
            self.status[ModelEndpoint.GROQ].is_available = False
            print(
                f"[Router] Groq rate limited until {self.status[ModelEndpoint.GROQ].rate_limited_until.strftime('%H:%M:%S')}")
            return False

        self.status[ModelEndpoint.GROQ].is_available = True
        return True

    def _get_cache_key(self, query: str, context: str = "") -> str:
        """Generate a cache key for a query."""
        content = f"{query}|{context[:100]}"
        return hashlib.md5(content.encode()).hexdigest()

    def _check_cache(self, query: str, context: str = "") -> Optional[str]:
        """Check if we have a cached response."""
        cache_key = self._get_cache_key(query, context)

        try:
            with sqlite3.connect(self.CACHE_DB_PATH) as conn:
                cursor = conn.execute("""
                    SELECT response FROM response_cache 
                    WHERE query_hash = ? 
                    AND datetime(created_at) > datetime('now', ?)
                """, (cache_key, f"-{self.CACHE_TTL_HOURS} hours"))

                row = cursor.fetchone()
                if row:
                    conn.execute(
                        "UPDATE response_cache SET hit_count = hit_count + 1 WHERE query_hash = ?", (cache_key,))
                    print(f"[Router] Cache hit! Saved API call.")
                    return row[0]
        except Exception as e:
            print(f"[Router] Cache check failed: {e}")

        return None

    def _save_to_cache(self, query: str, response: str, endpoint: str, context: str = "") -> None:
        """Save a response to cache."""
        cache_key = self._get_cache_key(query, context)

        try:
            with sqlite3.connect(self.CACHE_DB_PATH) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO response_cache 
                    (query_hash, query, response, endpoint, created_at, hit_count)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                """, (cache_key, query[:500], response, endpoint))
        except Exception as e:
            print(f"[Router] Cache save failed: {e}")

    def _query_ollama_tiny(self, prompt: str, system_prompt: str = "") -> str:
        """Query the tiny local Ollama model."""
        try:
            import requests

            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            models = resp.json().get("models", [])
            tiny_model = next(
                (m["name"] for m in models if "1.5b" in m["name"].lower()
                 or "tiny" in m["name"].lower()),
                "qwen2.5:1.5b"
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": tiny_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 512, "num_ctx": 2048}
            }

            resp = requests.post(
                "http://localhost:11434/api/chat", json=payload, timeout=60)
            resp.raise_for_status()

            result = resp.json().get("message", {}).get("content", "")
            self.status[ModelEndpoint.OLLAMA_TINY].total_requests += 1
            self.status[ModelEndpoint.OLLAMA_TINY].consecutive_failures = 0
            return result

        except Exception as e:
            self.status[ModelEndpoint.OLLAMA_TINY].consecutive_failures += 1
            if self.status[ModelEndpoint.OLLAMA_TINY].consecutive_failures > 3:
                self.status[ModelEndpoint.OLLAMA_TINY].is_available = False
            return f"[Local model unavailable: {str(e)[:50]}]"

    def _query_groq(self, prompt: str, system_prompt: str = "") -> str:
        """Query Groq API (free tier)."""
        import requests

        groq_key = os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            self.status[ModelEndpoint.GROQ].is_available = False
            raise Exception("GROQ_API_KEY not set")

        self._request_log.append(datetime.now())

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        headers = {"Authorization": f"Bearer {groq_key}",
                   "Content-Type": "application/json"}

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()

        self.status[ModelEndpoint.GROQ].total_requests += 1
        self.status[ModelEndpoint.GROQ].consecutive_failures = 0
        return resp.json()["choices"][0]["message"]["content"]

    def _search_duckduckgo(self, query: str) -> str:
        """Search DuckDuckGo for free."""
        try:
            import requests
            from urllib.parse import quote_plus

            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json",
                        "no_html": 1, "skip_disambig": 1},
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            data = resp.json()

            if data.get("AbstractText"):
                return data["AbstractText"]
            elif data.get("Answer"):
                return data["Answer"]
            elif data.get("Definition"):
                return data["Definition"]
            elif data.get("RelatedTopics"):
                topics = data["RelatedTopics"][:3]
                texts = [t.get("Text", "") for t in topics if t.get("Text")]
                if texts:
                    return " | ".join(texts)

            return ""

        except Exception as e:
            print(f"[Router] DDG search failed: {e}")
            return ""

    def route(self, query: str, system_prompt: str = "", allow_cache: bool = True, allow_web_search: bool = False) -> tuple:
        """
        Route a query to the best available free endpoint.
        Returns: (response_text, endpoint_used)
        """
        query = query.strip()
        if not query:
            return "I didn't catch that.", ModelEndpoint.LOCAL_FALLBACK

        # 1. Check cache first
        if allow_cache:
            cached = self._check_cache(query, system_prompt)
            if cached:
                return cached, ModelEndpoint.CACHE

        # 2. Web search for appropriate queries
        web_keywords = ["search", "find information", "look up",
                        "what is", "who is", "weather", "news", "latest"]
        if allow_web_search and any(kw in query.lower() for kw in web_keywords):
            web_result = self._search_duckduckgo(query)
            if web_result and len(web_result) > 50:
                self._save_to_cache(query, web_result,
                                    "duckduckgo", system_prompt)
                self.status[ModelEndpoint.DUCKDUCKGO].total_requests += 1
                return web_result, ModelEndpoint.DUCKDUCKGO

        # 3. Try Groq
        if self._check_groq_rate_limits() and self.status[ModelEndpoint.GROQ].is_available:
            try:
                response = self._query_groq(query, system_prompt)
                self._save_to_cache(query, response, "groq", system_prompt)
                return response, ModelEndpoint.GROQ
            except Exception as e:
                print(f"[Router] Groq failed: {e}")
                self.status[ModelEndpoint.GROQ].consecutive_failures += 1
                if self.status[ModelEndpoint.GROQ].consecutive_failures > 3:
                    self.status[ModelEndpoint.GROQ].is_available = False

        # 4. Fall back to local tiny Ollama
        if self.status[ModelEndpoint.OLLAMA_TINY].is_available:
            try:
                response = self._query_ollama_tiny(query, system_prompt)
                if not response.startswith("[Local model unavailable"):
                    return response, ModelEndpoint.OLLAMA_TINY
            except Exception as e:
                print(f"[Router] Ollama tiny failed: {e}")

        # 5. Ultimate fallback
        fallback = self._get_static_fallback(query)
        return fallback, ModelEndpoint.LOCAL_FALLBACK

    def _get_static_fallback(self, query: str) -> str:
        """Generate a static fallback response."""
        query_lower = query.lower()

        if any(w in query_lower for w in ["hello", "hi", "hey"]):
            return "Hello! I'm in offline mode but still ready to help with system tasks."
        if "time" in query_lower:
            return f"The current time is {datetime.now().strftime('%I:%M %p')}."
        if "date" in query_lower:
            return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."
        if any(w in query_lower for w in ["help", "can you", "what can"]):
            return "I can create files, run scripts, and manage your system even in offline mode."

        return "I'm having trouble connecting. I can still help with system tasks like creating files or running scripts."


_router: Optional[SmartRouter] = None


def get_router() -> SmartRouter:
    """Get the global SmartRouter instance."""
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router


def route_query(query: str, system_prompt: str = "", allow_web: bool = False) -> str:
    """Convenience function for routing a query."""
    router = get_router()
    response, endpoint = router.route(
        query, system_prompt, allow_web_search=allow_web)
    print(f"[Zara] Used: {endpoint.value}")
    return response
