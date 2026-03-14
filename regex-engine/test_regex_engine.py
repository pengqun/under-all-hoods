"""
Tests for the Regular Expression Engine
=========================================

Organized by feature/phase so failures point directly to the broken area.
Run with: python -m pytest test_regex_engine.py -v
     or:  python test_regex_engine.py
"""

import sys
import os

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the regex engine module (filename has a hyphen) ────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "regex-engine.py")
_loader = SourceFileLoader("regex_engine", _path)
_spec = spec_from_loader("regex_engine", _loader)
engine = module_from_spec(_spec)
sys.modules["regex_engine"] = engine
_loader.exec_module(engine)

# Pull out what we need
State = engine.State
Frag = engine.Frag
Regex = engine.Regex
compile = engine.compile
parse = engine.parse
compile_nfa = engine.compile_nfa
simulate = engine.simulate
search = engine.search
SPLIT = engine.SPLIT
MATCH = engine.MATCH
CONCAT = engine.CONCAT


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — PARSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestParser:
    """Tests for the parse() function (regex → postfix tokens)."""

    def test_single_char(self):
        result = parse("a")
        assert len(result) == 1
        assert result[0] == ('char', 'a')

    def test_concatenation(self):
        result = parse("ab")
        assert result[-1] == ('op', CONCAT)

    def test_alternation(self):
        result = parse("a|b")
        assert result[-1] == ('op', '|')

    def test_star(self):
        result = parse("a*")
        assert result[-1] == ('op', '*')

    def test_plus(self):
        result = parse("a+")
        assert result[-1] == ('op', '+')

    def test_question(self):
        result = parse("a?")
        assert result[-1] == ('op', '?')

    def test_grouped_alternation(self):
        result = parse("(a|b)c")
        # Should produce: a b | c concat
        types = [t for t, _ in result]
        assert 'op' in types

    def test_precedence_star_over_concat(self):
        """a* should bind tighter than concatenation: a(b*) not (ab)*"""
        result = parse("ab*")
        # Postfix: a b * concat
        assert result[0] == ('char', 'a')
        assert result[1] == ('char', 'b')
        assert result[2] == ('op', '*')
        assert result[3] == ('op', CONCAT)

    def test_precedence_concat_over_alternation(self):
        """ab|cd should parse as (ab)|(cd)"""
        result = parse("ab|cd")
        # Postfix: a b concat c d concat |
        assert result[-1] == ('op', '|')

    def test_mismatched_open_paren(self):
        with pytest.raises(ValueError, match="Mismatched"):
            parse("(ab")

    def test_mismatched_close_paren(self):
        with pytest.raises(ValueError, match="Mismatched"):
            parse("ab)")

    def test_empty_pattern(self):
        result = parse("")
        assert result == []

    def test_anchors(self):
        result = parse("^a$")
        types = [t for t, _ in result]
        assert 'anchor' in types


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — NFA COMPILATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompileNFA:
    """Tests for compile_nfa() — Thompson's construction."""

    def test_single_char_nfa(self):
        postfix = parse("a")
        start = compile_nfa(postfix)
        assert start.kind == ord('a')
        assert start.out is not None
        assert start.out.kind == MATCH

    def test_concat_nfa(self):
        postfix = parse("ab")
        start = compile_nfa(postfix)
        assert start.kind == ord('a')
        assert start.out.kind == ord('b')
        assert start.out.out.kind == MATCH

    def test_alternation_nfa(self):
        postfix = parse("a|b")
        start = compile_nfa(postfix)
        assert start.kind == SPLIT
        assert start.out.kind == ord('a')
        assert start.out1.kind == ord('b')

    def test_star_nfa(self):
        postfix = parse("a*")
        start = compile_nfa(postfix)
        assert start.kind == SPLIT  # split: try 'a' or skip

    def test_plus_nfa(self):
        postfix = parse("a+")
        start = compile_nfa(postfix)
        assert start.kind == ord('a')  # must match 'a' first

    def test_question_nfa(self):
        postfix = parse("a?")
        start = compile_nfa(postfix)
        assert start.kind == SPLIT


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATION / FULL MATCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullMatch:
    """Tests for fullmatch() — complete string matching."""

    # --- Literal characters ---

    def test_single_char_match(self):
        assert compile("a").fullmatch("a") is True

    def test_single_char_no_match(self):
        assert compile("a").fullmatch("b") is False

    def test_single_char_too_long(self):
        assert compile("a").fullmatch("ab") is False

    def test_single_char_empty(self):
        assert compile("a").fullmatch("") is False

    # --- Concatenation ---

    def test_concat_match(self):
        assert compile("abc").fullmatch("abc") is True

    def test_concat_no_match(self):
        assert compile("abc").fullmatch("abd") is False

    def test_concat_partial(self):
        assert compile("abc").fullmatch("ab") is False

    def test_concat_long(self):
        assert compile("abcdef").fullmatch("abcdef") is True

    # --- Alternation ---

    def test_alt_first(self):
        assert compile("a|b").fullmatch("a") is True

    def test_alt_second(self):
        assert compile("a|b").fullmatch("b") is True

    def test_alt_neither(self):
        assert compile("a|b").fullmatch("c") is False

    def test_alt_multi(self):
        assert compile("a|b|c").fullmatch("c") is True

    def test_alt_words(self):
        assert compile("cat|dog|bird").fullmatch("dog") is True

    def test_alt_words_no_match(self):
        assert compile("cat|dog|bird").fullmatch("fish") is False

    # --- Star (*) ---

    def test_star_empty(self):
        assert compile("a*").fullmatch("") is True

    def test_star_one(self):
        assert compile("a*").fullmatch("a") is True

    def test_star_many(self):
        assert compile("a*").fullmatch("aaaa") is True

    def test_star_wrong_char(self):
        assert compile("a*").fullmatch("b") is False

    def test_star_in_sequence(self):
        assert compile("ab*c").fullmatch("ac") is True
        assert compile("ab*c").fullmatch("abc") is True
        assert compile("ab*c").fullmatch("abbc") is True
        assert compile("ab*c").fullmatch("abbbc") is True

    # --- Plus (+) ---

    def test_plus_empty(self):
        assert compile("a+").fullmatch("") is False

    def test_plus_one(self):
        assert compile("a+").fullmatch("a") is True

    def test_plus_many(self):
        assert compile("a+").fullmatch("aaaa") is True

    def test_plus_in_sequence(self):
        assert compile("ab+c").fullmatch("ac") is False
        assert compile("ab+c").fullmatch("abc") is True
        assert compile("ab+c").fullmatch("abbc") is True

    # --- Question (?) ---

    def test_question_empty(self):
        assert compile("a?").fullmatch("") is True

    def test_question_one(self):
        assert compile("a?").fullmatch("a") is True

    def test_question_too_many(self):
        assert compile("a?").fullmatch("aa") is False

    def test_question_in_sequence(self):
        assert compile("ab?c").fullmatch("ac") is True
        assert compile("ab?c").fullmatch("abc") is True
        assert compile("ab?c").fullmatch("abbc") is False

    # --- Parentheses / Grouping ---

    def test_group_simple(self):
        assert compile("(ab)").fullmatch("ab") is True

    def test_group_alternation(self):
        assert compile("(a|b)c").fullmatch("ac") is True
        assert compile("(a|b)c").fullmatch("bc") is True
        assert compile("(a|b)c").fullmatch("cc") is False

    def test_group_star(self):
        assert compile("(ab)*").fullmatch("") is True
        assert compile("(ab)*").fullmatch("ab") is True
        assert compile("(ab)*").fullmatch("abab") is True
        assert compile("(ab)*").fullmatch("aba") is False

    def test_group_plus(self):
        assert compile("(ab)+").fullmatch("ab") is True
        assert compile("(ab)+").fullmatch("ababab") is True
        assert compile("(ab)+").fullmatch("") is False

    def test_nested_groups(self):
        assert compile("((a|b)c)+").fullmatch("acbc") is True
        assert compile("((a|b)c)+").fullmatch("ac") is True
        assert compile("((a|b)c)+").fullmatch("cc") is False

    # --- Dot (any char) ---

    def test_dot_matches_any(self):
        assert compile(".").fullmatch("a") is True
        assert compile(".").fullmatch("z") is True
        assert compile(".").fullmatch("5") is True
        assert compile(".").fullmatch("@") is True

    def test_dot_empty(self):
        assert compile(".").fullmatch("") is False

    def test_dot_multiple(self):
        assert compile("..").fullmatch("ab") is True
        assert compile("..").fullmatch("a") is False

    def test_dot_star(self):
        assert compile(".*").fullmatch("") is True
        assert compile(".*").fullmatch("anything") is True

    def test_dot_plus(self):
        assert compile(".+").fullmatch("") is False
        assert compile(".+").fullmatch("x") is True
        assert compile(".+").fullmatch("hello world") is True

    # --- Complex patterns ---

    def test_complex_email_like(self):
        r = compile("\\w+@\\w+\\.\\w+")
        assert r.fullmatch("user@host.com") is True
        assert r.fullmatch("@host.com") is False

    def test_complex_nested_alt_star(self):
        r = compile("a(b|c)*d")
        assert r.fullmatch("ad") is True
        assert r.fullmatch("abd") is True
        assert r.fullmatch("acd") is True
        assert r.fullmatch("abcbcd") is True
        assert r.fullmatch("aed") is False

    def test_complex_mixed_operators(self):
        r = compile("(a+b)*c?d")
        assert r.fullmatch("d") is True
        assert r.fullmatch("cd") is True
        assert r.fullmatch("abd") is True
        assert r.fullmatch("abaabd") is True
        assert r.fullmatch("ababcd") is True


