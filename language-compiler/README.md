# Language Compiler: Under the Hood

How does a compiler transform source code into something a machine can understand? This module breaks down the process — tokenizing, parsing, transforming, and code generation — through a super tiny compiler written in Python.

## What it Does

This compiler translates **Lisp-style** function calls into **C-style** function calls:

```
SOURCE (Lisp-like)                  TARGET (C-like)
──────────────────                  ────────────────
(add 2 2)                     →    add(2, 2);
(subtract 4 2)                →    subtract(4, 2);
(add 2 (subtract 4 2))       →    add(2, subtract(4, 2));
```

That's it — a simple syntax translation. But inside that translation live the same four phases that **every** real compiler uses.

## The Four Phases

Every compiler — from this tiny one to GCC — follows the same basic pipeline:

```
Source Code  →  Tokens  →  Source AST  →  Target AST  →  Target Code
               Phase 1     Phase 2        Phase 3         Phase 4
```

### Phase 1: Tokenizer (Lexical Analysis)

The tokenizer reads the raw source string character by character and groups them into **tokens** — the smallest meaningful pieces of the language.

```
Input:  "(add 2 3)"

Output: [
    Token(paren, "("),
    Token(name,  "add"),
    Token(number, "2"),
    Token(number, "3"),
    Token(paren, ")"),
]
```

It recognizes four kinds of tokens:

| Token Type | What It Matches      | Example    |
|------------|----------------------|------------|
| `paren`    | `(` or `)`           | `(`        |
| `number`   | Consecutive digits   | `42`       |
| `string`   | Text in `"quotes"`   | `"hello"`  |
| `name`     | Consecutive letters  | `add`      |

Whitespace is skipped. Anything else is an error.

### Phase 2: Parser (Syntactic Analysis)

The parser takes the flat list of tokens and builds them into a tree — the **Abstract Syntax Tree (AST)**. This tree captures the *structure* of the code: which function is being called, and what are its arguments.

```
Tokens for "(add 2 (subtract 4 2))"

        Program
          │
     CallExpression("add")
        ┌──┴──┐
  Number("2")  CallExpression("subtract")
                   ┌──┴──┐
             Number("4")  Number("2")
```

The parser uses **recursive descent**: when it sees `(` it enters a call expression, reads the name, then recursively parses each parameter until it finds the matching `)`.

### Phase 3: Transformer

The transformer walks the source AST and builds a new tree — the **target AST** — that maps directly onto C-style syntax. Two key changes happen:

1. `CallExpression(name="add")` becomes `TargetCallExpression(callee=Identifier("add"))` — the function name becomes a proper `Identifier` node with a `callee` relationship.
2. Top-level expressions get wrapped in `ExpressionStatement` nodes — so they produce semicolons in the output.

```
SOURCE AST                              TARGET AST
──────────                              ──────────
Program                                 TargetProgram
  └─ CallExpression("add")               └─ ExpressionStatement
       ├─ NumberLiteral("2")                  └─ TargetCallExpression
       └─ NumberLiteral("3")                       ├─ Identifier("add")
                                                   └─ arguments:
                                                        NumberLiteral("2")
                                                        NumberLiteral("3")
```

### Phase 4: Code Generator

The code generator walks the target AST and emits actual code as a string. Each node type maps to a simple output pattern:

| Node Type              | Output Pattern            |
|------------------------|---------------------------|
| `TargetProgram`        | Statements joined by `\n` |
| `ExpressionStatement`  | `expression;`             |
| `TargetCallExpression` | `callee(arg1, arg2)`      |
| `Identifier`           | `name`                    |
| `NumberLiteral`        | `value`                   |
| `StringLiteral`        | `"value"`                 |

## Running It

```bash
cd language-compiler
python javascript-compiler-jamie.py
```

Output:

```
Super Tiny Compiler — Python Edition
========================================

  input:  (add 2 2)
  output: add(2, 2);

  input:  (subtract 4 2)
  output: subtract(4, 2);

  input:  (add 2 (subtract 4 2))
  output: add(2, subtract(4, 2));

  input:  (add 1 (subtract 3 (add 4 5)))
  output: add(1, subtract(3, add(4, 5)));

  input:  (concat "hello" " " "world")
  output: concat("hello", " ", "world");
```

## Running Tests

```bash
cd language-compiler
python -m pytest test_compiler.py -v
```

The test suite covers each phase in isolation plus end-to-end compiler tests — 50+ test cases covering normal operation, edge cases, and error handling.

## Implementation: `javascript-compiler-jamie.py`

### Credit

- Original Project: [the-super-tiny-compiler](https://github.com/jamiebuilds/the-super-tiny-compiler) by Jamie Kyle
- This is a complete Python reimplementation for educational purposes
