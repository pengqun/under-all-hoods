# Regex Engine: Under the Hood

How does a regular expression engine match patterns against text? This module builds one from scratch using **Thompson's NFA construction** — the same algorithm behind fast regex engines like RE2 and Plan 9 grep.

## What it Does

This engine compiles a regex pattern into a **Nondeterministic Finite Automaton (NFA)**, then simulates it against input text — tracking all possible states simultaneously. No backtracking, no exponential blowup.

```
Pattern          Meaning
───────          ───────
a                Literal character
.                Any single character
ab               Concatenation
a|b              Alternation (or)
a*               Zero or more
a+               One or more
a?               Zero or one
(ab|cd)          Grouping
\d \w \s         Digit, word char, whitespace
[abc] [a-z]      Character classes
[^abc]           Negated character class
^ $              Start/end anchors
```

## The Three Phases

Every regex match goes through the same pipeline:

```
Regex String  →  Postfix Tokens  →  NFA  →  Match Result
                  Phase 1           Phase 2   Phase 3
```

### Phase 1: Parse (Regex → Postfix)

The parser converts the regex into a form suitable for stack-based compilation:

1. **Tokenize** — break the pattern into tokens (literals, operators, character classes, escapes)
2. **Insert concatenation** — add explicit concat operators where they're implied (`ab` → `a·b`)
3. **Shunting-yard** — convert infix to postfix, respecting operator precedence

```
Precedence (highest → lowest):
  *, +, ?    repetition
  ·          concatenation (implicit)
  |          alternation
```

Example: `a(b|c)*d` → `a b c | * · d ·`

### Phase 2: Compile (Postfix → NFA via Thompson's Construction)

Walk the postfix tokens with a stack of NFA fragments. Each token either pushes a new fragment or combines existing ones:

**Literal `a`** — one state matching 'a', one dangling arrow:
```
 ──→ [a] ──→
```

**Concatenation `e₁·e₂`** — connect e₁'s output to e₂'s start:
```
 ──→ [e₁] ──→ [e₂] ──→
```

**Alternation `e₁|e₂`** — new split state branching to both:
```
       ┌──→ [e₁] ──→
 ──→ [split]
       └──→ [e₂] ──→
```

**Zero or more `e*`** — split: try e (loop back) or skip:
```
       ┌──→ [e] ──┐
 ──→ [split]←──────┘
       └──→ (skip)
```

**One or more `e+`** — must match e, then optionally loop:
```
 ──→ [e] ──→ [split] ──→
              └──→ [e] (loop back)
```

**Zero or one `e?`** — split: try e or skip:
```
       ┌──→ [e] ──→
 ──→ [split]
       └──→ (skip)
```

Each construction creates exactly **one new state** per operator — keeping the NFA compact.

### Phase 3: Simulate (NFA + Text → Match)

Instead of backtracking (which can be exponentially slow), we track **all active states simultaneously**:

```
1. Start with the set of states reachable from the NFA start
2. For each input character:
   a. For every active state that matches the character,
      add its successor to the next state set
   b. Follow epsilon (split) transitions automatically
   c. Swap current ↔ next
3. If the accepting state is in the final set → match!
```

This gives **guaranteed O(m × n)** time — where m is the pattern length and n is the text length. The classic pathological case `a?ⁿaⁿ` matching `aⁿ` runs in linear time, while backtracking engines take exponential time.

## Supported Features

| Feature | Syntax | Example |
|---------|--------|---------|
| Literals | `a`, `b`, `1` | `hello` matches "hello" |
| Any char | `.` | `.+` matches any non-empty string |
| Alternation | `\|` | `cat\|dog` matches "cat" or "dog" |
| Zero or more | `*` | `a*` matches "", "a", "aaa" |
| One or more | `+` | `a+` matches "a", "aaa" but not "" |
| Optional | `?` | `colou?r` matches "color" and "colour" |
| Grouping | `()` | `(ab)+` matches "ab", "abab" |
| Digit | `\d`, `\D` | `\d+` matches "123" |
| Word char | `\w`, `\W` | `\w+` matches "hello_123" |
| Whitespace | `\s`, `\S` | `\s+` matches "  \t\n" |
| Char class | `[abc]` | `[aeiou]` matches vowels |
| Char range | `[a-z]` | `[A-Za-z]` matches any letter |
| Negated class | `[^abc]` | `[^0-9]` matches non-digits |
| Start anchor | `^` | `^hello` matches at start only |
| End anchor | `$` | `world$` matches at end only |
| Escaped chars | `\.`, `\\` | `\.` matches literal "." |

## Running It

```bash
cd regex-engine
python regex-engine.py
```

Output:

```
Regular Expression Engine — Thompson's NFA Construction
========================================================

  [OK]  /a/  vs  'a'           →  match
  [OK]  /a/  vs  'b'           →  no match
  [OK]  /ab/  vs  'ab'          →  match
  [OK]  /a|b/  vs  'a'           →  match
  [OK]  /a|b/  vs  'b'           →  match
  [OK]  /a|b/  vs  'c'           →  no match
  [OK]  /a*/  vs  ''            →  match
  [OK]  /a*/  vs  'aaa'         →  match
  [OK]  /a+/  vs  ''            →  no match
  [OK]  /a+/  vs  'aaa'         →  match
  ...

Search examples:
  [OK]  /world/  in  'hello world!'  →  (6, 11)
  [OK]  /\d+/  in  'abc 123 def'  →  (4, 7)

Findall examples:
  /\d+/  in  'abc 12 def 345 ghi 6'  →  ['12', '345', '6']
```

## Running Tests

```bash
cd regex-engine
python -m pytest test_regex_engine.py -v
```

The test suite covers each phase in isolation plus end-to-end matching — 120 test cases covering literals, operators, character classes, anchors, escape sequences, search/findall, edge cases, and real-world patterns.

## Implementation: `regex-engine.py`

### References

- [Regular Expression Matching Can Be Simple And Fast](https://swtch.com/~rsc/regexp/regexp1.html) by Russ Cox — the foundational article this implementation is based on, explaining Thompson's NFA construction
- [Regular Expression Matching: the Virtual Machine Approach](https://swtch.com/~rsc/regexp/regexp2.html) by Russ Cox — the follow-up exploring VM-based regex implementations
- [Implementing Regular Expressions](https://swtch.com/~rsc/regexp/) by Russ Cox — the full series on regex internals
- [Introduction to the Theory of Computation](https://math.mit.edu/~sipser/book.html) by Michael Sipser — the textbook treatment of finite automata and regular languages