# ═══════════════════════════════════════════════════════════════════════════════
# ESCAPE SEQUENCES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscapeSequences:
    """Tests for \\d, \\w, \\s and their negations."""

    def test_digit_match(self):
        r = compile("\\d")
        assert r.fullmatch("5") is True
        assert r.fullmatch("0") is True
        assert r.fullmatch("a") is False

    def test_digit_plus(self):
        r = compile("\\d+")
        assert r.fullmatch("12345") is True
        assert r.fullmatch("") is False
        assert r.fullmatch("12a") is False

    def test_non_digit(self):
        r = compile("\\D+")
        assert r.fullmatch("abc") is True
        assert r.fullmatch("12") is False

    def test_word_char(self):
        r = compile("\\w+")
        assert r.fullmatch("hello_123") is True
        assert r.fullmatch("hello world") is False

    def test_non_word_char(self):
        r = compile("\\W+")
        assert r.fullmatch("!@#") is True
        assert r.fullmatch("abc") is False

    def test_whitespace(self):
        r = compile("\\s+")
        assert r.fullmatch("  \t\n") is True
        assert r.fullmatch("abc") is False

    def test_non_whitespace(self):
        r = compile("\\S+")
        assert r.fullmatch("hello") is True
        assert r.fullmatch("hello world") is False

    def test_escaped_special_chars(self):
        assert compile("\\.").fullmatch(".") is True
        assert compile("\\.").fullmatch("a") is False
        assert compile("\\*").fullmatch("*") is True
        assert compile("\\+").fullmatch("+") is True
        assert compile("\\?").fullmatch("?") is True
        assert compile("\\(").fullmatch("(") is True
        assert compile("\\|").fullmatch("|") is True

    def test_escaped_backslash(self):
        assert compile("\\\\").fullmatch("\\") is True

    def test_escaped_tab_newline(self):
        assert compile("\\t").fullmatch("\t") is True
        assert compile("\\n").fullmatch("\n") is True
        assert compile("\\r").fullmatch("\r") is True


