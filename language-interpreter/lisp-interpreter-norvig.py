"""
A Lisp Interpreter — in Python
================================

Interprets a subset of Scheme (a Lisp dialect), turning source code into
results by parsing and evaluating expressions directly:

    SOURCE (Scheme)                      RESULT
    ───────────────                      ──────
    (+ 1 2)                         →    3
    (* 2 (+ 3 4))                   →    14
    (if (> 10 5) "yes" "no")        →    "yes"
    (define sq (lambda (x) (* x x)))
    (sq 7)                          →    49

The interpreter works in two main phases:

    Source Code
        │
        ▼
    ┌──────────┐    "(+ 1 2)"  →  ['+', 1, 2]
    │  PARSE   │    Tokenize the text, then build a tree of
    │          │    nested Python lists (the AST).
    └──────────┘
        │
        ▼
    ┌──────────┐    ['+', 1, 2]  →  3
    │   EVAL   │    Walk the tree: look up variables, apply
    │          │    special forms, call procedures.
    └──────────┘
        │
        ▼
      Result

Unlike a compiler (which translates source into *another* language), an
interpreter *executes* the program directly — the AST is evaluated in-place
using an environment of variable bindings and a set of built-in procedures.

A key insight: the AST is just nested Python lists and primitives.  There's
no need for special node classes — ``(+ 1 (* 2 3))`` parses to
``['+', 1, ['*', 2, 3]]``, and eval walks that list recursively.

Based on: https://www.norvig.com/lispy.html
"""

from __future__ import annotations

import math
import operator as op
import sys


# ═══════════════════════════════════════════════════════════════════════════════
# TYPES
#
# The interpreter represents Scheme values using plain Python types:
#
#   Scheme       Python
#   ──────       ──────
#   number       int or float
#   symbol       str
#   list         list
#   #t / #f      True / False
#   procedure    Procedure (defined below) or Python callable
#
# No wrapper classes needed — Python's built-in types do the job.
# ═══════════════════════════════════════════════════════════════════════════════

Symbol = str              # A Scheme symbol is a Python str
Number = (int, float)     # A Scheme number is a Python int or float
Atom = (Symbol, Number)   # An atom is a symbol or number
List = list               # A Scheme list is a Python list
Exp = (Atom, List)        # An expression is an atom or list


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — TOKENIZER
#
# The simplest possible tokenizer: pad parentheses with spaces so they become
# separate tokens, then split on whitespace.  That's it — two calls.
#
#   "(+ 1 (* 2 3))"
#     → ['(', '+', '1', '(', '*', '2', '3', ')', ')']
#
# This works because Scheme's syntax is so uniform — no operator precedence,
# no infix notation, no special delimiters beyond parentheses.
# ═══════════════════════════════════════════════════════════════════════════════

def tokenize(source: str) -> list[str]:
    """
    Break *source* into a list of token strings.

    Parentheses become their own tokens; everything else is split on
    whitespace.

    >>> tokenize("(+ 1 2)")
    ['(', '+', '1', '2', ')']

    >>> tokenize("(define x 10)")
    ['(', 'define', 'x', '10', ')']
    """
    return source.replace("(", " ( ").replace(")", " ) ").split()


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PARSER
#
# Converts a flat list of token strings into a nested Python structure:
#
#   ['(', '+', '1', '(', '*', '2', '3', ')', ')']
#     → ['+', 1, ['*', 2, 3]]
#
# The parser has three parts:
#   • parse()             — entry point: tokenize, then read
#   • read_from_tokens()  — recursive descent over the token list
#   • atom()              — convert a single token to int, float, or Symbol
#
# When we see '(' we start collecting items into a list until we hit ')'.
# Each item is itself parsed recursively, so nested lists fall out naturally.
# ═══════════════════════════════════════════════════════════════════════════════

def parse(source: str) -> Exp:
    """
    Parse a Scheme expression from a source string.

    >>> parse("42")
    42
    >>> parse("hello")
    'hello'
    >>> parse("(+ 1 2)")
    ['+', 1, 2]
    >>> parse("(+ 1 (* 2 3))")
    ['+', 1, ['*', 2, 3]]
    """
    return read_from_tokens(tokenize(source))


