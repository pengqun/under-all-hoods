"""
Tests for Mini Search Engine
==============================

Organized by component so failures point directly to the broken layer.
Run with: python -m pytest test_search_engine.py -v
     or:  python test_search_engine.py
"""

import os
import sys
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the module (filename has a hyphen) ────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "search-engine-alexmolas.py")
_loader = SourceFileLoader("search_engine", _path)
_spec = spec_from_loader("search_engine", _loader)
se_module = module_from_spec(_spec)
sys.modules["search_engine"] = se_module
_loader.exec_module(se_module)

normalize_string = se_module.normalize_string
update_url_scores = se_module.update_url_scores
SearchEngine = se_module.SearchEngine
TextExtractor = se_module.TextExtractor
crawl = se_module.crawl


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalization:

    def test_lowercase(self):
        assert normalize_string("Hello World") == "hello world"

    def test_punctuation_removed(self):
        assert normalize_string("hello, world!") == "hello world"

    def test_double_spaces_collapsed(self):
        assert normalize_string("hello   world") == "hello world"

    def test_empty_string(self):
        assert normalize_string("") == ""

    def test_mixed(self):
        assert normalize_string("  Hello, World!!  How's IT?  ") == "hello world how s it"

    def test_only_punctuation(self):
        result = normalize_string("...")
        assert result.strip() == ""


class TestUpdateUrlScores:

    def test_merge_disjoint(self):
        old = {"a": 1.0}
        new = {"b": 2.0}
        result = update_url_scores(old, new)
        assert result == {"a": 1.0, "b": 2.0}

    def test_merge_overlapping(self):
        old = {"a": 1.0, "b": 2.0}
        new = {"b": 3.0, "c": 4.0}
        result = update_url_scores(old, new)
        assert result == {"a": 1.0, "b": 5.0, "c": 4.0}

    def test_merge_empty(self):
        assert update_url_scores({}, {}) == {}

    def test_mutates_old(self):
        old = {"a": 1.0}
        result = update_url_scores(old, {"b": 2.0})
        assert result is old


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def engine():
    """Pre-indexed engine with sample documents."""
    se = SearchEngine()
    se.bulk_index([
        ("doc1", "the quick brown fox jumps over the lazy dog"),
        ("doc2", "the quick brown fox"),
        ("doc3", "the lazy dog sleeps all day"),
        ("doc4", "python is a programming language for machine learning"),
        ("doc5", "java is a programming language for enterprise"),
    ])
    return se


class TestSearchEngine:

    def test_number_of_documents(self, engine):
        assert engine.number_of_documents == 5

    def test_avdl(self, engine):
        assert engine.avdl > 0

    def test_avdl_empty(self):
        se = SearchEngine()
        assert se.avdl == 0

    def test_index_stores_content(self, engine):
        assert "quick brown fox" in engine._documents["doc1"]

    def test_get_urls(self, engine):
        urls = engine.get_urls("fox")
        assert "doc1" in urls
        assert "doc2" in urls
        assert "doc3" not in urls

    def test_get_urls_missing_keyword(self, engine):
        urls = engine.get_urls("nonexistent")
        assert len(urls) == 0

    def test_idf_common_term(self, engine):
        idf_the = engine.idf("the")
        idf_python = engine.idf("python")
        # "the" appears in 3 docs, "python" in 1 — python should have higher IDF
        assert idf_python > idf_the

    def test_idf_rare_term(self, engine):
        idf = engine.idf("sleeps")
        assert idf > 0

    def test_bm25_returns_scores(self, engine):
        scores = engine.bm25("fox")
        assert isinstance(scores, dict)
        assert all(isinstance(v, float) for v in scores.values())

    def test_bm25_higher_for_shorter_doc(self, engine):
        # "fox" appears once in both doc1 (long) and doc2 (short).
        # BM25 should score the shorter doc higher (term density).
        scores = engine.bm25("fox")
        assert scores["doc2"] > scores["doc1"]

    def test_search_single_keyword(self, engine):
        results = engine.search("fox")
        assert len(results) == 2
        urls = [url for url, _ in results]
        assert "doc1" in urls
        assert "doc2" in urls

    def test_search_multi_keyword(self, engine):
        results = engine.search("lazy dog")
        urls = [url for url, _ in results]
        assert "doc3" in urls or "doc1" in urls

    def test_search_no_results(self, engine):
        results = engine.search("xyznotfound")
        assert results == []

    def test_search_ranking_order(self, engine):
        results = engine.search("programming language")
        # Results should be sorted descending by score
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_empty_query(self, engine):
        assert engine.search("") == []

    def test_bulk_index(self):
        se = SearchEngine()
        se.bulk_index([("a", "hello world"), ("b", "goodbye world")])
        assert se.number_of_documents == 2
        results = se.search("hello")
        assert len(results) == 1
        assert results[0][0] == "a"


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT EXTRACTOR (HTML → plain text)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTextExtractor:

    def test_simple_html(self):
        te = TextExtractor()
        te.feed("<p>Hello world</p>")
        assert te.get_text() == "Hello world"

    def test_strips_script(self):
        te = TextExtractor()
        te.feed("<p>Hello</p><script>var x=1;</script><p>world</p>")
        assert "var" not in te.get_text()
        assert "Hello" in te.get_text()
        assert "world" in te.get_text()

    def test_strips_style(self):
        te = TextExtractor()
        te.feed("<style>body{color:red}</style><p>content</p>")
        assert "color" not in te.get_text()
        assert "content" in te.get_text()

    def test_nested_tags(self):
        te = TextExtractor()
        te.feed("<div><p>nested <b>bold</b> text</p></div>")
        assert "nested bold text" in te.get_text()

    def test_empty_html(self):
        te = TextExtractor()
        te.feed("")
        assert te.get_text() == ""


# ═══════════════════════════════════════════════════════════════════════════════
# CRAWLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrawler:

    @patch("search_engine.urlopen")
    def test_crawl_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body><p>Hello world</p></body></html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        text = crawl("https://example.com")
        assert text is not None
        assert "Hello world" in text

    @patch("search_engine.urlopen")
    def test_crawl_failure(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("test error")
        text = crawl("https://example.com/bad")
        assert text is None


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:

    def test_index_and_search_workflow(self):
        se = SearchEngine()
        se.index("doc/python", "Python is great for data science and machine learning")
        se.index("doc/java", "Java is great for enterprise applications")
        se.index("doc/rust", "Rust is great for systems programming")

        results = se.search("Python data science")
        assert len(results) >= 1
        assert results[0][0] == "doc/python"

    def test_relevance_ranking(self):
        se = SearchEngine()
        # doc_a mentions "python" many times
        se.index("doc_a", "Python Python Python is the best Python language Python")
        # doc_b mentions "python" once
        se.index("doc_b", "Java is a language, unlike Python")

        results = se.search("python")
        assert results[0][0] == "doc_a"
        assert results[0][1] > results[1][1]


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