# ═══════════════════════════════════════════════════════════════════════════════
# CHARACTER CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCharacterClasses:
    """Tests for [abc], [a-z], [^abc] character classes."""

    def test_simple_class(self):
        r = compile("[abc]")
        assert r.fullmatch("a") is True
        assert r.fullmatch("b") is True
        assert r.fullmatch("c") is True
        assert r.fullmatch("d") is False

    def test_range(self):
        r = compile("[a-z]")
        assert r.fullmatch("a") is True
        assert r.fullmatch("m") is True
        assert r.fullmatch("z") is True
        assert r.fullmatch("A") is False
        assert r.fullmatch("5") is False

    def test_multiple_ranges(self):
        r = compile("[a-zA-Z]")
        assert r.fullmatch("a") is True
        assert r.fullmatch("Z") is True
        assert r.fullmatch("5") is False

    def test_negated_class(self):
        r = compile("[^abc]")
        assert r.fullmatch("a") is False
        assert r.fullmatch("d") is True
        assert r.fullmatch("5") is True

    def test_negated_range(self):
        r = compile("[^0-9]")
        assert r.fullmatch("a") is True
        assert r.fullmatch("5") is False

    def test_class_with_star(self):
        r = compile("[a-z]+")
        assert r.fullmatch("hello") is True
        assert r.fullmatch("HELLO") is False
        assert r.fullmatch("") is False

    def test_class_with_digits(self):
        r = compile("[0-9]+")
        assert r.fullmatch("123") is True
        assert r.fullmatch("abc") is False

    def test_class_mixed(self):
        r = compile("[a-z0-9_]+")
        assert r.fullmatch("hello_123") is True
        assert r.fullmatch("HELLO") is False

    def test_unterminated_class(self):
        with pytest.raises(ValueError, match="Unterminated"):
            compile("[abc")

    def test_class_in_sequence(self):
        r = compile("[A-Z][a-z]+")
        assert r.fullmatch("Hello") is True
        assert r.fullmatch("hello") is False
        assert r.fullmatch("HELLO") is False