def read_from_tokens(tokens: list[str]) -> Exp:
    """
    Read one expression from the front of *tokens* (mutates the list).

    Raises:
        SyntaxError: On empty input or unmatched parentheses.
    """
    if len(tokens) == 0:
        raise SyntaxError("unexpected EOF while reading")
    token = tokens.pop(0)

    if token == "(":
        # Build a list of sub-expressions until we hit ')'
        items: list = []
        while tokens[0] != ")":
            items.append(read_from_tokens(tokens))
            if len(tokens) == 0:
                raise SyntaxError("unexpected EOF — missing closing ')'")
        tokens.pop(0)  # discard the ')'
        return items
    elif token == ")":
        raise SyntaxError("unexpected ')'")
    else:
        return atom(token)


def atom(token: str) -> Atom:
    """
    Convert a single token string to the appropriate Python type.

    Numbers become int or float; everything else becomes a Symbol (str).

    >>> atom("42")
    42
    >>> atom("3.14")
    3.14
    >>> atom("hello")
    'hello'
    """
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return Symbol(token)


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT
#
# An environment maps variable names to their values.  Environments chain
# together for lexical scoping: each environment has an optional *outer*
# environment.  When looking up a variable, we search outward through the
# chain until we find it.
#
#   ┌───────────────────────────┐
#   │  Global env               │   (+ - * / pi ...)
#   │                           │
#   │  ┌────────────────────┐   │
#   │  │  Function env      │   │   (x = 5, y = 10)
#   │  │                    │   │
#   │  │  ┌─────────────┐   │   │
#   │  │  │  Inner env   │   │   │   (z = 3)
#   │  │  │  find("x")───┼───┘   │   → searches up to function env
#   │  │  └─────────────┘   │   │
#   │  └────────────────────┘   │
#   └───────────────────────────┘
# ═══════════════════════════════════════════════════════════════════════════════

class Env(dict):
    """
    An environment: a dict of ``{'var': val}`` pairs, with an outer Env.

    When a variable isn't found locally, ``find()`` walks up the chain
    of outer environments — this is how lexical scoping works.
    """

    def __init__(self, params=(), args=(), outer=None):
        super().__init__()
        self.update(zip(params, args))
        self.outer = outer

    def find(self, name: str) -> Env:
        """
        Return the innermost Env in which *name* appears.

        >>> env = Env(('x',), (10,), outer=Env(('y',), (20,)))
        >>> env.find('x')['x']
        10
        >>> env.find('y')['y']
        20

        Raises:
            LookupError: If *name* is not found in any enclosing scope.
        """
        if name in self:
            return self
        if self.outer is None:
            raise LookupError(f"undefined symbol: {name!r}")
        return self.outer.find(name)


# ═══════════════════════════════════════════════════════════════════════════════
# STANDARD ENVIRONMENT
#
# The default global environment pre-loaded with Scheme's standard procedures.
# These are just ordinary Python functions and values — the interpreter
# doesn't need to know they're "built-in".
#
# Categories:
#   • Arithmetic:    + - * / abs expt round min max
#   • Comparison:    > < >= <= =
#   • List ops:      car cdr cons append list length map
#   • Type tests:    number? symbol? list? null? procedure?
#   • Logic:         not eq? equal?
#   • Control:       begin apply
#   • I/O:           print
#   • Math:          pi, e, sqrt, sin, cos, ... (from Python's math module)
# ═══════════════════════════════════════════════════════════════════════════════

def standard_env() -> Env:
    """
    Create an environment with Scheme standard procedures.

    >>> env = standard_env()
    >>> env['+']( 1, 2)
    3
    >>> env['car']([1, 2, 3])
    1
    >>> env['pi']  # doctest: +ELLIPSIS
    3.14159...
    """
    env = Env()
    env.update(vars(math))  # sin, cos, sqrt, pi, e, ...
    env.update({
        # ── Arithmetic ────────────────────────────────────────────────
        "+": op.add,
        "-": lambda *args: -args[0] if len(args) == 1 else args[0] - args[1],
        "*": op.mul,
        "/": op.truediv,
        "abs": abs,
        "expt": pow,
        "round": round,
        "min": min,
        "max": max,

        # ── Comparison ────────────────────────────────────────────────
        ">": op.gt,
        "<": op.lt,
        ">=": op.ge,
        "<=": op.le,
        "=": op.eq,

        # ── List operations ───────────────────────────────────────────
        "car": lambda x: x[0],
        "cdr": lambda x: x[1:],
        "cons": lambda x, y: [x] + y,
        "append": op.add,
        "list": lambda *x: list(x),
        "length": len,
        "map": lambda f, xs: list(map(f, xs)),

        # ── Type predicates ───────────────────────────────────────────
        "number?": lambda x: isinstance(x, Number),
        "symbol?": lambda x: isinstance(x, Symbol) and not isinstance(x, bool),
        "list?": lambda x: isinstance(x, list),
        "null?": lambda x: x == [],
        "procedure?": callable,

        # ── Logic ─────────────────────────────────────────────────────
        "not": op.not_,
        "eq?": op.is_,
        "equal?": op.eq,

        # ── Control ───────────────────────────────────────────────────
        "begin": lambda *x: x[-1],
        "apply": lambda proc, args: proc(*args),

        # ── I/O ───────────────────────────────────────────────────────
        "print": print,

        # ── Boolean constants ─────────────────────────────────────────
        "#t": True,
        "#f": False,
    })
    return env


