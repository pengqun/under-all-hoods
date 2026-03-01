"""
Tests for the Super Tiny Compiler
==================================

Organized by compiler phase so failures point directly to the broken stage.
Run with: python -m pytest test_compiler.py -v
     or:  python test_compiler.py
"""

import sys
import os

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the compiler module (filename has a hyphen) ───────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "javascript-compiler-jamie.py")
_loader = SourceFileLoader("compiler", _path)
_spec = spec_from_loader("compiler", _loader)
compiler_module = module_from_spec(_spec)
sys.modules["compiler"] = compiler_module
_loader.exec_module(compiler_module)

# Pull out everything we need
Token = compiler_module.Token
NumberLiteral = compiler_module.NumberLiteral
StringLiteral = compiler_module.StringLiteral
CallExpression = compiler_module.CallExpression
Program = compiler_module.Program
Identifier = compiler_module.Identifier
TargetCallExpression = compiler_module.TargetCallExpression
ExpressionStatement = compiler_module.ExpressionStatement
TargetProgram = compiler_module.TargetProgram

tokenize = compiler_module.tokenize
parse = compiler_module.parse
transform = compiler_module.transform
generate = compiler_module.generate
compiler = compiler_module.compiler


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — TOKENIZER TESTS
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
        assert tokenize("(") == [Token("paren", "(")]

    def test_single_close_paren(self):
        assert tokenize(")") == [Token("paren", ")")]

    def test_single_number(self):
        assert tokenize("42") == [Token("number", "42")]

    def test_multi_digit_number(self):
        assert tokenize("12345") == [Token("number", "12345")]

    def test_single_name(self):
        assert tokenize("add") == [Token("name", "add")]

    def test_single_string(self):
        assert tokenize('"hello"') == [Token("string", "hello")]

    def test_simple_expression(self):
        """Tokenize a basic call: (add 2 3)"""
        result = tokenize("(add 2 3)")
        expected = [
            Token("paren", "("),
            Token("name", "add"),
            Token("number", "2"),
            Token("number", "3"),
            Token("paren", ")"),
        ]
        assert result == expected

    def test_nested_expression(self):
        """Tokenize nested calls: (add 2 (subtract 4 2))"""
        result = tokenize("(add 2 (subtract 4 2))")
        expected = [
            Token("paren", "("),
            Token("name", "add"),
            Token("number", "2"),
            Token("paren", "("),
            Token("name", "subtract"),
            Token("number", "4"),
            Token("number", "2"),
            Token("paren", ")"),
            Token("paren", ")"),
        ]
        assert result == expected

    def test_string_expression(self):
        """Tokenize an expression with strings."""
        result = tokenize('(concat "hello" "world")')
        expected = [
            Token("paren", "("),
            Token("name", "concat"),
            Token("string", "hello"),
            Token("string", "world"),
            Token("paren", ")"),
        ]
        assert result == expected

    def test_extra_whitespace(self):
        """Extra whitespace between tokens is handled gracefully."""
        result = tokenize("(  add   2   3  )")
        expected = [
            Token("paren", "("),
            Token("name", "add"),
            Token("number", "2"),
            Token("number", "3"),
            Token("paren", ")"),
        ]
        assert result == expected

    def test_unterminated_string_raises(self):
        """An unterminated string should raise a SyntaxError."""
        with pytest.raises(SyntaxError, match="Unterminated string"):
            tokenize('"oops')

    def test_unexpected_character_raises(self):
        """An unrecognized character should raise a SyntaxError."""
        with pytest.raises(SyntaxError, match="Unexpected character"):
            tokenize("@")

    def test_multiple_expressions(self):
        """Tokenize multiple top-level expressions."""
        result = tokenize("(add 1 2) (subtract 3 4)")
        assert result == [
            Token("paren", "("),
            Token("name", "add"),
            Token("number", "1"),
            Token("number", "2"),
            Token("paren", ")"),
            Token("paren", "("),
            Token("name", "subtract"),
            Token("number", "3"),
            Token("number", "4"),
            Token("paren", ")"),
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PARSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestParser:
    """Tests for the parse() function."""

    def test_empty_tokens(self):
        """No tokens should produce an empty program."""
        result = parse([])
        assert result == Program(body=[])

    def test_number_literal(self):
        """A bare number token is parsed as a NumberLiteral."""
        tokens = [Token("number", "5")]
        result = parse(tokens)
        assert result == Program(body=[NumberLiteral("5")])

    def test_string_literal(self):
        """A bare string token is parsed as a StringLiteral."""
        tokens = [Token("string", "hi")]
        result = parse(tokens)
        assert result == Program(body=[StringLiteral("hi")])

    def test_simple_call(self):
        """Parse (add 2 3) into a CallExpression."""
        tokens = tokenize("(add 2 3)")
        result = parse(tokens)
        expected = Program(body=[
            CallExpression("add", [NumberLiteral("2"), NumberLiteral("3")])
        ])
        assert result == expected

    def test_nested_call(self):
        """Parse (add 2 (subtract 4 2)) with nesting."""
        tokens = tokenize("(add 2 (subtract 4 2))")
        result = parse(tokens)
        expected = Program(body=[
            CallExpression("add", [
                NumberLiteral("2"),
                CallExpression("subtract", [
                    NumberLiteral("4"),
                    NumberLiteral("2"),
                ]),
            ])
        ])
        assert result == expected

    def test_deeply_nested_call(self):
        """Parse three levels of nesting."""
        tokens = tokenize("(add 1 (subtract 3 (multiply 4 5)))")
        result = parse(tokens)
        expected = Program(body=[
            CallExpression("add", [
                NumberLiteral("1"),
                CallExpression("subtract", [
                    NumberLiteral("3"),
                    CallExpression("multiply", [
                        NumberLiteral("4"),
                        NumberLiteral("5"),
                    ]),
                ]),
            ])
        ])
        assert result == expected

    def test_call_with_no_args(self):
        """Parse a call with zero arguments: (noop)."""
        tokens = tokenize("(noop)")
        result = parse(tokens)
        assert result == Program(body=[CallExpression("noop", [])])

    def test_multiple_top_level_calls(self):
        """Parse two separate top-level expressions."""
        tokens = tokenize("(add 1 2) (subtract 3 4)")
        result = parse(tokens)
        expected = Program(body=[
            CallExpression("add", [NumberLiteral("1"), NumberLiteral("2")]),
            CallExpression("subtract", [NumberLiteral("3"), NumberLiteral("4")]),
        ])
        assert result == expected

    def test_missing_function_name_raises(self):
        """'(' followed by a number instead of a name should error."""
        tokens = [Token("paren", "("), Token("number", "5"), Token("paren", ")")]
        with pytest.raises(SyntaxError, match="Expected function name"):
            parse(tokens)

    def test_unexpected_token_raises(self):
        """A closing paren at the top level should error."""
        tokens = [Token("paren", ")")]
        with pytest.raises(SyntaxError, match="Unexpected token"):
            parse(tokens)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — TRANSFORMER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransformer:
    """Tests for the transform() function."""

    def test_empty_program(self):
        """Empty source program produces empty target program."""
        result = transform(Program(body=[]))
        assert result == TargetProgram(body=[])

    def test_number_literal_passthrough(self):
        """A top-level NumberLiteral is wrapped in ExpressionStatement."""
        source = Program(body=[NumberLiteral("7")])
        result = transform(source)
        expected = TargetProgram(body=[
            ExpressionStatement(NumberLiteral("7"))
        ])
        assert result == expected

    def test_string_literal_passthrough(self):
        """A top-level StringLiteral is wrapped in ExpressionStatement."""
        source = Program(body=[StringLiteral("hi")])
        result = transform(source)
        expected = TargetProgram(body=[
            ExpressionStatement(StringLiteral("hi"))
        ])
        assert result == expected

    def test_simple_call_transformation(self):
        """CallExpression → TargetCallExpression with Identifier callee."""
        source = Program(body=[
            CallExpression("add", [NumberLiteral("2"), NumberLiteral("3")])
        ])
        result = transform(source)
        expected = TargetProgram(body=[
            ExpressionStatement(
                TargetCallExpression(
                    callee=Identifier("add"),
                    arguments=[NumberLiteral("2"), NumberLiteral("3")],
                )
            )
        ])
        assert result == expected

    def test_nested_call_transformation(self):
        """Nested calls are recursively transformed."""
        source = Program(body=[
            CallExpression("add", [
                NumberLiteral("2"),
                CallExpression("subtract", [NumberLiteral("4"), NumberLiteral("2")]),
            ])
        ])
        result = transform(source)
        expected = TargetProgram(body=[
            ExpressionStatement(
                TargetCallExpression(
                    callee=Identifier("add"),
                    arguments=[
                        NumberLiteral("2"),
                        TargetCallExpression(
                            callee=Identifier("subtract"),
                            arguments=[NumberLiteral("4"), NumberLiteral("2")],
                        ),
                    ],
                )
            )
        ])
        assert result == expected

    def test_multiple_statements(self):
        """Multiple top-level nodes each get their own ExpressionStatement."""
        source = Program(body=[
            CallExpression("a", [NumberLiteral("1")]),
            CallExpression("b", [NumberLiteral("2")]),
        ])
        result = transform(source)
        assert len(result.body) == 2
        assert all(isinstance(s, ExpressionStatement) for s in result.body)

    def test_unknown_node_raises(self):
        """Passing an unknown node type should raise TypeError."""
        source = Program(body=["not a real node"])
        with pytest.raises(TypeError, match="Unknown node"):
            transform(source)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — CODE GENERATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeGenerator:
    """Tests for the generate() function."""

    def test_number_literal(self):
        assert generate(NumberLiteral("42")) == "42"

    def test_string_literal(self):
        assert generate(StringLiteral("hello")) == '"hello"'

    def test_identifier(self):
        assert generate(Identifier("add")) == "add"

    def test_target_call_no_args(self):
        node = TargetCallExpression(callee=Identifier("noop"), arguments=[])
        assert generate(node) == "noop()"

    def test_target_call_with_args(self):
        node = TargetCallExpression(
            callee=Identifier("add"),
            arguments=[NumberLiteral("2"), NumberLiteral("3")],
        )
        assert generate(node) == "add(2, 3)"

    def test_expression_statement(self):
        node = ExpressionStatement(
            TargetCallExpression(
                callee=Identifier("add"),
                arguments=[NumberLiteral("2"), NumberLiteral("3")],
            )
        )
        assert generate(node) == "add(2, 3);"

    def test_full_program(self):
        node = TargetProgram(body=[
            ExpressionStatement(
                TargetCallExpression(
                    callee=Identifier("add"),
                    arguments=[NumberLiteral("2"), NumberLiteral("3")],
                )
            )
        ])
        assert generate(node) == "add(2, 3);"

    def test_nested_call_generation(self):
        node = TargetCallExpression(
            callee=Identifier("add"),
            arguments=[
                NumberLiteral("2"),
                TargetCallExpression(
                    callee=Identifier("subtract"),
                    arguments=[NumberLiteral("4"), NumberLiteral("2")],
                ),
            ],
        )
        assert generate(node) == "add(2, subtract(4, 2))"

    def test_multiple_statements(self):
        node = TargetProgram(body=[
            ExpressionStatement(
                TargetCallExpression(
                    callee=Identifier("a"),
                    arguments=[NumberLiteral("1")],
                )
            ),
            ExpressionStatement(
                TargetCallExpression(
                    callee=Identifier("b"),
                    arguments=[NumberLiteral("2")],
                )
            ),
        ])
        assert generate(node) == "a(1);\nb(2);"

    def test_unknown_node_raises(self):
        with pytest.raises(TypeError, match="Unknown node"):
            generate("not a real node")


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END COMPILER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompilerEndToEnd:
    """Full pipeline tests: source string → target string."""

    def test_simple_add(self):
        assert compiler("(add 2 2)") == "add(2, 2);"

    def test_simple_subtract(self):
        assert compiler("(subtract 4 2)") == "subtract(4, 2);"

    def test_nested_expression(self):
        assert compiler("(add 2 (subtract 4 2))") == "add(2, subtract(4, 2));"

    def test_deeply_nested(self):
        source = "(add 1 (subtract 3 (multiply 4 5)))"
        expected = "add(1, subtract(3, multiply(4, 5)));"
        assert compiler(source) == expected

    def test_string_arguments(self):
        source = '(concat "hello" "world")'
        expected = 'concat("hello", "world");'
        assert compiler(source) == expected

    def test_mixed_types(self):
        source = '(print "value" 42)'
        expected = 'print("value", 42);'
        assert compiler(source) == expected

    def test_single_arg_call(self):
        assert compiler("(inc 1)") == "inc(1);"

    def test_no_args_call(self):
        assert compiler("(noop)") == "noop();"

    def test_multiple_top_level_expressions(self):
        source = "(add 1 2) (subtract 3 4)"
        expected = "add(1, 2);\nsubtract(3, 4);"
        assert compiler(source) == expected

    def test_three_arguments(self):
        source = "(sum 1 2 3)"
        expected = "sum(1, 2, 3);"
        assert compiler(source) == expected

    def test_all_nested(self):
        source = "(a (b (c 1)))"
        expected = "a(b(c(1)));"
        assert compiler(source) == expected

    def test_whitespace_variations(self):
        """Extra whitespace should not affect output."""
        assert compiler("(  add  2   3  )") == "add(2, 3);"

    def test_newlines_in_source(self):
        """Newlines in source are treated as whitespace."""
        source = "(add\n  2\n  3)"
        assert compiler(source) == "add(2, 3);"


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
