"""
A Regular Expression Engine — in Python
=========================================

Matches text against regular expressions using Thompson's NFA construction
and multi-state simulation — the same algorithm behind fast regex engines
like RE2 and Plan 9 grep.

    Pattern          Meaning
    ───────          ───────
    a                Literal character 'a'
    .                Any single character
    ab               Concatenation: 'a' then 'b'
    a|b              Alternation: 'a' or 'b'
    a*               Zero or more 'a'
    a+               One or more 'a'
    a?               Zero or one 'a'
    (ab|cd)          Grouping with parentheses
    \\d              Digit [0-9]
    \\w              Word char [a-zA-Z0-9_]
    \\s              Whitespace [ \\t\\n\\r\\f\\v]
    [abc]            Character class: a, b, or c
    [a-z]            Character range
    [^abc]           Negated character class
    ^                Anchor: start of string
    $                Anchor: end of string

The engine works in three phases:

    Regex String
        │
        ▼
    ┌──────────┐    "a(b|c)*"  →  "ab.c|*.""
    │  PARSE   │    Insert explicit concat operators,
    │          │    then convert infix → postfix (shunting-yard).
    └──────────┘
        │
        ▼
    ┌──────────┐    Postfix  →  NFA (graph of State nodes)
    │ COMPILE  │    Thompson's construction: one state per
    │          │    character/operator, building NFA fragments.
    └──────────┘
        │
        ▼
    ┌──────────┐    NFA + input string  →  match / no match
    │ SIMULATE │    Track all active states simultaneously.
    │          │    Linear time: O(pattern × text).
    └──────────┘

Based on: https://swtch.com/~rsc/regexp/regexp1.html
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# NFA STATES
# ═══════════════════════════════════════════════════════════════════════════════
#
# Every state in the NFA is one of three kinds:
#
#   Literal  — matches a single character (or character predicate)
#   Split    — epsilon node: two outgoing arrows, no input consumed
#   Match    — accepting state: pattern matched successfully
#

SPLIT = -1   # sentinel: state is a split (branch) node
MATCH = -2   # sentinel: state is the accepting (match) node


@dataclass
class State:
    """A single NFA state.

    kind:  character code to match, or SPLIT / MATCH sentinel.
    out:   first outgoing state (after consuming input, or epsilon).
    out1:  second outgoing state (only used by SPLIT nodes).
    predicate: optional function for matching (used by ., \\d, \\w, \\s,
               character classes).
    """
    kind: int = MATCH
    out: Optional[State] = None
    out1: Optional[State] = None
    predicate: Optional[object] = None  # callable(char) -> bool
    last_list: int = 0  # generation counter for simulation


def match_state() -> State:
    """Create the accepting state."""
    return State(kind=MATCH)


def literal_state(ch: int, out: Optional[State] = None) -> State:
    """Create a state that matches a specific character."""
    return State(kind=ch, out=out)


def predicate_state(pred, out: Optional[State] = None) -> State:
    """Create a state that matches via a predicate function."""
    return State(kind=ord('.'), out=out, predicate=pred)


def split_state(out: Optional[State] = None, out1: Optional[State] = None) -> State:
    """Create a split (epsilon/branch) state."""
    return State(kind=SPLIT, out=out, out1=out1)


# ═══════════════════════════════════════════════════════════════════════════════
# NFA FRAGMENTS
# ═══════════════════════════════════════════════════════════════════════════════
#
# During compilation, we build NFA fragments — partial NFAs with dangling
# outgoing arrows that haven't been connected yet. Each fragment tracks its
# start state and a list of dangling arrow "slots" to be patched later.
#

@dataclass
class Frag:
    """An NFA fragment with dangling outgoing arrows.

    start: the entry state of this fragment.
    outs:  list of (state, attr) tuples — dangling arrow slots.
           attr is 'out' or 'out1', indicating which pointer to patch.
    """
    start: State
    outs: list  # list of (State, str) tuples


def patch(outs: list, target: State):
    """Connect all dangling arrows in `outs` to `target`."""
    for state, attr in outs:
        setattr(state, attr, target)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PARSE — Regex to Postfix
# ═══════════════════════════════════════════════════════════════════════════════
#
# We need to convert the regex string into a form suitable for stack-based
# compilation. Two sub-steps:
#
#   1. Insert explicit concatenation operators (we use '\x00' internally)
#   2. Convert infix notation to postfix using the shunting-yard algorithm
#
# Operator precedence (highest to lowest):
#   *, +, ?    (repetition)
#   \x00       (concatenation — implicit in regex syntax)
#   |          (alternation)
#

CONCAT = '\x00'  # internal concatenation operator


# -- Character class parsing --------------------------------------------------

def _parse_char_class(pattern: str, pos: int) -> tuple:
    """Parse a character class like [abc], [a-z], [^a-z] starting at pos.

    Returns (predicate_function, new_pos) where new_pos is past the closing ].
    """
    pos += 1  # skip opening [
    negate = False
    if pos < len(pattern) and pattern[pos] == '^':
        negate = True
        pos += 1

    ranges = []  # list of (lo, hi) character code ranges
    singles = set()

    # Allow ] as first char in class (literal)
    if pos < len(pattern) and pattern[pos] == ']':
        singles.add(ord(']'))
        pos += 1

    while pos < len(pattern) and pattern[pos] != ']':
        ch = pattern[pos]
        if ch == '\\' and pos + 1 < len(pattern):
            pos += 1
            ch = _unescape(pattern[pos])
            if callable(ch):
                # Shorthand like \d inside class — expand it
                # We handle this by storing the predicate
                pred = ch
                singles.add(pred)  # store callable as sentinel
                pos += 1
                continue
        # Check for range a-z
        if pos + 2 < len(pattern) and pattern[pos + 1] == '-' and pattern[pos + 2] != ']':
            lo = ord(ch) if isinstance(ch, str) else ch
            hi_ch = pattern[pos + 2]
            if hi_ch == '\\' and pos + 3 < len(pattern):
                hi = ord(_unescape(pattern[pos + 3]))
                pos += 4
            else:
                hi = ord(hi_ch)
                pos += 3
            if isinstance(lo, str):
                lo = ord(lo)
            ranges.append((lo, hi))
        else:
            c = ord(ch) if isinstance(ch, str) else ch
            singles.add(c)
            pos += 1

    if pos >= len(pattern):
        raise ValueError("Unterminated character class: missing ']'")
    pos += 1  # skip closing ]

    # Build predicate
    frozen_ranges = list(ranges)
    frozen_singles = set(singles)

    def char_class_pred(c: str) -> bool:
        code = ord(c)
        for pred in frozen_singles:
            if callable(pred):
                if pred(c):
                    return not negate
            elif code == pred:
                return not negate
        for lo, hi in frozen_ranges:
            if lo <= code <= hi:
                return not negate
        return negate

    return char_class_pred, pos


def _unescape(ch: str):
    """Handle escape sequences. Returns a char or a predicate function."""
    if ch == 'd':
        return lambda c: c.isdigit()
    elif ch == 'D':
        return lambda c: not c.isdigit()
    elif ch == 'w':
        return lambda c: c.isalnum() or c == '_'
    elif ch == 'W':
        return lambda c: not (c.isalnum() or c == '_')
    elif ch == 's':
        return lambda c: c in ' \t\n\r\f\v'
    elif ch == 'S':
        return lambda c: c not in ' \t\n\r\f\v'
    elif ch == 'n':
        return '\n'
    elif ch == 't':
        return '\t'
    elif ch == 'r':
        return '\r'
    else:
        # Escaped literal: \., \*, \+, \?, \(, \), \|, \\, \[, \]
        return ch


# Tokens: each is (type, value)
# type: 'char' (literal/predicate), 'op' (operator), 'anchor' (^/$)
Token = tuple  # (type_str, value)


def _tokenize(pattern: str) -> list:
    """Tokenize a regex pattern into a list of tokens."""
    tokens = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == '\\' and i + 1 < len(pattern):
            i += 1
            val = _unescape(pattern[i])
            if callable(val):
                tokens.append(('char', val))  # predicate
            else:
                tokens.append(('char', val))  # literal char
            i += 1
        elif ch == '[':
            pred, i = _parse_char_class(pattern, i)
            tokens.append(('char', pred))
        elif ch == '(':
            tokens.append(('op', '('))
            i += 1
        elif ch == ')':
            tokens.append(('op', ')'))
            i += 1
        elif ch in ('|', '*', '+', '?'):
            tokens.append(('op', ch))
            i += 1
        elif ch == '.':
            tokens.append(('char', lambda c: True))  # any char
            i += 1
        elif ch == '^':
            tokens.append(('anchor', '^'))
            i += 1
        elif ch == '$':
            tokens.append(('anchor', '$'))
            i += 1
        else:
            tokens.append(('char', ch))
            i += 1
    return tokens


def _insert_concat(tokens: list) -> list:
    """Insert explicit concatenation operators between tokens that need them.

    Concatenation goes between:
      - char/close-paren/postfix-op FOLLOWED BY char/open-paren/anchor
    """
    result = []
    for i, tok in enumerate(tokens):
        result.append(tok)
        if i + 1 < len(tokens):
            t1_type, t1_val = tok
            t2_type, t2_val = tokens[i + 1]
            # Left side: char, anchor, ), *, +, ?
            left_concat = (
                t1_type == 'char' or
                t1_type == 'anchor' or
                (t1_type == 'op' and t1_val in (')', '*', '+', '?'))
            )
            # Right side: char, anchor, (
            right_concat = (
                t2_type == 'char' or
                t2_type == 'anchor' or
                (t2_type == 'op' and t2_val == '(')
            )
            if left_concat and right_concat:
                result.append(('op', CONCAT))
    return result


def _precedence(op: str) -> int:
    """Operator precedence for shunting-yard."""
    if op == '|':
        return 1
    if op == CONCAT:
        return 2
    if op in ('*', '+', '?'):
        return 3
    return 0


def _to_postfix(tokens: list) -> list:
    """Convert infix token list to postfix using shunting-yard algorithm."""
    output = []
    op_stack = []

    for tok_type, tok_val in tokens:
        if tok_type == 'char' or tok_type == 'anchor':
            output.append((tok_type, tok_val))
        elif tok_type == 'op':
            if tok_val == '(':
                op_stack.append(tok_val)
            elif tok_val == ')':
                while op_stack and op_stack[-1] != '(':
                    output.append(('op', op_stack.pop()))
                if not op_stack:
                    raise ValueError("Mismatched parentheses: extra ')'")
                op_stack.pop()  # remove '('
            elif tok_val in ('*', '+', '?'):
                # Postfix operators — push directly to output
                output.append(('op', tok_val))
            else:
                # Infix operators: CONCAT, |
                while (op_stack and op_stack[-1] != '(' and
                       _precedence(op_stack[-1]) >= _precedence(tok_val)):
                    output.append(('op', op_stack.pop()))
                op_stack.append(tok_val)

    while op_stack:
        op = op_stack.pop()
        if op == '(':
            raise ValueError("Mismatched parentheses: extra '('")
        output.append(('op', op))

    return output


def parse(pattern: str) -> list:
    """Parse a regex string into postfix token list.

    >>> parse("ab")
    [('char', 'a'), ('char', 'b'), ('op', '\\x00')]
    """
    tokens = _tokenize(pattern)
    tokens = _insert_concat(tokens)
    return _to_postfix(tokens)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: COMPILE — Postfix to NFA (Thompson's Construction)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Walk the postfix token list. For each token, either push a new fragment
# onto the stack (literals) or pop fragment(s) and combine them (operators).
#

# Anchor sentinels
ANCHOR_START = -3
ANCHOR_END = -4


def compile_nfa(postfix: list) -> State:
    """Compile postfix tokens into an NFA. Returns the start state.

    Uses Thompson's construction: exactly one state per literal character,
    one split state per operator. Fragments are combined on a stack.
    """
    stack: list[Frag] = []
    matchstate = match_state()

    for tok_type, tok_val in postfix:
        if tok_type == 'anchor':
            # Anchors: create special states
            if tok_val == '^':
                s = State(kind=ANCHOR_START)
                stack.append(Frag(s, [(s, 'out')]))
            elif tok_val == '$':
                s = State(kind=ANCHOR_END)
                stack.append(Frag(s, [(s, 'out')]))

        elif tok_type == 'char':
            # Literal or predicate
            if callable(tok_val):
                s = State(kind=ord('.'), predicate=tok_val)
            else:
                s = State(kind=ord(tok_val))
            stack.append(Frag(s, [(s, 'out')]))

        elif tok_type == 'op':
            op = tok_val

            if op == CONCAT:
                # Concatenation: connect e1's dangling arrows to e2's start
                if len(stack) < 2:
                    raise ValueError("Invalid regex: missing operand for concatenation")
                e2 = stack.pop()
                e1 = stack.pop()
                patch(e1.outs, e2.start)
                stack.append(Frag(e1.start, e2.outs))

            elif op == '|':
                # Alternation: new split state branching to e1 and e2
                if len(stack) < 2:
                    raise ValueError("Invalid regex: missing operand for '|'")
                e2 = stack.pop()
                e1 = stack.pop()
                s = split_state(e1.start, e2.start)
                stack.append(Frag(s, e1.outs + e2.outs))

            elif op == '*':
                # Zero or more: split → (e → loop back) or skip
                if not stack:
                    raise ValueError("Invalid regex: nothing to repeat with '*'")
                e = stack.pop()
                s = split_state(e.start, None)
                patch(e.outs, s)
                stack.append(Frag(s, [(s, 'out1')]))

            elif op == '+':
                # One or more: e → split (loop back or exit)
                if not stack:
                    raise ValueError("Invalid regex: nothing to repeat with '+'")
                e = stack.pop()
                s = split_state(e.start, None)
                patch(e.outs, s)
                stack.append(Frag(e.start, [(s, 'out1')]))

            elif op == '?':
                # Zero or one: split → e or skip
                if not stack:
                    raise ValueError("Invalid regex: nothing to repeat with '?'")
                e = stack.pop()
                s = split_state(e.start, None)
                stack.append(Frag(s, e.outs + [(s, 'out1')]))

    if len(stack) != 1:
        raise ValueError(f"Invalid regex: stack has {len(stack)} fragments (expected 1)")

    # Patch final fragment to the match state
    frag = stack[0]
    patch(frag.outs, matchstate)
    return frag.start


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: SIMULATE — Run NFA on Input String
# ═══════════════════════════════════════════════════════════════════════════════
#
# Instead of backtracking, we track ALL active states simultaneously.
# For each input character, we advance every active state in parallel.
# This gives us guaranteed O(pattern_length × text_length) performance.
#

_generation = 0


def _add_state(state_list: list, state: State, gen: int):
    """Add a state to the list, following epsilon transitions (SPLIT states).

    Uses a generation counter to avoid adding duplicate states.
    Anchor states are added to the list (not followed through) so they
    can be checked at the appropriate time during simulation.
    """
    if state is None or state.last_list == gen:
        return
    state.last_list = gen

    if state.kind == SPLIT:
        # Follow both epsilon arrows without consuming input
        _add_state(state_list, state.out, gen)
        _add_state(state_list, state.out1, gen)
        return

    state_list.append(state)


def _step(current: list, ch: str, gen: int) -> list:
    """Advance NFA one step: consume character `ch`, return next state list."""
    nxt = []
    for state in current:
        if state.kind == MATCH:
            continue
        # Skip anchors — they don't consume input
        if state.kind in (ANCHOR_START, ANCHOR_END):
            continue

        if state.predicate is not None:
            # Predicate match (., \d, \w, \s, character classes)
            if state.predicate(ch):
                _add_state(nxt, state.out, gen)
        elif state.kind == ord(ch):
            # Exact character match
            _add_state(nxt, state.out, gen)
    return nxt


def _is_match(states: list) -> bool:
    """Check if any state in the list is the accepting state."""
    return any(s.kind == MATCH for s in states)


def _has_anchor_start(state: State, visited: set = None) -> bool:
    """Check if the NFA starts with a ^ anchor."""
    if visited is None:
        visited = set()
    if id(state) in visited:
        return False
    visited.add(id(state))
    if state.kind == ANCHOR_START:
        return True
    if state.kind == SPLIT:
        return (_has_anchor_start(state.out, visited) and
                _has_anchor_start(state.out1, visited))
    return False


def _resolve_anchors(states: list, at_start: bool, at_end: bool, gen: int) -> list:
    """Follow through anchor states based on current position context.

    Anchor states act as epsilon transitions that only pass when the
    position condition is met:
      - ANCHOR_START (^): passes only at start of string
      - ANCHOR_END ($): passes only at end of string
    """
    global _generation
    result = []
    _generation += 1
    gen = _generation
    for s in states:
        if s.kind == ANCHOR_START:
            if at_start:
                _add_state(result, s.out, gen)
        elif s.kind == ANCHOR_END:
            if at_end:
                _add_state(result, s.out, gen)
        else:
            _add_state(result, s, gen)

    # Recursively resolve if new anchors appeared
    if any(s.kind in (ANCHOR_START, ANCHOR_END) for s in result):
        return _resolve_anchors(result, at_start, at_end, gen)
    return result


def simulate(start: State, text: str) -> bool:
    """Run the NFA on `text`. Returns True if the pattern matches.

    This is a FULL match — the pattern must match the entire string.
    For partial/search matching, use search() instead.
    """
    global _generation

    _generation += 1
    current = []
    _add_state(current, start, _generation)

    # Resolve anchors at start position
    at_end = len(text) == 0
    current = _resolve_anchors(current, at_start=True, at_end=at_end, gen=_generation)

    for idx, ch in enumerate(text):
        _generation += 1
        current = _step(current, ch, _generation)
        # Resolve anchors: no longer at start, check if at end
        at_end = (idx == len(text) - 1)
        current = _resolve_anchors(current, at_start=False, at_end=at_end, gen=_generation)

    return _is_match(current)


def search(start: State, text: str) -> tuple:
    """Search for the pattern anywhere in `text`.

    Returns (start_index, end_index) of the first match, or None.
    The match is the leftmost match, and for each start position
    we find the longest match (greedy).
    """
    global _generation

    has_caret = _has_anchor_start(start)

    for i in range(len(text) + 1):
        if has_caret and i > 0:
            break  # ^ means must start at position 0

        _generation += 1
        current = []
        _add_state(current, start, _generation)

        # Resolve anchors at this position
        at_start = (i == 0)
        at_end = (i == len(text))
        current = _resolve_anchors(current, at_start=at_start, at_end=at_end, gen=_generation)

        # Check for zero-length match at this position
        last_match = None
        if _is_match(current):
            last_match = i

        for j in range(i, len(text)):
            _generation += 1
            current = _step(current, text[j], _generation)

            # Resolve anchors after consuming character
            at_end = (j + 1 == len(text))
            current = _resolve_anchors(current, at_start=False, at_end=at_end, gen=_generation)

            if _is_match(current):
                last_match = j + 1

            if not current:
                break

        if last_match is not None:
            return (i, last_match)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

class Regex:
    """Compiled regular expression object.

    Usage:
        >>> r = Regex("a(b|c)*d")
        >>> r.fullmatch("abcbd")
        True
        >>> r.search("xxabcdyy")
        (2, 6)
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        postfix = parse(pattern)
        self.start = compile_nfa(postfix)

    def fullmatch(self, text: str) -> bool:
        """Test if the ENTIRE text matches the pattern."""
        return simulate(self.start, text)

    def search(self, text: str) -> tuple:
        """Find the first match anywhere in text.

        Returns (start, end) indices or None.
        """
        return search(self.start, text)

    def match(self, text: str) -> tuple:
        """Match at the beginning of text.

        Returns (0, end) or None.
        """
        result = search(self.start, text)
        if result and result[0] == 0:
            return result
        # If pattern doesn't have ^, try anchored match
        anchored = Regex('^' + self.pattern)
        return search(anchored.start, text)

    def findall(self, text: str) -> list:
        """Find all non-overlapping matches in text.

        Returns list of matched substrings.
        """
        results = []
        i = 0
        while i <= len(text):
            result = search(self.start, text[i:])
            if result is None:
                break
            start, end = result
            matched = text[i + start:i + end]
            results.append(matched)
            # Advance past this match (at least 1 char to avoid infinite loop)
            i += start + max(end - start, 1)
        return results

    def __repr__(self):
        return f"Regex({self.pattern!r})"