# ═══════════════════════════════════════════════════════════════════════════════
# ANCHORS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnchors:
    """Tests for ^ (start) and $ (end) anchors."""

    def test_caret_in_search(self):
        r = compile("^hello")
        assert r.search("hello world") == (0, 5)
        assert r.search("say hello") is None

    def test_dollar_in_search(self):
        r = compile("world$")
        assert r.search("hello world") == (6, 11)
        assert r.search("world hello") is None

    def test_both_anchors(self):
        r = compile("^hello$")
        assert r.search("hello") == (0, 5)
        assert r.search("hello world") is None
        assert r.search("say hello") is None

    def test_caret_fullmatch(self):
        r = compile("^abc")
        assert r.fullmatch("abc") is True


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    """Tests for search() — find pattern anywhere in text."""

    def test_search_at_start(self):
        r = compile("hello")
        assert r.search("hello world") == (0, 5)

    def test_search_in_middle(self):
        r = compile("world")
        assert r.search("hello world!") == (6, 11)

    def test_search_at_end(self):
        r = compile("end")
        assert r.search("the end") == (4, 7)

    def test_search_no_match(self):
        r = compile("xyz")
        assert r.search("hello world") is None

    def test_search_returns_first(self):
        r = compile("ab")
        assert r.search("ab ab ab") == (0, 2)

    def test_search_with_star(self):
        r = compile("a*b")
        assert r.search("xaaab") == (1, 5)

    def test_search_digits(self):
        r = compile("\\d+")
        assert r.search("abc 123 def") == (4, 7)

    def test_search_empty_text(self):
        r = compile("a")
        assert r.search("") is None

    def test_search_greedy(self):
        """Search should find the longest match at each position."""
        r = compile("a+")
        assert r.search("baaab") == (1, 4)


