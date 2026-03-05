"""
A Minimal Search Engine — in Python
======================================

How does a search engine find relevant results from a sea of documents?
This module implements a minimal search engine from scratch, covering
crawling, indexing, and ranking — all in a single file.

Architecture
------------

::

    Documents (URL + text)              Query string
            │                                │
            ▼                                ▼
    ┌──────────────┐               ┌──────────────┐
    │   CRAWLER     │               │  NORMALIZER   │  Lowercase, strip punctuation
    │ (urllib+html) │               └──────┬───────┘
    └──────┬───────┘                      │
           │  plain text                  ▼
           ▼                       ┌──────────────┐
    ┌──────────────┐               │  BM25 RANKER  │  Score each document
    │  INVERTED     │◄─────────────│               │  for the query
    │  INDEX        │  lookup      └──────┬───────┘
    │               │                     │
    │ word → {url:  │                     ▼
    │   frequency}  │              Ranked results
    └──────────────┘              [(url, score), …]

Ranking algorithm
-----------------

Uses `Okapi BM25 <https://en.wikipedia.org/wiki/Okapi_BM25>`_, the
classic probabilistic ranking function used by Elasticsearch and others::

    score(q, D) = Σ  IDF(qᵢ) · f(qᵢ,D)·(k₁+1)
                  i            ─────────────────────────────
                               f(qᵢ,D) + k₁·(1 − b + b·|D|/avgdl)

Reference
---------
- `A search engine in 80 lines of Python
  <https://www.alexmolas.com/2024/02/05/a-search-engine-in-80-lines.html>`_
  by Alex Molas
"""

from collections import defaultdict
from html.parser import HTMLParser
from math import log
from urllib.error import URLError
from urllib.request import Request, urlopen
import string


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

_PUNCT_TABLE = str.maketrans(string.punctuation, " " * len(string.punctuation))


def normalize_string(text):
    """Lowercase, strip punctuation, collapse whitespace."""
    without_punct = text.translate(_PUNCT_TABLE)
    return " ".join(without_punct.split()).lower()


def update_url_scores(old, new):
    """Merge *new* URL→score mapping into *old* by summing scores."""
    for url, score in new.items():
        old[url] = old.get(url, 0) + score
    return old


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH ENGINE — inverted index + BM25 ranking
# ═══════════════════════════════════════════════════════════════════════════════

class SearchEngine:
    """A minimal search engine backed by an inverted index and BM25 ranking.

    >>> se = SearchEngine()
    >>> se.index("a.html", "the quick brown fox")
    >>> se.index("b.html", "the slow brown dog")
    >>> results = se.search("quick fox")
    >>> results[0][0]
    'a.html'
    """

    def __init__(self, k1=1.5, b=0.75):
        # Inverted index: word → {url: term_frequency}
        self._index = defaultdict(lambda: defaultdict(int))
        # Original documents: url → raw content string
        self._documents = {}
        # BM25 tuning parameters
        self.k1 = k1  # term-frequency saturation
        self.b = b     # document-length normalization

    @property
    def number_of_documents(self):
        return len(self._documents)

    @property
    def avdl(self):
        """Average document length (in characters)."""
        if not self._documents:
            return 0
        return sum(len(d) for d in self._documents.values()) / len(self._documents)

    # ── Indexing ─────────────────────────────────────────────────────────────

    def index(self, url, content):
        """Add a document to the index."""
        self._documents[url] = content
        for word in normalize_string(content).split():
            self._index[word][url] += 1

    def bulk_index(self, documents):
        """Index multiple ``(url, content)`` pairs."""
        for url, content in documents:
            self.index(url, content)

    # ── Lookup ───────────────────────────────────────────────────────────────

    def get_urls(self, keyword):
        """Return ``{url: frequency}`` for *keyword*."""
        return self._index[normalize_string(keyword)]

    # ── Ranking ──────────────────────────────────────────────────────────────

    def idf(self, keyword):
        """Inverse document frequency for *keyword*.

        ``log((N - n + 0.5) / (n + 0.5) + 1)`` where *N* is the total
        number of documents and *n* is the number containing *keyword*.
        """
        N = self.number_of_documents
        n = len(self.get_urls(keyword))
        return log((N - n + 0.5) / (n + 0.5) + 1)

    def bm25(self, keyword):
        """BM25 score for a single *keyword* across all indexed documents.

        Returns ``{url: score}``.
        """
        result = {}
        idf_score = self.idf(keyword)
        avdl = self.avdl
        for url, freq in self.get_urls(keyword).items():
            doc_len = len(self._documents[url])
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / avdl)
            result[url] = idf_score * numerator / denominator
        return result

    def search(self, query):
        """Search for *query* and return ``[(url, score), …]`` ranked by relevance.

        Multi-word queries accumulate BM25 scores across all keywords so
        documents matching more terms rank higher.
        """
        keywords = normalize_string(query).split()
        if not keywords:
            return []
        url_scores = {}
        for kw in keywords:
            update_url_scores(url_scores, self.bm25(kw))
        return sorted(url_scores.items(), key=lambda item: item[1], reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CRAWLER — stdlib only (urllib + HTMLParser)
# ═══════════════════════════════════════════════════════════════════════════════

class TextExtractor(HTMLParser):
    """Strip HTML tags and return plain text.

    Skips ``<script>`` and ``<style>`` blocks.

    >>> te = TextExtractor()
    >>> te.feed("<p>Hello <b>world</b></p>")
    >>> te.get_text()
    'Hello world'
    """

    _SKIP_TAGS = frozenset(("script", "style"))

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self):
        return " ".join("".join(self._pieces).split())