# ═══════════════════════════════════════════════════════════════════════════════
# PROCEDURE
#
# A user-defined Scheme procedure (created by ``lambda``).  It captures three
# things at creation time:
#
#   1. Parameter names  — e.g. (x y)
#   2. Body expression  — the code to evaluate when called
#   3. Defining env     — the environment where the lambda was created
#
# When called, it creates a *new* environment that binds the parameter names
# to the argument values, with the defining environment as its outer scope.
# This is what makes closures work — the body can reference variables from
# the scope where the lambda was defined, not where it's called.
# ═══════════════════════════════════════════════════════════════════════════════

class Procedure:
    """
    A user-defined Scheme procedure.

    >>> import math
    >>> env = standard_env()
    >>> square = Procedure(['x'], ['*', 'x', 'x'], env)
    >>> square(5)
    25
    """

    def __init__(self, params: list, body: Exp, env: Env):
        self.params = params
        self.body = body
        self.env = env

    def __call__(self, *args):
        child_env = Env(self.params, args, outer=self.env)
        return leval(self.body, child_env)

    def __repr__(self):
        return f"Procedure(params={self.params!r})"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — EVAL
#
# The core of the interpreter.  Walks the parsed AST and evaluates it in
# the given environment.  Handles eight expression types:
#
#   Expression              Example              Action
#   ──────────              ───────              ──────
#   symbol                  x                    Look up in env
#   number (constant)       42                   Return as-is
#   (quote exp)             (quote (1 2 3))      Return exp unevaluated
#   (if test yes no)        (if (> x 0) x 0)     Eval test, then branch
#   (define sym exp)        (define r 10)         Bind sym = eval(exp) in env
#   (set! sym exp)          (set! r 20)          Update existing binding
#   (lambda (p...) body)    (lambda (x) (* x x)) Create a Procedure
#   (proc arg...)           (+ 1 2)              Eval proc & args, apply
# ═══════════════════════════════════════════════════════════════════════════════

def leval(x: Exp, env: Env) -> Exp:
    """
    Evaluate expression *x* in environment *env*.

    Named ``leval`` to avoid shadowing Python's built-in ``eval``.

    >>> env = standard_env()
    >>> leval(3, env)
    3
    >>> leval('+', env)  # doctest: +ELLIPSIS
    <built-in function add>
    >>> leval(['+', 1, 2], env)
    3
    >>> leval(['if', ['>', 10, 5], 'yes', 'no'], env)
    'yes'
    """
    # ── Symbol — variable reference ───────────────────────────────────
    if isinstance(x, Symbol):
        return env.find(x)[x]

    # ── Constant — number, bool, etc. ─────────────────────────────────
    elif not isinstance(x, list):
        return x

    # ── Special forms ─────────────────────────────────────────────────
    head, *args = x

    if head == "quote":
        # (quote exp) → return exp without evaluating it
        return args[0]

    elif head == "if":
        # (if test consequent alternative)
        test, consequent, alternative = args
        branch = consequent if leval(test, env) else alternative
        return leval(branch, env)

    elif head == "define":
        # (define symbol exp) → bind symbol in current env
        symbol, exp = args
        env[symbol] = leval(exp, env)

    elif head == "set!":
        # (set! symbol exp) → update existing binding
        symbol, exp = args
        env.find(symbol)[symbol] = leval(exp, env)

    elif head == "lambda":
        # (lambda (params...) body) → create Procedure
        # If multiple body expressions, wrap in implicit (begin ...)
        params = args[0]
        body = args[1] if len(args) == 2 else ["begin"] + args[1:]
        return Procedure(params, body, env)

    else:
        # ── Procedure call ────────────────────────────────────────────
        # Evaluate the operator and all operands, then apply
        proc = leval(head, env)
        vals = [leval(arg, env) for arg in args]
        return proc(*vals)


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTING
#
# Converts Python values back into Scheme-readable strings.
# ═══════════════════════════════════════════════════════════════════════════════

