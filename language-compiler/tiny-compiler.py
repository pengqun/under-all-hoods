"""
A Super Tiny Compiler — in Python
==================================

Compiles Lisp-style function calls into C-style function calls:

    SOURCE (Lisp-like)                  TARGET (C-like)
    ──────────────────                  ────────────────
    (add 2 2)                     →    add(2, 2);
    (subtract 4 2)                →    subtract(4, 2);
    (add 2 (subtract 4 2))       →    add(2, subtract(4, 2));

The compiler works in four phases, each one feeding into the next:

    Source Code
        │
        ▼
    ┌──────────┐    "( add 2 2 )"  →  [Token, Token, ...]
    │ TOKENIZE │    Break raw text into meaningful chunks.
    └──────────┘
        │
        ▼
    ┌──────────┐    [Token, ...]  →  Program(body=[CallExpression(...)])
    │  PARSE   │    Arrange tokens into a tree structure (AST).
    └──────────┘
        │
        ▼
    ┌───────────┐   Source AST  →  Target AST
    │ TRANSFORM │   Reshape the tree for the target language.
    └───────────┘
        │
        ▼
    ┌───────────┐   Target AST  →  "add(2, 2);"
    │ GENERATE  │   Walk the tree and emit code as a string.
    └───────────┘
        │
        ▼
    Target Code

Based on: https://github.com/jamiebuilds/the-super-tiny-compiler
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENS
#
# The tokenizer breaks source code into these atomic pieces.  Each token
# remembers what *kind* of thing it is and what characters it contains.
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Token:
    """
    A single lexical token.

    Attributes:
        type:  One of 'paren', 'number', 'string', or 'name'.
        value: The raw characters that make up this token.

    Examples:
        Token('paren',  '(')
        Token('number', '42')
        Token('string', 'hello')
        Token('name',   'add')
    """
    type: str
    value: str


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE AST NODES
#
# These represent the *structure* of the source language.  The parser reads
# a flat list of tokens and produces a tree made of these nodes.
#
#   Program
#     └─ CallExpression("add")
#          ├─ NumberLiteral("2")
#          └─ NumberLiteral("3")
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class NumberLiteral:
    """A numeric value like ``42``."""
    value: str

@dataclass
class StringLiteral:
    """A quoted string value like ``"hello"``."""
    value: str

@dataclass
class CallExpression:
    """
    A function call in the source language.

    In source code this looks like ``(add 2 3)`` — the name comes first,
    then the parameters follow as nested expressions.
    """
    name: str
    params: list = field(default_factory=list)

@dataclass
class Program:
    """Root node of the source AST.  Contains top-level expressions."""
    body: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# TARGET AST NODES
#
# The transformer rewrites the source AST into this shape, which maps
# directly onto C-style syntax.
#
#   TargetProgram
#     └─ ExpressionStatement
#          └─ TargetCallExpression
#               ├─ callee: Identifier("add")
#               └─ arguments: [NumberLiteral("2"), NumberLiteral("3")]
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Identifier:
    """A name reference, used as the callee of a function call."""
    name: str

@dataclass
class TargetCallExpression:
    """A C-style function call like ``add(2, 3)``."""
    callee: Identifier
    arguments: list = field(default_factory=list)

@dataclass
class ExpressionStatement:
    """Wraps a top-level expression so it becomes a statement (gets a ``;``)."""
    expression: object

@dataclass
class TargetProgram:
    """Root node of the target AST."""
    body: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — TOKENIZER
#
# Scans the source string character by character and groups them into tokens.
#
#   "(add 2 3)"
#     → [Token('paren','('), Token('name','add'), Token('number','2'),
#        Token('number','3'), Token('paren',')')]
#
# Rules:
#   • '(' and ')'     → paren token
#   • Consecutive digits → number token
#   • Text in "quotes"  → string token
#   • Consecutive letters → name token
#   • Whitespace        → skipped
#   • Anything else     → error
# ═══════════════════════════════════════════════════════════════════════════════

def tokenize(source: str) -> list[Token]:
    """
    Break *source* into a list of tokens.

    >>> tokenize("(add 2 3)")
    [Token(type='paren', value='('), Token(type='name', value='add'), \
Token(type='number', value='2'), Token(type='number', value='3'), \
Token(type='paren', value=')')]

    Raises:
        SyntaxError: On unterminated strings or unexpected characters.
    """
    tokens: list[Token] = []
    pos = 0

    while pos < len(source):
        char = source[pos]

        # ── Parentheses ──────────────────────────────────────────────
        if char in ("(", ")"):
            tokens.append(Token("paren", char))
            pos += 1
            continue

        # ── Whitespace — skip ────────────────────────────────────────
        if char.isspace():
            pos += 1
            continue

        # ── Numbers — consume consecutive digits ─────────────────────
        if char.isdigit():
            start = pos
            while pos < len(source) and source[pos].isdigit():
                pos += 1
            tokens.append(Token("number", source[start:pos]))
            continue

        # ── Strings — everything between double quotes ───────────────
        if char == '"':
            pos += 1  # skip opening quote
            start = pos
            while pos < len(source) and source[pos] != '"':
                pos += 1
            if pos >= len(source):
                raise SyntaxError("Unterminated string literal")
            tokens.append(Token("string", source[start:pos]))
            pos += 1  # skip closing quote
            continue

        # ── Names — consecutive letters ──────────────────────────────
        if char.isalpha():
            start = pos
            while pos < len(source) and source[pos].isalpha():
                pos += 1
            tokens.append(Token("name", source[start:pos]))
            continue

        # ── Unknown character ────────────────────────────────────────
        raise SyntaxError(f"Unexpected character: {char!r}")

    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PARSER
#
# Transforms the flat list of tokens into a tree (AST) using recursive
# descent.  The key insight: when we see '(' we enter a CallExpression
# and recursively read parameters until we reach the matching ')'.
#
#   [Token('paren','('), Token('name','add'), Token('number','2'),
#    Token('number','3'), Token('paren',')')]
#
#   → Program(body=[
#       CallExpression(name='add', params=[
#           NumberLiteral('2'),
#           NumberLiteral('3'),
#       ])
#     ])
# ═══════════════════════════════════════════════════════════════════════════════

def parse(tokens: list[Token]) -> Program:
    """
    Build a source AST from *tokens* using recursive descent.

    Raises:
        SyntaxError: On unexpected token sequences (e.g. missing names).
    """
    pos = 0

    def walk():
        """Parse one expression and advance *pos* past it."""
        nonlocal pos

        if pos >= len(tokens):
            raise SyntaxError("Unexpected end of input")

        token = tokens[pos]

        # ── Number literal ───────────────────────────────────────────
        if token.type == "number":
            pos += 1
            return NumberLiteral(token.value)

        # ── String literal ───────────────────────────────────────────
        if token.type == "string":
            pos += 1
            return StringLiteral(token.value)

        # ── Call expression — begins with '(' ────────────────────────
        if token.type == "paren" and token.value == "(":
            pos += 1  # skip '('

            # Next token must be the function name
            if pos >= len(tokens):
                raise SyntaxError("Unexpected end of input after '('")
            name_token = tokens[pos]
            if name_token.type != "name":
                raise SyntaxError(
                    f"Expected function name after '(', got {name_token.type}: "
                    f"{name_token.value!r}"
                )
            pos += 1

            # Collect parameters until we hit ')'
            params: list = []
            while pos < len(tokens) and not (
                tokens[pos].type == "paren" and tokens[pos].value == ")"
            ):
                params.append(walk())

            if pos >= len(tokens):
                raise SyntaxError("Missing closing ')'")

            pos += 1  # skip ')'
            return CallExpression(name_token.value, params)

        raise SyntaxError(f"Unexpected token: {token.type} ({token.value!r})")

    # Parse all top-level expressions
    program = Program()
    while pos < len(tokens):
        program.body.append(walk())

    return program


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — TRANSFORMER
#
# Converts the source AST into the target AST.  The two key changes:
#
#   1. CallExpression becomes TargetCallExpression with an Identifier callee.
#   2. Top-level expressions are wrapped in ExpressionStatement.
#
#   Source:                          Target:
#   ───────                          ───────
#   Program                          TargetProgram
#     └─ CallExpression("add")         └─ ExpressionStatement
#          ├─ NumberLiteral("2")            └─ TargetCallExpression
#          └─ NumberLiteral("3")                 ├─ Identifier("add")
#                                                └─ [NumberLiteral("2"),
#                                                    NumberLiteral("3")]
# ═══════════════════════════════════════════════════════════════════════════════

def transform(source_ast: Program) -> TargetProgram:
    """
    Reshape *source_ast* into a target AST suitable for C-style code
    generation.
    """

    def transform_node(node):
        """Recursively transform a single node."""
        if isinstance(node, NumberLiteral):
            return NumberLiteral(node.value)

        if isinstance(node, StringLiteral):
            return StringLiteral(node.value)

        if isinstance(node, CallExpression):
            return TargetCallExpression(
                callee=Identifier(node.name),
                arguments=[transform_node(param) for param in node.params],
            )

        raise TypeError(f"Unknown node: {type(node).__name__}")

    # Build the target program, wrapping each top-level node
    target = TargetProgram()
    for node in source_ast.body:
        target.body.append(ExpressionStatement(transform_node(node)))

    return target


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — CODE GENERATOR
#
# Walks the target AST and emits code as a string.  Each node type maps
# to a simple code pattern:
#
#   TargetProgram         →  statements joined by newlines
#   ExpressionStatement   →  expression + ";"
#   TargetCallExpression  →  callee(arg1, arg2, ...)
#   Identifier            →  name
#   NumberLiteral         →  value
#   StringLiteral         →  "value"
# ═══════════════════════════════════════════════════════════════════════════════

def generate(node) -> str:
    """
    Recursively emit target source code from a target AST *node*.

    >>> generate(TargetProgram(body=[
    ...     ExpressionStatement(TargetCallExpression(
    ...         callee=Identifier('add'),
    ...         arguments=[NumberLiteral('2'), NumberLiteral('3')],
    ...     ))
    ... ]))
    'add(2, 3);'
    """
    if isinstance(node, TargetProgram):
        return "\n".join(generate(stmt) for stmt in node.body)

    if isinstance(node, ExpressionStatement):
        return generate(node.expression) + ";"

    if isinstance(node, TargetCallExpression):
        callee = generate(node.callee)
        args = ", ".join(generate(arg) for arg in node.arguments)
        return f"{callee}({args})"

    if isinstance(node, Identifier):
        return node.name

    if isinstance(node, NumberLiteral):
        return node.value

    if isinstance(node, StringLiteral):
        return f'"{node.value}"'

    raise TypeError(f"Unknown node: {type(node).__name__}")


# ═══════════════════════════════════════════════════════════════════════════════
# COMPILER — the full pipeline
#
# This is the only function most callers need.  It chains the four phases
# together:  tokenize → parse → transform → generate.
# ═══════════════════════════════════════════════════════════════════════════════

def compiler(source: str) -> str:
    """
    Compile Lisp-style *source* code into C-style target code.

    >>> compiler("(add 2 2)")
    'add(2, 2);'
    >>> compiler("(subtract 4 2)")
    'subtract(4, 2);'
    >>> compiler("(add 2 (subtract 4 2))")
    'add(2, subtract(4, 2));'
    """
    tokens = tokenize(source)
    source_ast = parse(tokens)
    target_ast = transform(source_ast)
    output = generate(target_ast)
    return output


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — interactive demo
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    examples = [
        "(add 2 2)",
        "(subtract 4 2)",
        "(add 2 (subtract 4 2))",
        "(add 1 (subtract 3 (add 4 5)))",
        '(concat "hello" " " "world")',
    ]

    print("Super Tiny Compiler — Python Edition")
    print("=" * 40)
    print()

    for source in examples:
        result = compiler(source)
        print(f"  input:  {source}")
        print(f"  output: {result}")
        print()
