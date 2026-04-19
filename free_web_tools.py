"""Friday - Free Web Tools (Zero API Cost) - EXPANDED EDITION

Web research and utilities using only free, no-auth-required endpoints.

CATEGORIES:
- Knowledge: Wikipedia, DuckDuckGo, Dictionary, Thesaurus
- News: Hacker News, Dev.to, RSS feeds
- Entertainment: Jokes, Quotes, Cat Facts, Dog Facts, Chuck Norris
- Utility: Weather, Crypto, Exchange Rates, Time Zones
- Development: GitHub, NPM, PyPI, CVE Security
- Fun: Bored API, Advice, Useless Facts, Numbers API
- Images: Placeholder images, QR codes
- Data: Country info, University info, Public holidays
"""

from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
from urllib.parse import quote_plus, urlencode

import requests


class FreeWebTools:
    """Web tools that cost $0 and require zero API keys."""

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self._rate_limit: Dict[str, float] = {}
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._cache_ttl = 300  # 5 minutes default

    def _rate_limit_check(self, key: str, min_interval: float = 1.0) -> None:
        """Simple rate limiting."""
        now = time.time()
        if key in self._rate_limit:
            elapsed = now - self._rate_limit[key]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._rate_limit[key] = time.time()

    def _cached_request(self, cache_key: str, url: str, ttl: int = 300, **kwargs) -> Optional[Any]:
        """Make a cached HTTP request."""
        now = time.time()
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if now - timestamp < ttl:
                return data

        try:
            resp = self.session.get(url, timeout=10, **kwargs)
            resp.raise_for_status()
            data = resp.json() if "application/json" in resp.headers.get("content-type",
                                                                         "") else resp.text
            self._cache[cache_key] = (data, now)
            return data
        except Exception as e:
            print(f"[WebTools] Request failed: {e}")
            return None

    # ==================== KNOWLEDGE & SEARCH ====================

    def search_duckduckgo(self, query: str) -> Optional[str]:
        """Get instant answer from DuckDuckGo."""
        self._rate_limit_check("ddg", 1.0)

        try:
            resp = self.session.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json",
                        "no_html": 1, "skip_disambig": 1},
                timeout=10
            )
            data = resp.json()

            if data.get("AbstractText"):
                source = data.get("AbstractSource", "DuckDuckGo")
                return f"{data['AbstractText']}\n\n📌 Source: {source}"
            elif data.get("Answer"):
                return f"💡 Answer: {data['Answer']}"
            elif data.get("Definition"):
                return f"📖 Definition: {data['Definition']}"
            elif data.get("RelatedTopics"):
                topics = data["RelatedTopics"][:3]
                texts = []
                for t in topics:
                    if t.get("Text"):
                        texts.append(t["Text"])
                if texts:
                    return "🔍 Related:\n• " + "\n• ".join(texts)
            return None
        except Exception as e:
            print(f"[WebTools] DDG error: {e}")
            return None

    def search_wikipedia(self, query: str) -> Optional[str]:
        """Get Wikipedia summary."""
        self._rate_limit_check("wiki", 0.5)

        try:
            resp = self.session.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                quote_plus(query),
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get('extract', '')[:2000]
                title = data.get('title', query)
                url = data.get('content_urls', {}).get(
                    'desktop', {}).get('page', '')
                if extract:
                    return f"📚 {title}\n\n{extract}\n\n🔗 {url}"
            return None
        except Exception as e:
            print(f"[WebTools] Wikipedia error: {e}")
            return None

    def get_word_definition(self, word: str) -> Optional[str]:
        """Get dictionary definition."""
        self._rate_limit_check("dict", 1.0)

        try:
            resp = self.session.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(word)}",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    word_data = data[0]
                    word_name = word_data.get("word", word)
                    meanings = word_data.get("meanings", [])

                    if meanings:
                        result = f"📖 {word_name}\n\n"
                        for i, meaning in enumerate(meanings[:2]):
                            pos = meaning.get("partOfSpeech", "")
                            definitions = meaning.get("definitions", [])
                            if definitions:
                                definition = definitions[0].get(
                                    "definition", "")
                                example = definitions[0].get("example", "")
                                result += f"[{pos}] {definition}\n"
                                if example:
                                    result += f"    Example: \"{example}\"\n"

                        phonetics = word_data.get("phonetics", [])
                        if phonetics:
                            for p in phonetics:
                                if p.get("text"):
                                    result += f"\n🔊 {p['text']}"
                                    break

                        return result
            return None
        except Exception as e:
            print(f"[WebTools] Dictionary error: {e}")
            return None

    def get_synonyms(self, word: str) -> Optional[str]:
        """Get synonyms from Datamuse API."""
        self._rate_limit_check("synonym", 0.5)

        try:
            resp = self.session.get(
                f"https://api.datamuse.com/words?rel_syn={quote_plus(word)}&max=10",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    words = [item.get("word", "") for item in data[:10]]
                    return f"📝 Synonyms for '{word}': " + ", ".join(words)
            return None
        except Exception as e:
            print(f"[WebTools] Synonym error: {e}")
            return None

    def get_rhymes(self, word: str) -> Optional[str]:
        """Get rhyming words."""
        self._rate_limit_check("rhyme", 0.5)

        try:
            resp = self.session.get(
                f"https://api.datamuse.com/words?rel_rhy={quote_plus(word)}&max=10",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    words = [item.get("word", "") for item in data[:10]]
                    return f"🎵 Rhymes with '{word}': " + ", ".join(words)
            return None
        except Exception as e:
            print(f"[WebTools] Rhyme error: {e}")
            return None

    # ==================== NEWS & TECH ====================

    def get_hacker_news_top(self, limit: int = 5) -> Optional[str]:
        """Get top stories from Hacker News."""
        self._rate_limit_check("hn", 2.0)

        try:
            resp = self.session.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=10
            )
            if resp.status_code == 200:
                story_ids = resp.json()[:limit]

                result = "🔥 Hacker News Top Stories:\n\n"
                for i, story_id in enumerate(story_ids, 1):
                    story_resp = self.session.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                        timeout=5
                    )
                    if story_resp.status_code == 200:
                        story = story_resp.json()
                        title = story.get("title", "Unknown")
                        score = story.get("score", 0)
                        comments = story.get("descendants", 0)
                        result += f"{i}. {title}\n   📊 {score} pts | 💬 {comments} comments\n\n"

                return result.strip()
            return None
        except Exception as e:
            print(f"[WebTools] Hacker News error: {e}")
            return None

    def get_dev_to_top(self, limit: int = 5) -> Optional[str]:
        """Get top articles from DEV.to."""
        self._rate_limit_check("devto", 2.0)

        try:
            resp = self.session.get(
                "https://dev.to/api/articles",
                params={"top": 1, "per_page": limit},
                timeout=10
            )
            if resp.status_code == 200:
                articles = resp.json()
                result = "💻 DEV.to Top Articles:\n\n"
                for i, article in enumerate(articles, 1):
                    title = article.get("title", "Unknown")
                    author = article.get("user", {}).get("name", "Unknown")
                    tags = ", ".join(article.get("tag_list", [])[:3])
                    reactions = article.get("positive_reactions_count", 0)
                    result += f"{i}. {title}\n   👤 {author} | 🏷️ {tags} | ❤️ {reactions}\n\n"

                return result.strip()
            return None
        except Exception as e:
            print(f"[WebTools] DEV.to error: {e}")
            return None

    # ==================== ENTERTAINMENT ====================

    def get_random_joke(self) -> str:
        """Get a random dad joke."""
        self._rate_limit_check("joke", 1.0)

        try:
            resp = self.session.get(
                "https://icanhazdadjoke.com/",
                headers={"Accept": "application/json"},
                timeout=10
            )
            if resp.status_code == 200:
                joke = resp.json().get("joke", "No joke found.")
                return f"😄 {joke}"
        except Exception as e:
            print(f"[WebTools] Joke error: {e}")

        try:
            resp = self.session.get(
                "https://v2.jokeapi.dev/joke/Any?type=single", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("type") == "single":
                    return f"😄 {data.get('joke', 'No joke found.')}"
        except:
            pass

        return "Why did the AI cross the road? To optimize the other side! 😄"

    def get_chuck_norris_joke(self) -> str:
        """Get a Chuck Norris joke."""
        self._rate_limit_check("chuck", 1.0)

        try:
            resp = self.session.get(
                "https://api.chucknorris.io/jokes/random", timeout=10)
            if resp.status_code == 200:
                joke = resp.json().get("value", "")
                return f"💪 {joke}"
        except Exception as e:
            print(f"[WebTools] Chuck Norris error: {e}")

        return "💪 Chuck Norris doesn't need an API. The API needs Chuck Norris."

    def get_random_quote(self) -> str:
        """Get a random quote."""
        self._rate_limit_check("quote", 1.0)

        try:
            resp = self.session.get(
                "https://api.quotable.io/random", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return f"💬 \"{data.get('content', '')}\"\n   — {data.get('author', 'Unknown')}"
        except Exception as e:
            print(f"[WebTools] Quote error: {e}")

        return "💬 \"The only limit to our realization of tomorrow is our doubts of today.\"\n   — Franklin D. Roosevelt"

    def get_cat_fact(self) -> str:
        """Get a random cat fact."""
        self._rate_limit_check("catfact", 1.0)

        try:
            resp = self.session.get("https://catfact.ninja/fact", timeout=10)
            if resp.status_code == 200:
                return f"🐱 {resp.json().get('fact', 'Cats are amazing.')}"
        except Exception as e:
            print(f"[WebTools] Cat fact error: {e}")

        return "🐱 Cats spend 70% of their lives sleeping."

    def get_dog_fact(self) -> str:
        """Get a random dog fact."""
        self._rate_limit_check("dogfact", 1.0)

        try:
            resp = self.session.get(
                "https://dogapi.dog/api/v2/facts", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                facts = data.get("data", [])
                if facts:
                    fact = facts[0].get("attributes", {}).get("body", "")
                    return f"🐕 {fact}"
        except Exception as e:
            print(f"[WebTools] Dog fact error: {e}")

        return "🐕 Dogs can understand up to 250 words and gestures."

    def get_useless_fact(self) -> str:
        """Get a random useless fact."""
        self._rate_limit_check("useless", 1.0)

        try:
            resp = self.session.get(
                "https://uselessfacts.jsph.pl/api/v2/facts/random", timeout=10)
            if resp.status_code == 200:
                return f"🤔 {resp.json().get('text', '')}"
        except Exception as e:
            print(f"[WebTools] Useless fact error: {e}")

        return "🤔 A group of porcupines is called a prickle."

    def get_advice(self) -> str:
        """Get random advice."""
        self._rate_limit_check("advice", 1.0)

        try:
            resp = self.session.get(
                "https://api.adviceslip.com/advice", timeout=10)
            if resp.status_code == 200:
                slip = resp.json().get("slip", {})
                return f"💡 {slip.get('advice', 'Take a deep breath.')}"
        except Exception as e:
            print(f"[WebTools] Advice error: {e}")

        return "💡 Always save your work before taking a break."

    def get_bored_activity(self) -> str:
        """Get a random activity suggestion."""
        self._rate_limit_check("bored", 1.0)

        try:
            resp = self.session.get(
                "https://www.boredapi.com/api/activity", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                activity = data.get('activity', '')
                type_ = data.get('type', '')
                participants = data.get('participants', 1)
                return f"🎯 {activity}\n   Type: {type_} | Participants: {participants}"
        except Exception as e:
            print(f"[WebTools] Bored error: {e}")

        return "🎯 Learn something new on YouTube."

    # ==================== NUMBERS & TRIVIA ====================

    def get_number_fact(self, number: int = None) -> str:
        """Get a fact about a number."""
        self._rate_limit_check("number", 0.5)

        try:
            url = f"http://numbersapi.com/{number if number else 'random'}/trivia"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                return f"🔢 {resp.text}"
        except Exception as e:
            print(f"[WebTools] Number fact error: {e}")

        return "🔢 42 is the answer to life, the universe, and everything."

    def get_date_fact(self, month: int = None, day: int = None) -> str:
        """Get a fact about a date."""
        self._rate_limit_check("datefact", 0.5)

        if month is None or day is None:
            today = datetime.now()
            month = today.month
            day = today.day

        try:
            resp = self.session.get(
                f"http://numbersapi.com/{month}/{day}/date", timeout=10)
            if resp.status_code == 200:
                return f"📅 {resp.text}"
        except Exception as e:
            print(f"[WebTools] Date fact error: {e}")

        return f"📅 On this day in history, something probably happened."

    # ==================== WEATHER & TIME ====================

    def get_weather(self, city: str) -> Optional[str]:
        """Get weather from wttr.in."""
        self._rate_limit_check("weather", 2.0)

        try:
            resp = self.session.get(
                f"https://wttr.in/{quote_plus(city)}?format=j1", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                location = data.get("nearest_area", [{}])[0]

                return (
                    f"🌍 Weather in {city}:\n"
                    f"🌡️ {current.get('temp_C', '?')}°C (feels like {current.get('FeelsLikeC', '?')}°C)\n"
                    f"☁️ {current.get('weatherDesc', [{}])[0].get('value', 'Unknown')}\n"
                    f"💧 Humidity: {current.get('humidity', '?')}%\n"
                    f"💨 Wind: {current.get('windspeedKmph', '?')} km/h\n"
                    f"👁️ Visibility: {current.get('visibility', '?')} km\n"
                    f"☀️ UV Index: {current.get('uvIndex', '?')}"
                )
            return None
        except Exception as e:
            print(f"[WebTools] Weather error: {e}")
            return None

    def get_astronomy(self, city: str) -> Optional[str]:
        """Get sun/moon times."""
        self._rate_limit_check("astro", 2.0)

        try:
            resp = self.session.get(
                f"https://wttr.in/{quote_plus(city)}?format=j1", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                weather = data.get("weather", [{}])[0]
                astronomy = weather.get("astronomy", [{}])[0]

                return (
                    f"🌅 Astronomy for {city}:\n"
                    f"☀️ Sunrise: {astronomy.get('sunrise', '?')}\n"
                    f"🌙 Sunset: {astronomy.get('sunset', '?')}\n"
                    f"🌕 Moonrise: {astronomy.get('moonrise', '?')}\n"
                    f"🌑 Moonset: {astronomy.get('moonset', '?')}\n"
                    f"🌓 Moon Phase: {astronomy.get('moon_phase', '?')}"
                )
            return None
        except Exception as e:
            print(f"[WebTools] Astronomy error: {e}")
            return None

    def get_timezone_time(self, timezone: str) -> Optional[str]:
        """Get current time in a timezone."""
        self._rate_limit_check("timezone", 1.0)

        try:
            resp = self.session.get(
                f"https://worldtimeapi.org/api/timezone/{quote_plus(timezone)}",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                dt = datetime.fromisoformat(
                    data.get("datetime", "").replace("Z", "+00:00"))
                return (
                    f"🕐 {data.get('timezone', timezone)}\n"
                    f"   {dt.strftime('%I:%M %p, %A, %B %d, %Y')}\n"
                    f"   UTC Offset: {data.get('utc_offset', '?')}"
                )
            return None
        except Exception as e:
            print(f"[WebTools] Timezone error: {e}")
            return None

    def list_timezones(self) -> List[str]:
        """List available timezones."""
        try:
            resp = self.session.get(
                "https://worldtimeapi.org/api/timezone", timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return ["America/New_York", "Europe/London", "Asia/Tokyo", "Australia/Sydney"]

    # ==================== CRYPTO & FINANCE ====================

    def get_crypto_price(self, coin: str = "bitcoin") -> Optional[str]:
        """Get crypto price from CoinGecko."""
        self._rate_limit_check("crypto", 5.0)

        coin_map = {
            "btc": "bitcoin", "eth": "ethereum", "doge": "dogecoin",
            "sol": "solana", "ada": "cardano", "xrp": "ripple",
            "dot": "polkadot", "matic": "matic-network"
        }
        coin_id = coin_map.get(coin.lower(), coin.lower())

        try:
            resp = self.session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true"
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                coin_data = data.get(coin_id, {})
                price = coin_data.get("usd", 0)
                change = coin_data.get("usd_24h_change", 0)
                market_cap = coin_data.get("usd_market_cap", 0)

                change_symbol = "📈" if change > 0 else "📉"
                return (
                    f"₿ {coin.title()} Price: ${price:,.2f} USD\n"
                    f"{change_symbol} 24h Change: {change:.2f}%\n"
                    f"💰 Market Cap: ${market_cap:,.0f}"
                )
            elif resp.status_code == 429:
                return "⏳ Crypto API rate limited. Try again in a minute."
        except Exception as e:
            print(f"[WebTools] Crypto error: {e}")
        return None

    def get_exchange_rate(self, from_cur: str = "USD", to_cur: str = "EUR") -> Optional[str]:
        """Get exchange rate."""
        self._rate_limit_check("exchange", 2.0)

        try:
            resp = self.session.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_cur.upper()}",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("rates", {})
                rate = rates.get(to_cur.upper(), 0)
                if rate:
                    return (
                        f"💱 1 {from_cur.upper()} = {rate:.4f} {to_cur.upper()}\n"
                        f"   Updated: {data.get('date', 'today')}"
                    )
        except Exception as e:
            print(f"[WebTools] Exchange error: {e}")
        return None

    # ==================== DEVELOPMENT TOOLS ====================

    def get_github_user(self, username: str) -> Optional[str]:
        """Get GitHub user info."""
        self._rate_limit_check("github", 1.0)

        try:
            resp = self.session.get(
                f"https://api.github.com/users/{username}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return (
                    f"🐙 GitHub: {data.get('name', username)}\n"
                    f"   📝 Bio: {data.get('bio', 'N/A')}\n"
                    f"   📦 Public Repos: {data.get('public_repos', 0)}\n"
                    f"   👥 Followers: {data.get('followers', 0)} | Following: {data.get('following', 0)}\n"
                    f"   📍 Location: {data.get('location', 'N/A')}\n"
                    f"   🔗 {data.get('html_url', '')}"
                )
            elif resp.status_code == 404:
                return f"❌ User '{username}' not found."
            elif resp.status_code == 403:
                return "⏳ GitHub API rate limit exceeded. Try later."
        except Exception as e:
            print(f"[WebTools] GitHub error: {e}")
        return None

    def get_npm_package(self, package: str) -> Optional[str]:
        """Get NPM package info."""
        self._rate_limit_check("npm", 1.0)

        try:
            resp = self.session.get(
                f"https://registry.npmjs.org/{package}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get('dist-tags', {}).get('latest', 'unknown')
                versions = data.get('versions', {})
                latest_data = versions.get(latest, {})

                return (
                    f"📦 NPM: {data.get('name', package)}\n"
                    f"   📝 {data.get('description', 'No description')}\n"
                    f"   🏷️ Version: {latest}\n"
                    f"   📅 Updated: {data.get('time', {}).get('modified', 'unknown')[:10]}\n"
                    f"   👤 Author: {latest_data.get('author', {}).get('name', data.get('author', {}).get('name', 'Unknown'))}\n"
                    f"   🔗 https://www.npmjs.com/package/{package}"
                )
            elif resp.status_code == 404:
                return f"❌ Package '{package}' not found."
        except Exception as e:
            print(f"[WebTools] NPM error: {e}")
        return None

    def get_pypi_package(self, package: str) -> Optional[str]:
        """Get PyPI package info."""
        self._rate_limit_check("pypi", 1.0)

        try:
            resp = self.session.get(
                f"https://pypi.org/pypi/{package}/json", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                info = data.get('info', {})

                return (
                    f"🐍 PyPI: {info.get('name', package)}\n"
                    f"   📝 {info.get('summary', 'No description')}\n"
                    f"   🏷️ Version: {info.get('version', 'unknown')}\n"
                    f"   👤 Author: {info.get('author', 'Unknown')}\n"
                    f"   📊 License: {info.get('license', 'Unknown')}\n"
                    f"   🔗 {info.get('package_url', '')}"
                )
            elif resp.status_code == 404:
                return f"❌ Package '{package}' not found."
        except Exception as e:
            print(f"[WebTools] PyPI error: {e}")
        return None

    def get_http_status(self, code: int) -> Optional[str]:
        """Get HTTP status code description."""
        self._rate_limit_check("http", 0.5)

        try:
            resp = self.session.get(f"https://http.cat/{code}", timeout=5)
            if resp.status_code == 200:
                descriptions = {
                    200: "OK - Request succeeded",
                    201: "Created - Resource created",
                    204: "No Content",
                    301: "Moved Permanently",
                    302: "Found - Temporary redirect",
                    400: "Bad Request - Invalid syntax",
                    401: "Unauthorized - Authentication required",
                    403: "Forbidden - Access denied",
                    404: "Not Found - Resource doesn't exist",
                    418: "I'm a teapot - RFC 2324",
                    429: "Too Many Requests - Rate limited",
                    500: "Internal Server Error",
                    502: "Bad Gateway",
                    503: "Service Unavailable",
                }
                desc = descriptions.get(code, f"HTTP {code}")
                return f"🌐 HTTP {code}: {desc}\n   😺 https://http.cat/{code}"
        except Exception as e:
            print(f"[WebTools] HTTP status error: {e}")
        return None

    def get_cve_info(self, cve_id: str) -> Optional[str]:
        """Get CVE vulnerability info."""
        self._rate_limit_check("cve", 2.0)

        try:
            resp = self.session.get(
                f"https://cve.circl.lu/api/cve/{cve_id.upper()}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    summary = data.get('summary', 'No description')
                    cvss = data.get('cvss', 'N/A')
                    published = data.get('Published', 'Unknown')

                    return (
                        f"🔒 {cve_id.upper()}\n"
                        f"   📝 {summary[:200]}...\n"
                        f"   ⚠️ CVSS Score: {cvss}\n"
                        f"   📅 Published: {published}"
                    )
        except Exception as e:
            print(f"[WebTools] CVE error: {e}")
        return None

    # ==================== DATA & REFERENCE ====================

    def get_country_info(self, country: str) -> Optional[str]:
        """Get country information."""
        self._rate_limit_check("country", 1.0)

        try:
            resp = self.session.get(
                f"https://restcountries.com/v3.1/name/{quote_plus(country)}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    c = data[0]
                    name = c.get('name', {}).get('common', country)
                    capital = c.get('capital', ['Unknown'])[0]
                    region = c.get('region', 'Unknown')
                    subregion = c.get('subregion', 'Unknown')
                    population = c.get('population', 0)
                    area = c.get('area', 0)
                    currencies = c.get('currencies', {})
                    currency_str = ", ".join(
                        f"{v.get('name', k)} ({k})" for k, v in currencies.items())
                    languages = c.get('languages', {})
                    language_str = ", ".join(languages.values())

                    return (
                        f"🌍 {name}\n"
                        f"   🏛️ Capital: {capital}\n"
                        f"   📍 Region: {region} / {subregion}\n"
                        f"   👥 Population: {population:,}\n"
                        f"   📐 Area: {area:,} km²\n"
                        f"   💰 Currency: {currency_str}\n"
                        f"   🗣️ Languages: {language_str}\n"
                        f"   🚩 Flag: {c.get('flag', '')}"
                    )
        except Exception as e:
            print(f"[WebTools] Country error: {e}")
        return None

    def get_university_info(self, name: str) -> Optional[str]:
        """Search for universities."""
        self._rate_limit_check("uni", 1.0)

        try:
            resp = self.session.get(
                "http://universities.hipolabs.com/search",
                params={"name": name},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    results = data[:3]
                    result_str = f"🎓 Universities matching '{name}':\n\n"
                    for uni in results:
                        result_str += (
                            f"• {uni.get('name', 'Unknown')}\n"
                            f"  🌐 {uni.get('web_pages', ['N/A'])[0]}\n"
                            f"  📍 {uni.get('country', 'Unknown')}\n\n"
                        )
                    return result_str.strip()
        except Exception as e:
            print(f"[WebTools] University error: {e}")
        return None

    def get_public_holidays(self, country_code: str = "US", year: int = None) -> Optional[str]:
        """Get public holidays for a country."""
        self._rate_limit_check("holiday", 2.0)

        if year is None:
            year = datetime.now().year

        try:
            resp = self.session.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code.upper()}",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    result = f"📅 Public Holidays {year} ({country_code.upper()}):\n\n"
                    for holiday in data[:10]:
                        date = holiday.get("date", "")
                        name = holiday.get(
                            "localName", holiday.get("name", ""))
                        result += f"• {date}: {name}\n"
                    return result.strip()
        except Exception as e:
            print(f"[WebTools] Holidays error: {e}")
        return None

    # ==================== UTILITY ====================

    def get_qr_code(self, text: str, size: int = 150) -> Optional[str]:
        """Generate a QR code URL."""
        encoded = quote_plus(text)
        return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}"

    def get_placeholder_image(self, width: int = 400, height: int = 300, text: str = "Friday") -> str:
        """Get a placeholder image URL."""
        return f"https://via.placeholder.com/{width}x{height}/0D1421/00D4FF?text={quote_plus(text)}"

    def shorten_url(self, url: str) -> Optional[str]:
        """Shorten a URL using TinyURL."""
        self._rate_limit_check("shorten", 1.0)

        try:
            resp = self.session.get(
                "https://tinyurl.com/api-create.php",
                params={"url": url},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            print(f"[WebTools] URL shorten error: {e}")
        return None

    def validate_email(self, email: str) -> Optional[str]:
        """Basic email validation using abstract API."""
        self._rate_limit_check("email", 1.0)

        try:
            resp = self.session.get(
                f"https://disposable.debounce.io/?email={quote_plus(email)}",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("disposable") == "true":
                    return f"📧 {email} appears to be a disposable/temporary email."
                else:
                    return f"📧 {email} format looks valid."
        except:
            pass

        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(pattern, email):
            return f"📧 {email} format is valid."
        return f"❌ {email} format is invalid."

    def get_ip_info(self, ip: str = "") -> Optional[str]:
        """Get IP address information."""
        self._rate_limit_check("ip", 1.0)

        try:
            url = f"https://ipapi.co/{ip}/json/" if ip else "https://ipapi.co/json/"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ip"):
                    return (
                        f"🌐 IP: {data.get('ip', 'Unknown')}\n"
                        f"   📍 Location: {data.get('city', '')}, {data.get('region', '')}, {data.get('country_name', '')}\n"
                        f"   🏢 ISP: {data.get('org', 'Unknown')}\n"
                        f"   ⏰ Timezone: {data.get('timezone', 'Unknown')}"
                    )
        except Exception as e:
            print(f"[WebTools] IP error: {e}")
        return None

    # ==================== COMPREHENSIVE RESEARCH ====================

    def research(self, topic: str) -> str:
        """Comprehensive research using multiple free sources."""
        results = []

        ddg = self.search_duckduckgo(topic)
        if ddg:
            results.append(f"[DuckDuckGo]\n{ddg}")

        wiki = self.search_wikipedia(topic)
        if wiki:
            results.append(f"[Wikipedia]\n{wiki}")

        if not results:
            return f"I couldn't find information about '{topic}' using free sources. Try rephrasing."

        return "\n\n---\n\n".join(results)


# Global singleton
_web_tools: Optional[FreeWebTools] = None


def get_web_tools() -> FreeWebTools:
    """Get the global FreeWebTools instance."""
    global _web_tools
    if _web_tools is None:
        _web_tools = FreeWebTools()
    return _web_tools