def crawl(url):
    """Fetch *url* and return its plain-text content, or ``None`` on error."""
    try:
        req = Request(url, headers={"User-Agent": "MiniSearchBot/1.0"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        extractor = TextExtractor()
        extractor.feed(html)
        return extractor.get_text()
    except (URLError, OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"  [crawl] {url}: {exc}")
        return None


def crawl_multiple(urls):
    """Crawl a list of URLs and return ``[(url, text), …]`` for successes."""
    results = []
    for i, url in enumerate(urls, 1):
        print(f"  Crawling [{i}/{len(urls)}]: {url}")
        text = crawl(url)
        if text:
            results.append((url, text))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — demo
# ═══════════════════════════════════════════════════════════════════════════════

def _demo():
    print("Mini Search Engine — Python Edition")
    print("=" * 40)

    # ── Offline demo with sample documents ───────────────────────────────────
    documents = [
        ("https://example.com/python",
         "Python is a high-level programming language known for its readability. "
         "Python supports multiple programming paradigms including procedural, "
         "object-oriented, and functional programming."),
        ("https://example.com/java",
         "Java is a class-based, object-oriented programming language designed "
         "to have as few implementation dependencies as possible. Java is widely "
         "used for enterprise applications."),
        ("https://example.com/rust",
         "Rust is a systems programming language focused on safety, speed, and "
         "concurrency. Rust achieves memory safety without a garbage collector."),
        ("https://example.com/web",
         "Web development involves building websites and web applications. "
         "HTML, CSS, and JavaScript are the core technologies for the web."),
        ("https://example.com/databases",
         "Databases store and organize data. SQL databases like PostgreSQL and "
         "MySQL are relational, while NoSQL databases like MongoDB store documents."),
        ("https://example.com/ml",
         "Machine learning is a subset of artificial intelligence. Python is "
         "the most popular language for machine learning and data science."),
    ]

    engine = SearchEngine()
    engine.bulk_index(documents)
    print(f"\n  Indexed {engine.number_of_documents} documents")
    print(f"  Average document length: {engine.avdl:.0f} chars")

    queries = [
        "programming language",
        "Python machine learning",
        "web development",
        "memory safety",
        "databases SQL",
    ]

    for query in queries:
        results = engine.search(query)
        print(f"\n  Query: {query!r}")
        if not results:
            print("    (no results)")
        for url, score in results[:3]:
            print(f"    {score:6.3f}  {url}")

    # Peek inside the inverted index
    print(f"\n{'=' * 40}")
    print("Inverted index for 'python':")
    for url, freq in engine.get_urls("python").items():
        print(f"    freq={freq}  {url}")


if __name__ == "__main__":
    _demo()
