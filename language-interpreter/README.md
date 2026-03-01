# Language Interpreter: Under the Hood

How does a programming language understand and execute your code? This module walks through a Lisp interpreter written in Python, covering parsing, environments, and evaluation.

## What it Does

This interpreter evaluates a subset of **Scheme** (a Lisp dialect) directly — no compilation step, just parse and execute:

```
SOURCE (Scheme)                      RESULT
───────────────                      ──────
(+ 1 2)                         →    3
(* 2 (+ 3 4))                   →    14
(if (> 10 5) "yes" "no")        →    "yes"
((lambda (x) (* x x)) 5)        →    25
```

That's the core difference between a **compiler** and an **interpreter**: a compiler translates code into another language, while an interpreter *executes* it directly by walking the syntax tree.

## The Two Phases

Every interpreter follows the same basic pipeline:

```
Source Code  →  Parse  →  AST  →  Eval  →  Result
                Phase 1          Phase 2
```

### Phase 1: Parse (Tokenize + Build AST)

The parser converts source text into a nested Python data structure. It uses the simplest possible tokenizer — pad parentheses with spaces, then split:

```
Input:  "(+ 1 (* 2 3))"

Tokenize:  ['(', '+', '1', '(', '*', '2', '3', ')', ')']

Parse:     ['+', 1, ['*', 2, 3]]
```

No special AST node classes needed — the AST is just nested Python lists, integers, floats, and strings. This is one of the elegant insights of Lisp: the code *is* the data structure.

### Phase 2: Eval (Evaluate the AST)

The evaluator walks the AST and handles eight expression types:

| Expression | Example | Action |
|-----------|---------|--------|
| symbol | `x` | Look up in environment |
| constant | `42` | Return as-is |
| `(quote exp)` | `(quote (1 2 3))` | Return exp unevaluated |
| `(if test yes no)` | `(if (> x 0) x 0)` | Eval test, then branch |
| `(define sym exp)` | `(define r 10)` | Bind sym = eval(exp) |
| `(set! sym exp)` | `(set! r 20)` | Update existing binding |
| `(lambda (p...) body)` | `(lambda (x) (* x x))` | Create a procedure |
| `(proc arg...)` | `(+ 1 2)` | Eval proc & args, apply |

### Environments and Closures

Variables live in **environments** — nested dictionaries that chain together for lexical scoping. When a `lambda` is created, it captures its defining environment. When called, a new environment is created that links back to the defining scope. This is how closures work:

```
(define make-adder (lambda (n) (lambda (x) (+ n x))))
(define add5 (make-adder 5))
(add5 10)  →  15
```

## Running It

```bash
cd language-interpreter
python lisp-interpreter-norvig.py
```

Output:

```
Lisp Interpreter — Python Edition
========================================

  Simple addition:
    input:  (+ 1 2)
    output: 3

  Nested arithmetic:
    input:  (* 2 (+ 3 4))
    output: 14

  Inline lambda — square of 5:
    input:  ((lambda (x) (* x x)) 5)
    output: 25

  Define r, then compute circle area:
    input:  (begin (define r 10) (* pi (* r r)))
    output: 314.1592653589793

  Factorial of 10:
    input:  (begin (define fact (lambda (n) (if (<= n 1) 1 (* n (fact (- n 1)))))) (fact 10))
    output: 3628800

  Closure — make-adder creates add5:
    input:  (begin (define make-adder (lambda (n) (lambda (x) (+ n x)))) (define add5 (make-adder 5)) (add5 10))
    output: 15
```

## Running Tests

```bash
cd language-interpreter
python -m pytest test_interpreter.py -v
```

The test suite covers each component in isolation plus end-to-end interpreter tests — 166 test cases covering tokenizing, parsing, environments, evaluation, closures, recursion, and error handling.

## Implementation: `lisp-interpreter-norvig.py`

### References

- [How to Write a (Lisp) Interpreter (in Python)](https://www.norvig.com/lispy.html) by Peter Norvig — the original tutorial this implementation is based on
- [Crafting Interpreters](https://craftinginterpreters.com/) by Robert Nystrom — the comprehensive guide to building interpreters from scratch
- [Structure and Interpretation of Computer Programs](https://mitpress.mit.edu/sites/default/files/sicp/index.html) — the classic CS textbook that teaches programming through a Scheme interpreter