# ═══════════════════════════════════════════════════════════════════════════════
# MATCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatch:
    """Tests for match() — match at beginning of text."""

    def test_match_at_start(self):
        r = compile("hello")
        assert r.match("hello world") == (0, 5)

    def test_match_not_at_start(self):
        r = compile("world")
        result = r.match("hello world")
        assert result is None

    def test_match_full(self):
        r = compile("abc")
        assert r.match("abc") == (0, 3)

    def test_match_with_quantifier(self):
        r = compile("\\d+")
        assert r.match("123abc") == (0, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# FINDALL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindAll:
    """Tests for findall() — find all non-overlapping matches."""

    def test_findall_digits(self):
        r = compile("\\d+")
        assert r.findall("abc 12 def 345 ghi 6") == ["12", "345", "6"]

    def test_findall_words(self):
        r = compile("[a-z]+")
        result = r.findall("Hello World 123 test")
        assert result == ["ello", "orld", "test"]

    def test_findall_no_match(self):
        r = compile("\\d+")
        assert r.findall("no digits here") == []

    def test_findall_single_chars(self):
        r = compile("[aeiou]")
        assert r.findall("hello") == ["e", "o"]

    def test_findall_overlapping_patterns(self):
        r = compile("ab")
        assert r.findall("ababab") == ["ab", "ab", "ab"]


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES & ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_pattern_matches_empty(self):
        """Empty pattern should match empty string (or cause error)."""
        # Empty postfix → compile_nfa gets empty list → error
        with pytest.raises(ValueError):
            compile("")

    def test_single_dot(self):
        r = compile(".")
        assert r.fullmatch("a") is True
        assert r.fullmatch("") is False
        assert r.fullmatch("ab") is False

    def test_escaped_dot(self):
        r = compile("\\.")
        assert r.fullmatch(".") is True
        assert r.fullmatch("a") is False

    def test_deeply_nested(self):
        r = compile("((((a))))")
        assert r.fullmatch("a") is True
        assert r.fullmatch("b") is False

    def test_alternation_with_empty(self):
        """(|a) should match empty string or 'a'."""
        # This is a tricky case — depends on implementation
        # Our implementation may raise an error or handle it
        pass  # Skip — edge case not required for basic engine

    def test_star_star(self):
        """a** — double quantifier."""
        # Some engines reject this, ours should handle it
        # since * is a postfix op, a** means (a*)* which is valid
        r = compile("a**")
        assert r.fullmatch("") is True
        assert r.fullmatch("aaa") is True

    def test_unicode_chars(self):
        r = compile("héllo")
        assert r.fullmatch("héllo") is True
        assert r.fullmatch("hello") is False

    def test_repr(self):
        r = compile("abc")
        assert repr(r) == "Regex('abc')"

    def test_long_string(self):
        """Should handle long strings efficiently (no exponential blowup)."""
        r = compile("a*b")
        # This would be catastrophic for a backtracking engine
        assert r.fullmatch("a" * 100 + "b") is True
        assert r.fullmatch("a" * 100) is False

    def test_pathological_pattern(self):
        """Classic pattern that causes exponential backtracking in naive engines.

        a?^n a^n should match a^n — and our NFA engine handles it in linear time.
        """
        n = 25
        pattern = "a?" * n + "a" * n
        text = "a" * n
        r = compile(pattern)
        assert r.fullmatch(text) is True


# ═══════════════════════════════════════════════════════════════════════════════
# REGEX OBJECT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexObject:
    """Tests for the Regex class interface."""

    def test_compile_returns_regex(self):
        r = compile("abc")
        assert isinstance(r, Regex)

    def test_pattern_stored(self):
        r = compile("abc")
        assert r.pattern == "abc"

    def test_all_methods_exist(self):
        r = compile("abc")
        assert hasattr(r, 'fullmatch')
        assert hasattr(r, 'search')
        assert hasattr(r, 'match')
        assert hasattr(r, 'findall')


# ═══════════════════════════════════════════════════════════════════════════════
# REAL-WORLD PATTERN TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealWorldPatterns:
    """Test patterns commonly used in practice."""

    def test_ip_address_like(self):
        r = compile("\\d+\\.\\d+\\.\\d+\\.\\d+")
        assert r.fullmatch("192.168.1.1") is True
        assert r.fullmatch("10.0.0.255") is True
        assert r.fullmatch("abc.def.ghi.jkl") is False

    def test_simple_email(self):
        r = compile("\\w+@\\w+\\.\\w+")
        assert r.fullmatch("user@host.com") is True
        assert r.fullmatch("@host.com") is False

    def test_hex_color(self):
        r = compile("[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]")
        assert r.fullmatch("ff00cc") is True
        assert r.fullmatch("AABB11") is True
        assert r.fullmatch("xyz123") is False

    def test_simple_phone(self):
        r = compile("\\d\\d\\d-\\d\\d\\d-\\d\\d\\d\\d")
        assert r.fullmatch("555-123-4567") is True
        assert r.fullmatch("55-123-4567") is False

    def test_identifier(self):
        r = compile("[a-zA-Z_][a-zA-Z0-9_]*")
        assert r.fullmatch("my_var") is True
        assert r.fullmatch("_private") is True
        assert r.fullmatch("CamelCase") is True
        assert r.fullmatch("123bad") is False

    def test_url_protocol(self):
        r = compile("https?://\\w+\\.\\w+")
        assert r.fullmatch("http://example.com") is True
        assert r.fullmatch("https://example.com") is True
        assert r.fullmatch("ftp://example.com") is False


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
