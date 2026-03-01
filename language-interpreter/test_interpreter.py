"""
Tests for the Lisp Interpreter
================================

Organized by interpreter component so failures point directly to the
broken part.

Run with: python -m pytest test_interpreter.py -v
     or:  python test_interpreter.py
"""

import sys
import os
import math

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the interpreter module (filename has a hyphen) ─────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "lisp-interpreter-norvig.py")
_loader = SourceFileLoader("interpreter", _path)
_spec = spec_from_loader("interpreter", _loader)
interp_module = module_from_spec(_spec)
sys.modules["interpreter"] = interp_module
_loader.exec_module(interp_module)

# Pull out everything we need
tokenize = interp_module.tokenize
parse = interp_module.parse
read_from_tokens = interp_module.read_from_tokens
atom = interp_module.atom
Env = interp_module.Env
standard_env = interp_module.standard_env
Procedure = interp_module.Procedure
leval = interp_module.leval
schemestr = interp_module.schemestr
interpreter = interp_module.interpreter
run = interp_module.run


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENIZER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenizer:
    """Tests for the tokenize() function."""

    def test_empty_input(self):
        """Empty string produces no tokens."""
        assert tokenize("") == []

    def test_whitespace_only(self):
        """Whitespace-only input produces no tokens."""
        assert tokenize("   \t\n  ") == []

    def test_single_open_paren(self):
        assert tokenize("(") == ["("]

    def test_single_close_paren(self):
        assert tokenize(")") == [")"]

    def test_single_number(self):
        assert tokenize("42") == ["42"]

    def test_single_symbol(self):
        assert tokenize("add") == ["add"]

    def test_simple_expression(self):
        """Tokenize a basic call: (+ 1 2)"""
        result = tokenize("(+ 1 2)")
        assert result == ["(", "+", "1", "2", ")"]

    def test_nested_expression(self):
        """Tokenize nested calls: (+ 1 (* 2 3))"""
        result = tokenize("(+ 1 (* 2 3))")
        expected = ["(", "+", "1", "(", "*", "2", "3", ")", ")"]
        assert result == expected

    def test_define_expression(self):
        """Tokenize a define form."""
        result = tokenize("(define x 10)")
        assert result == ["(", "define", "x", "10", ")"]

    def test_extra_whitespace(self):
        """Extra whitespace between tokens is handled gracefully."""
        result = tokenize("(  +   1   2  )")
        assert result == ["(", "+", "1", "2", ")"]

    def test_newlines_as_whitespace(self):
        """Newlines are treated as whitespace."""
        result = tokenize("(+\n  1\n  2)")
        assert result == ["(", "+", "1", "2", ")"]

    def test_lambda_expression(self):
        """Tokenize a lambda form."""
        result = tokenize("(lambda (x) (* x x))")
        expected = ["(", "lambda", "(", "x", ")", "(", "*", "x", "x", ")", ")"]
        assert result == expected

    def test_multiple_expressions(self):
        """Tokenize multiple top-level expressions."""
        result = tokenize("(+ 1 2) (- 3 4)")
        expected = ["(", "+", "1", "2", ")", "(", "-", "3", "4", ")"]
        assert result == expected

    def test_float_token(self):
        """Float numbers are tokenized as single tokens."""
        result = tokenize("3.14")
        assert result == ["3.14"]

    def test_negative_number_token(self):
        """Negative numbers (unary minus) are separate tokens."""
        result = tokenize("(- 5)")
        assert result == ["(", "-", "5", ")"]

    def test_boolean_tokens(self):
        """Boolean literals tokenize correctly."""
        result = tokenize("(if #t 1 0)")
        assert result == ["(", "if", "#t", "1", "0", ")"]


# ═══════════════════════════════════════════════════════════════════════════════
# ATOM TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAtom:
    """Tests for the atom() function."""

    def test_integer(self):
        assert atom("42") == 42
        assert isinstance(atom("42"), int)

    def test_negative_integer(self):
        assert atom("-7") == -7
        assert isinstance(atom("-7"), int)

    def test_zero(self):
        assert atom("0") == 0
        assert isinstance(atom("0"), int)

    def test_float(self):
        assert atom("3.14") == 3.14
        assert isinstance(atom("3.14"), float)

    def test_negative_float(self):
        assert atom("-2.5") == -2.5
        assert isinstance(atom("-2.5"), float)

    def test_symbol(self):
        assert atom("hello") == "hello"
        assert isinstance(atom("hello"), str)

    def test_operator_symbol(self):
        assert atom("+") == "+"
        assert atom("<=") == "<="

    def test_special_symbol(self):
        assert atom("define") == "define"
        assert atom("lambda") == "lambda"