def compile(pattern: str) -> Regex:
    """Compile a regex pattern into a Regex object.

    >>> r = compile("hello|world")
    >>> r.fullmatch("hello")
    True
    """
    return Regex(pattern)


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def _demo():
    """Run a few examples to show the engine in action."""
    print("Regular Expression Engine — Thompson's NFA Construction")
    print("=" * 56)
    print()

    examples = [
        ("a",         "a",       True),
        ("a",         "b",       False),
        ("ab",        "ab",      True),
        ("a|b",       "a",       True),
        ("a|b",       "b",       True),
        ("a|b",       "c",       False),
        ("a*",        "",        True),
        ("a*",        "aaa",     True),
        ("a+",        "",        False),
        ("a+",        "aaa",     True),
        ("a?",        "",        True),
        ("a?",        "a",       True),
        ("a(b|c)*d",  "abcbd",   True),
        ("a(b|c)*d",  "ad",      True),
        ("a(b|c)*d",  "aed",     False),
        ("(ab)+",     "ababab",  True),
        ("\\d+",      "12345",   True),
        ("\\w+@\\w+", "a@b",     True),
        ("[a-z]+",    "hello",   True),
        ("[^0-9]+",   "abc",     True),
        (".",         "x",       True),
        (".+",        "hello",   True),
    ]

    for pattern, text, expected in examples:
        r = compile(pattern)
        result = r.fullmatch(text)
        status = "OK" if result == expected else "FAIL"
        match_str = "match" if result else "no match"
        print(f"  [{status}]  /{pattern}/  vs  {text!r:12s}  →  {match_str}")

    print()

    # Search examples
    print("Search examples:")
    print("-" * 40)
    search_examples = [
        ("world",     "hello world!",    (6, 11)),
        ("\\d+",      "abc 123 def",     (4, 7)),
        ("[A-Z]+",    "hello WORLD bye", (6, 11)),
    ]
    for pattern, text, expected in search_examples:
        r = compile(pattern)
        result = r.search(text)
        status = "OK" if result == expected else f"FAIL (got {result})"
        print(f"  [{status}]  /{pattern}/  in  {text!r}  →  {result}")

    print()
    print("Findall examples:")
    print("-" * 40)
    r = compile("\\d+")
    result = r.findall("abc 12 def 345 ghi 6")
    print(f"  /\\d+/  in  'abc 12 def 345 ghi 6'  →  {result}")

    r = compile("[a-z]+")
    result = r.findall("Hello World 123 test")
    print(f"  /[a-z]+/  in  'Hello World 123 test'  →  {result}")


if __name__ == "__main__":
    _demo()