def schemestr(exp: Exp) -> str:
    """
    Convert a Python object back into a Scheme-readable string.

    >>> schemestr(42)
    '42'
    >>> schemestr(3.14)
    '3.14'
    >>> schemestr([1, 2, 3])
    '(1 2 3)'
    >>> schemestr([1, [2, 3]])
    '(1 (2 3))'
    >>> schemestr(True)
    '#t'
    >>> schemestr(False)
    '#f'
    """
    if isinstance(exp, bool):
        return "#t" if exp else "#f"
    elif isinstance(exp, list):
        return "(" + " ".join(map(schemestr, exp)) + ")"
    else:
        return str(exp)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERPRETER — the full pipeline
#
# This is the main entry point.  It chains the two phases together:
#   parse → eval → format
#
# Each call gets a fresh environment so expressions are evaluated in
# isolation — handy for testing and one-shot use.
# ═══════════════════════════════════════════════════════════════════════════════

def interpreter(source: str) -> str:
    """
    Parse and evaluate a Scheme expression, returning the result as a string.

    >>> interpreter("(+ 1 2)")
    '3'
    >>> interpreter("(* 2 (+ 3 4))")
    '14'
    >>> interpreter("(if (> 10 5) 1 0)")
    '1'
    >>> interpreter("(quote (1 2 3))")
    '(1 2 3)'
    >>> interpreter("((lambda (x) (* x x)) 5)")
    '25'
    """
    env = standard_env()
    result = leval(parse(source), env)
    if result is None:
        return ""
    return schemestr(result)


def run(source: str, env: Env | None = None) -> Exp:
    """
    Parse and evaluate *source* in the given environment.

    Unlike ``interpreter()``, this returns the raw Python value and reuses
    an existing environment — useful for multi-expression programs.

    >>> env = standard_env()
    >>> run("(define x 10)", env)
    >>> run("x", env)
    10
    >>> run("(+ x 5)", env)
    15
    """
    if env is None:
        env = standard_env()
    return leval(parse(source), env)


# ═══════════════════════════════════════════════════════════════════════════════
# REPL — Read-Eval-Print Loop
#
# An interactive prompt for typing Scheme expressions and seeing results.
# Type Ctrl-C or Ctrl-D to exit.
# ═══════════════════════════════════════════════════════════════════════════════

def repl(prompt: str = "lispy> ") -> None:
    """
    Start an interactive read-eval-print loop.

    Uses a persistent environment so ``define`` persists across inputs.
    """
    env = standard_env()
    while True:
        try:
            source = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not source.strip():
            continue

        try:
            result = leval(parse(source), env)
            if result is not None:
                print(schemestr(result))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — interactive demo
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    examples = [
        # ── Basic arithmetic ──────────────────────────────────────────
        ("(+ 1 2)", "Simple addition"),
        ("(* 2 (+ 3 4))", "Nested arithmetic"),
        ("(- 10 (* 2 3))", "Subtraction with nested multiply"),

        # ── Comparisons and conditionals ──────────────────────────────
        ("(> 10 5)", "Greater-than comparison"),
        ("(if (> 10 5) 1 0)", "If-then-else"),

        # ── Lambda (anonymous function) ───────────────────────────────
        ("((lambda (x) (* x x)) 5)", "Inline lambda — square of 5"),

        # ── Quote ─────────────────────────────────────────────────────
        ("(quote (1 2 3))", "Quoted list"),

        # ── List operations ───────────────────────────────────────────
        ("(list 1 2 3)", "Build a list"),
        ("(car (list 1 2 3))", "First element"),
        ("(cdr (list 1 2 3))", "Rest of list"),

        # ── Define and use ────────────────────────────────────────────
        ("(begin (define r 10) (* pi (* r r)))",
         "Define r, then compute circle area"),

        # ── Recursive function ────────────────────────────────────────
        ("(begin (define fact (lambda (n) (if (<= n 1) 1 (* n (fact (- n 1)))))) (fact 10))",
         "Factorial of 10"),

        # ── Higher-order function ─────────────────────────────────────
        ("(map (lambda (x) (* x x)) (list 1 2 3 4 5))",
         "Map square over a list"),

        # ── Closures ─────────────────────────────────────────────────
        ("(begin (define make-adder (lambda (n) (lambda (x) (+ n x)))) (define add5 (make-adder 5)) (add5 10))",
         "Closure — make-adder creates add5"),
    ]

    print("Lisp Interpreter — Python Edition")
    print("=" * 40)
    print()

    for source, description in examples:
        result = interpreter(source)
        print(f"  {description}:")
        print(f"    input:  {source}")
        print(f"    output: {result}")
        print()