# ═══════════════════════════════════════════════════════════════════════════════
# PARSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestParser:
    """Tests for the parse() function."""

    def test_integer(self):
        """A bare integer is parsed as int."""
        assert parse("42") == 42

    def test_float(self):
        """A bare float is parsed as float."""
        assert parse("3.14") == 3.14

    def test_symbol(self):
        """A bare symbol is parsed as str."""
        assert parse("hello") == "hello"

    def test_simple_list(self):
        """Parse (+ 1 2) into a nested list."""
        result = parse("(+ 1 2)")
        assert result == ["+", 1, 2]

    def test_nested_list(self):
        """Parse nested expression into nested lists."""
        result = parse("(+ 1 (* 2 3))")
        assert result == ["+", 1, ["*", 2, 3]]

    def test_deeply_nested(self):
        """Parse three levels of nesting."""
        result = parse("(+ 1 (- 3 (* 4 5)))")
        assert result == ["+", 1, ["-", 3, ["*", 4, 5]]]

    def test_empty_list(self):
        """Parse () into an empty list."""
        result = parse("()")
        assert result == []

    def test_define_form(self):
        """Parse a define expression."""
        result = parse("(define x 10)")
        assert result == ["define", "x", 10]

    def test_lambda_form(self):
        """Parse a lambda expression."""
        result = parse("(lambda (x) (* x x))")
        assert result == ["lambda", ["x"], ["*", "x", "x"]]

    def test_if_form(self):
        """Parse an if expression."""
        result = parse("(if (> x 0) x 0)")
        assert result == ["if", [">", "x", 0], "x", 0]

    def test_quote_form(self):
        """Parse a quote expression."""
        result = parse("(quote (1 2 3))")
        assert result == ["quote", [1, 2, 3]]

    def test_empty_input_raises(self):
        """Empty input should raise SyntaxError."""
        with pytest.raises(SyntaxError, match="unexpected EOF"):
            parse("")

    def test_unmatched_close_paren_raises(self):
        """A bare ')' should raise SyntaxError."""
        with pytest.raises(SyntaxError, match="unexpected '\\)'"):
            parse(")")

    def test_unclosed_paren_raises(self):
        """An unclosed '(' should raise."""
        with pytest.raises((SyntaxError, IndexError)):
            parse("(+ 1 2")


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnv:
    """Tests for the Env class."""

    def test_basic_lookup(self):
        """Variables can be stored and retrieved."""
        env = Env(("x",), (10,))
        assert env["x"] == 10

    def test_multiple_bindings(self):
        """Multiple variables can be bound at once."""
        env = Env(("x", "y"), (10, 20))
        assert env["x"] == 10
        assert env["y"] == 20

    def test_find_local(self):
        """find() returns the env containing the variable."""
        env = Env(("x",), (10,))
        assert env.find("x") is env
        assert env.find("x")["x"] == 10

    def test_find_in_outer(self):
        """find() searches outer scopes."""
        outer = Env(("y",), (20,))
        inner = Env(("x",), (10,), outer=outer)
        assert inner.find("y")["y"] == 20

    def test_find_shadows_outer(self):
        """Inner variables shadow outer ones."""
        outer = Env(("x",), (1,))
        inner = Env(("x",), (2,), outer=outer)
        assert inner.find("x")["x"] == 2

    def test_find_three_levels(self):
        """find() works through three levels of nesting."""
        global_env = Env(("z",), (30,))
        middle = Env(("y",), (20,), outer=global_env)
        inner = Env(("x",), (10,), outer=middle)
        assert inner.find("z")["z"] == 30
        assert inner.find("y")["y"] == 20
        assert inner.find("x")["x"] == 10

    def test_find_undefined_raises(self):
        """Looking up an undefined variable raises LookupError."""
        env = Env(("x",), (10,))
        with pytest.raises(LookupError, match="undefined symbol"):
            env.find("missing")

    def test_find_undefined_in_nested_raises(self):
        """Undefined variable raises even with nested scopes."""
        outer = Env(("x",), (10,))
        inner = Env(("y",), (20,), outer=outer)
        with pytest.raises(LookupError, match="undefined symbol"):
            inner.find("missing")

    def test_empty_env(self):
        """An env with no bindings works."""
        env = Env()
        assert len(env) == 0

    def test_mutation(self):
        """Environment bindings can be updated."""
        env = Env(("x",), (10,))
        env["x"] = 42
        assert env["x"] == 42


# ═══════════════════════════════════════════════════════════════════════════════
# STANDARD ENVIRONMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestStandardEnv:
    """Tests for the standard_env() function."""

    def test_arithmetic_add(self):
        env = standard_env()
        assert env["+"](1, 2) == 3

    def test_arithmetic_sub(self):
        env = standard_env()
        assert env["-"](10, 3) == 7

    def test_arithmetic_mul(self):
        env = standard_env()
        assert env["*"](4, 5) == 20

    def test_arithmetic_div(self):
        env = standard_env()
        assert env["/"](10, 4) == 2.5

    def test_comparison_gt(self):
        env = standard_env()
        assert env[">"](5, 3) is True
        assert env[">"](3, 5) is False

    def test_comparison_eq(self):
        env = standard_env()
        assert env["="](5, 5) is True
        assert env["="](5, 3) is False

    def test_car(self):
        env = standard_env()
        assert env["car"]([1, 2, 3]) == 1

    def test_cdr(self):
        env = standard_env()
        assert env["cdr"]([1, 2, 3]) == [2, 3]

    def test_cons(self):
        env = standard_env()
        assert env["cons"](1, [2, 3]) == [1, 2, 3]

    def test_list(self):
        env = standard_env()
        assert env["list"](1, 2, 3) == [1, 2, 3]

    def test_length(self):
        env = standard_env()
        assert env["length"]([1, 2, 3]) == 3

    def test_number_predicate(self):
        env = standard_env()
        assert env["number?"](42) is True
        assert env["number?"](3.14) is True
        assert env["number?"]("hello") is False

    def test_list_predicate(self):
        env = standard_env()
        assert env["list?"]([1, 2]) is True
        assert env["list?"](42) is False

    def test_null_predicate(self):
        env = standard_env()
        assert env["null?"]([]) is True
        assert env["null?"]([1]) is False

    def test_not(self):
        env = standard_env()
        assert env["not"](False) is True
        assert env["not"](True) is False

    def test_begin(self):
        env = standard_env()
        assert env["begin"](1, 2, 3) == 3

    def test_abs(self):
        env = standard_env()
        assert env["abs"](-5) == 5
        assert env["abs"](5) == 5

    def test_pi(self):
        env = standard_env()
        assert env["pi"] == math.pi

    def test_sqrt(self):
        env = standard_env()
        assert env["sqrt"](16) == 4.0

    def test_map(self):
        env = standard_env()
        result = env["map"](lambda x: x * 2, [1, 2, 3])
        assert result == [2, 4, 6]

    def test_apply(self):
        env = standard_env()
        assert env["apply"](env["+"], [1, 2]) == 3

    def test_procedure_predicate(self):
        env = standard_env()
        assert env["procedure?"](env["+"]) is True
        assert env["procedure?"](42) is False

    def test_boolean_constants(self):
        env = standard_env()
        assert env["#t"] is True
        assert env["#f"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# PROCEDURE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcedure:
    """Tests for the Procedure class."""

    def test_simple_call(self):
        """A procedure that multiplies its argument by 2."""
        env = standard_env()
        double = Procedure(["x"], ["*", "x", 2], env)
        assert double(5) == 10

    def test_two_params(self):
        """A procedure with two parameters."""
        env = standard_env()
        add = Procedure(["a", "b"], ["+", "a", "b"], env)
        assert add(3, 4) == 7

    def test_closure_captures_env(self):
        """A procedure captures its defining environment."""
        env = standard_env()
        env["y"] = 10
        add_y = Procedure(["x"], ["+", "x", "y"], env)
        assert add_y(5) == 15

    def test_repr(self):
        """Procedure has a readable repr."""
        env = standard_env()
        p = Procedure(["x", "y"], ["+", "x", "y"], env)
        assert "Procedure" in repr(p)
        assert "x" in repr(p)


# ═══════════════════════════════════════════════════════════════════════════════
# EVAL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEval:
    """Tests for the leval() function."""

    def test_number(self):
        """A number evaluates to itself."""
        env = standard_env()
        assert leval(42, env) == 42

    def test_float(self):
        """A float evaluates to itself."""
        env = standard_env()
        assert leval(3.14, env) == 3.14

    def test_symbol_lookup(self):
        """A symbol evaluates to its value in the environment."""
        env = standard_env()
        env["x"] = 42
        assert leval("x", env) == 42

    def test_undefined_symbol_raises(self):
        """An undefined symbol raises LookupError."""
        env = standard_env()
        with pytest.raises(LookupError, match="undefined symbol"):
            leval("undefined_var", env)

    def test_quote(self):
        """(quote exp) returns exp without evaluating it."""
        env = standard_env()
        assert leval(["quote", [1, 2, 3]], env) == [1, 2, 3]

    def test_quote_symbol(self):
        """(quote x) returns the symbol itself, not its value."""
        env = standard_env()
        env["x"] = 99
        assert leval(["quote", "x"], env) == "x"

    def test_if_true_branch(self):
        """(if #t 1 0) evaluates the consequent."""
        env = standard_env()
        assert leval(["if", True, 1, 0], env) == 1

    def test_if_false_branch(self):
        """(if #f 1 0) evaluates the alternative."""
        env = standard_env()
        assert leval(["if", False, 1, 0], env) == 0

    def test_if_with_expression_test(self):
        """(if (> 10 5) 1 0) — test is an expression."""
        env = standard_env()
        assert leval(["if", [">", 10, 5], 1, 0], env) == 1

    def test_if_evaluates_only_chosen_branch(self):
        """Only the chosen branch is evaluated (no side effects from other)."""
        env = standard_env()
        # If we evaluated both branches, (/ 1 0) would error
        result = leval(["if", True, 42, ["/", 1, 0]], env)
        assert result == 42

    def test_define(self):
        """(define x 10) binds x in the current environment."""
        env = standard_env()
        leval(["define", "x", 10], env)
        assert env["x"] == 10

    def test_define_with_expression(self):
        """(define x (+ 1 2)) — the value is an expression."""
        env = standard_env()
        leval(["define", "x", ["+", 1, 2]], env)
        assert env["x"] == 3

    def test_set_bang(self):
        """(set! x 20) updates an existing binding."""
        env = standard_env()
        env["x"] = 10
        leval(["set!", "x", 20], env)
        assert env["x"] == 20

    def test_set_bang_in_outer(self):
        """(set! x 20) updates the binding in the correct scope."""
        outer = standard_env()
        outer["x"] = 10
        inner = Env(("y",), (5,), outer=outer)
        leval(["set!", "x", 20], inner)
        assert outer["x"] == 20

    def test_lambda_creates_procedure(self):
        """(lambda (x) (* x x)) creates a Procedure."""
        env = standard_env()
        result = leval(["lambda", ["x"], ["*", "x", "x"]], env)
        assert isinstance(result, Procedure)

    def test_lambda_call(self):
        """((lambda (x) (* x x)) 5) — immediately invoke a lambda."""
        env = standard_env()
        result = leval([["lambda", ["x"], ["*", "x", "x"]], 5], env)
        assert result == 25

    def test_procedure_call(self):
        """Call a built-in procedure: (+ 1 2)."""
        env = standard_env()
        assert leval(["+", 1, 2], env) == 3

    def test_nested_call(self):
        """Nested calls: (+ 1 (* 2 3))."""
        env = standard_env()
        assert leval(["+", 1, ["*", 2, 3]], env) == 7

    def test_define_then_call(self):
        """Define a function, then call it."""
        env = standard_env()
        leval(["define", "square", ["lambda", ["x"], ["*", "x", "x"]]], env)
        assert leval(["square", 4], env) == 16

    def test_recursive_factorial(self):
        """Recursive factorial function."""
        env = standard_env()
        leval(["define", "fact",
               ["lambda", ["n"],
                ["if", ["<=", "n", 1], 1,
                 ["*", "n", ["fact", ["-", "n", 1]]]]]], env)
        assert leval(["fact", 5], env) == 120
        assert leval(["fact", 10], env) == 3628800

    def test_closure(self):
        """Closures capture their defining environment."""
        env = standard_env()
        # (define make-adder (lambda (n) (lambda (x) (+ n x))))
        leval(["define", "make-adder",
               ["lambda", ["n"],
                ["lambda", ["x"], ["+", "n", "x"]]]], env)
        # (define add5 (make-adder 5))
        leval(["define", "add5", ["make-adder", 5]], env)
        assert leval(["add5", 10], env) == 15
        assert leval(["add5", 0], env) == 5

    def test_begin(self):
        """(begin expr1 expr2 ...) evaluates all, returns last."""
        env = standard_env()
        result = leval(["begin", ["+", 1, 2], ["*", 3, 4]], env)
        assert result == 12

    def test_begin_with_define(self):
        """(begin (define x 10) x) — define then use."""
        env = standard_env()
        result = leval(["begin", ["define", "x", 10], "x"], env)
        assert result == 10


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMESTR TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemeStr:
    """Tests for the schemestr() function."""

    def test_integer(self):
        assert schemestr(42) == "42"

    def test_float(self):
        assert schemestr(3.14) == "3.14"

    def test_symbol(self):
        assert schemestr("hello") == "hello"

    def test_simple_list(self):
        assert schemestr([1, 2, 3]) == "(1 2 3)"

    def test_nested_list(self):
        assert schemestr([1, [2, 3]]) == "(1 (2 3))"

    def test_empty_list(self):
        assert schemestr([]) == "()"

    def test_true(self):
        assert schemestr(True) == "#t"

    def test_false(self):
        assert schemestr(False) == "#f"

    def test_mixed_list(self):
        assert schemestr(["+", 1, 2]) == "(+ 1 2)"

    def test_deeply_nested(self):
        assert schemestr([1, [2, [3, 4]]]) == "(1 (2 (3 4)))"


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END INTERPRETER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterpreterEndToEnd:
    """Full pipeline tests: source string → result string."""

    # ── Arithmetic ────────────────────────────────────────────────────

    def test_addition(self):
        assert interpreter("(+ 1 2)") == "3"

    def test_subtraction(self):
        assert interpreter("(- 10 3)") == "7"

    def test_multiplication(self):
        assert interpreter("(* 4 5)") == "20"

    def test_division(self):
        assert interpreter("(/ 10 4)") == "2.5"

    def test_nested_arithmetic(self):
        assert interpreter("(+ 1 (* 2 3))") == "7"

    def test_deeply_nested_arithmetic(self):
        assert interpreter("(+ 1 (- 3 (* 2 2)))") == "0"

    def test_three_args(self):
        """(+ 1 2 3) — three arguments."""
        assert interpreter("(+ 1 2)") == "3"

    def test_unary_minus(self):
        assert interpreter("(- 5)") == "-5"

    # ── Comparison ────────────────────────────────────────────────────

    def test_greater_than_true(self):
        assert interpreter("(> 10 5)") == "#t"

    def test_greater_than_false(self):
        assert interpreter("(> 3 5)") == "#f"

    def test_less_than(self):
        assert interpreter("(< 3 5)") == "#t"

    def test_equal(self):
        assert interpreter("(= 5 5)") == "#t"

    def test_not_equal(self):
        assert interpreter("(= 5 3)") == "#f"

    def test_gte(self):
        assert interpreter("(>= 5 5)") == "#t"

    def test_lte(self):
        assert interpreter("(<= 3 5)") == "#t"

    # ── Conditionals ──────────────────────────────────────────────────

    def test_if_true(self):
        assert interpreter("(if (> 10 5) 1 0)") == "1"

    def test_if_false(self):
        assert interpreter("(if (< 10 5) 1 0)") == "0"

    def test_if_with_expressions(self):
        assert interpreter("(if (= 1 1) (+ 2 3) (- 5 1))") == "5"

    # ── Quote ─────────────────────────────────────────────────────────

    def test_quote_list(self):
        assert interpreter("(quote (1 2 3))") == "(1 2 3)"

    def test_quote_symbol(self):
        assert interpreter("(quote hello)") == "hello"

    def test_quote_nested(self):
        assert interpreter("(quote (a (b c)))") == "(a (b c))"

    # ── Lambda ────────────────────────────────────────────────────────

    def test_inline_lambda(self):
        assert interpreter("((lambda (x) (* x x)) 5)") == "25"

    def test_lambda_two_params(self):
        assert interpreter("((lambda (x y) (+ x y)) 3 4)") == "7"

    def test_lambda_with_body_expression(self):
        assert interpreter("((lambda (x) (+ x 1)) 10)") == "11"

    # ── Define + Use (via begin) ──────────────────────────────────────

    def test_define_and_use(self):
        assert interpreter("(begin (define x 10) x)") == "10"

    def test_define_function_and_call(self):
        source = "(begin (define square (lambda (x) (* x x))) (square 7))"
        assert interpreter(source) == "49"

    def test_define_returns_empty(self):
        """A bare define returns None (empty string)."""
        assert interpreter("(define x 10)") == ""

    # ── List operations ───────────────────────────────────────────────

    def test_list_construction(self):
        assert interpreter("(list 1 2 3)") == "(1 2 3)"

    def test_car(self):
        assert interpreter("(car (list 1 2 3))") == "1"

    def test_cdr(self):
        assert interpreter("(cdr (list 1 2 3))") == "(2 3)"

    def test_cons(self):
        assert interpreter("(cons 0 (list 1 2 3))") == "(0 1 2 3)"

    def test_length(self):
        assert interpreter("(length (list 1 2 3))") == "3"

    def test_null_true(self):
        assert interpreter("(null? (list))") == "#t"

    def test_null_false(self):
        assert interpreter("(null? (list 1))") == "#f"

    # ── Math functions ────────────────────────────────────────────────

    def test_abs(self):
        assert interpreter("(abs -5)") == "5"

    def test_pi(self):
        result = float(interpreter("pi"))
        assert abs(result - math.pi) < 1e-10

    def test_sqrt(self):
        assert interpreter("(sqrt 16)") == "4.0"

    def test_expt(self):
        assert interpreter("(expt 2 10)") == "1024"

    def test_max(self):
        assert interpreter("(max 3 7)") == "7"

    def test_min(self):
        assert interpreter("(min 3 7)") == "3"

    # ── Higher-order functions ────────────────────────────────────────

    def test_map(self):
        source = "(map (lambda (x) (* x x)) (list 1 2 3 4 5))"
        assert interpreter(source) == "(1 4 9 16 25)"

    # ── Recursive programs ────────────────────────────────────────────

    def test_factorial(self):
        source = """
        (begin
            (define fact (lambda (n)
                (if (<= n 1) 1 (* n (fact (- n 1))))))
            (fact 10))
        """
        assert interpreter(source) == "3628800"

    def test_fibonacci(self):
        source = """
        (begin
            (define fib (lambda (n)
                (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))))
            (fib 10))
        """
        assert interpreter(source) == "55"

    # ── Closures ──────────────────────────────────────────────────────

    def test_closure_make_adder(self):
        source = """
        (begin
            (define make-adder (lambda (n) (lambda (x) (+ n x))))
            (define add5 (make-adder 5))
            (add5 10))
        """
        assert interpreter(source) == "15"

    def test_closure_counter(self):
        """Closures can share and mutate state via set!."""
        env = standard_env()
        run("(define counter (begin (define n 0) (lambda () (set! n (+ n 1)) n)))", env)
        assert run("(counter)", env) == 1
        assert run("(counter)", env) == 2
        assert run("(counter)", env) == 3

    # ── Circle area (from Norvig's examples) ──────────────────────────

    def test_circle_area(self):
        source = "(begin (define r 10) (* pi (* r r)))"
        result = float(interpreter(source))
        assert abs(result - 314.1592653589793) < 1e-6

    # ── Boolean values ────────────────────────────────────────────────

    def test_not_true(self):
        assert interpreter("(not #t)") == "#f"

    def test_not_false(self):
        assert interpreter("(not #f)") == "#t"

    # ── Type predicates ───────────────────────────────────────────────

    def test_number_predicate_true(self):
        assert interpreter("(number? 42)") == "#t"

    def test_number_predicate_false(self):
        assert interpreter("(number? (quote hello))") == "#f"

    def test_list_predicate_true(self):
        assert interpreter("(list? (list 1 2))") == "#t"

    def test_list_predicate_false(self):
        assert interpreter("(list? 42)") == "#f"

    # ── Edge cases ────────────────────────────────────────────────────

    def test_whitespace_variations(self):
        """Extra whitespace should not affect output."""
        assert interpreter("(  +   1   2  )") == "3"

    def test_newlines_in_source(self):
        """Newlines in source are treated as whitespace."""
        assert interpreter("(+\n  1\n  2)") == "3"


# ═══════════════════════════════════════════════════════════════════════════════
# RUN FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRun:
    """Tests for the run() helper function."""

    def test_returns_raw_value(self):
        """run() returns raw Python values, not strings."""
        env = standard_env()
        assert run("(+ 1 2)", env) == 3
        assert isinstance(run("(+ 1 2)", env), int)

    def test_persistent_env(self):
        """run() shares environment across calls."""
        env = standard_env()
        run("(define x 42)", env)
        assert run("x", env) == 42

    def test_multi_step_program(self):
        """Build up a program across multiple run() calls."""
        env = standard_env()
        run("(define square (lambda (x) (* x x)))", env)
        run("(define cube (lambda (x) (* x (square x))))", env)
        assert run("(cube 3)", env) == 27

    def test_default_env(self):
        """run() creates a fresh env when none is provided."""
        assert run("(+ 1 2)") == 3


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
