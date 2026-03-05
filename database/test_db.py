"""
Tests for Mini-DB
==================

Organized by layer so failures point directly to the broken component.
Run with: python -m pytest test_db.py -v
     or:  python test_db.py
"""

import os
import sys

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the module (filename has a hyphen) ────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "mini-db.py")
_loader = SourceFileLoader("mini_db", _path)
_spec = spec_from_loader("mini_db", _loader)
db_module = module_from_spec(_spec)
sys.modules["mini_db"] = db_module
_loader.exec_module(db_module)

BTree = db_module.BTree
BTreeNode = db_module.BTreeNode
Table = db_module.Table
Token = db_module.Token
tokenize = db_module.tokenize
parse = db_module.parse
CreateTable = db_module.CreateTable
Insert = db_module.Insert
Select = db_module.Select
Update = db_module.Update
Delete = db_module.Delete
WhereClause = db_module.WhereClause
Database = db_module.Database


# ═══════════════════════════════════════════════════════════════════════════════
# B-TREE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBTree:
    """Tests for the B-Tree data structure."""

    def test_empty_tree(self):
        tree = BTree()
        assert len(tree) == 0
        assert tree.search(1) is None

    def test_insert_single(self):
        tree = BTree()
        tree.insert(1, "a")
        assert tree.search(1) == "a"

    def test_insert_multiple(self):
        tree = BTree()
        for i in range(10):
            tree.insert(i, f"val_{i}")
        for i in range(10):
            assert tree.search(i) == f"val_{i}"

    def test_insert_reverse_order(self):
        tree = BTree()
        for i in range(9, -1, -1):
            tree.insert(i, f"val_{i}")
        for i in range(10):
            assert tree.search(i) == f"val_{i}"

    def test_insert_update(self):
        tree = BTree()
        tree.insert(1, "old")
        tree.insert(1, "new")
        assert tree.search(1) == "new"
        assert len(tree) == 1

    def test_search_missing(self):
        tree = BTree()
        tree.insert(1, "a")
        assert tree.search(999) is None

    def test_contains(self):
        tree = BTree()
        tree.insert(5, "x")
        assert 5 in tree
        assert 99 not in tree

    def test_items_sorted(self):
        tree = BTree()
        keys = [5, 2, 8, 1, 9, 3]
        for k in keys:
            tree.insert(k, f"v{k}")
        result = [k for k, v in tree.items()]
        assert result == sorted(keys)

    def test_len(self):
        tree = BTree()
        assert len(tree) == 0
        for i in range(5):
            tree.insert(i, i)
        assert len(tree) == 5

    def test_delete_leaf(self):
        tree = BTree()
        tree.insert(1, "a")
        tree.insert(2, "b")
        tree.insert(3, "c")
        assert tree.delete(2) is True
        assert tree.search(2) is None
        assert tree.search(1) == "a"
        assert tree.search(3) == "c"

    def test_delete_missing(self):
        tree = BTree()
        tree.insert(1, "a")
        assert tree.delete(999) is False

    def test_delete_all(self):
        tree = BTree()
        for i in range(10):
            tree.insert(i, f"v{i}")
        for i in range(10):
            tree.delete(i)
        assert len(tree) == 0

    def test_large_insert(self):
        """Insert many keys to force multiple splits."""
        tree = BTree(t=2)
        for i in range(100):
            tree.insert(i, i * 10)
        assert len(tree) == 100
        for i in range(100):
            assert tree.search(i) == i * 10

    def test_large_delete(self):
        """Delete many keys to force merges and borrows."""
        tree = BTree(t=2)
        for i in range(50):
            tree.insert(i, i)
        for i in range(0, 50, 2):
            tree.delete(i)
        assert len(tree) == 25
        for i in range(1, 50, 2):
            assert tree.search(i) == i

    def test_string_keys(self):
        tree = BTree()
        tree.insert("banana", 2)
        tree.insert("apple", 1)
        tree.insert("cherry", 3)
        assert tree.search("apple") == 1
        result = [k for k, v in tree.items()]
        assert result == ["apple", "banana", "cherry"]

    def test_minimum_degree(self):
        """Test with different minimum degrees."""
        for t in [2, 3, 5]:
            tree = BTree(t=t)
            for i in range(30):
                tree.insert(i, i)
            assert len(tree) == 30
            for i in range(30):
                assert tree.search(i) == i


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTable:
    """Tests for the Table class."""

    @pytest.fixture
    def users(self):
        t = Table("users", [("id", "INTEGER"), ("name", "TEXT"), ("age", "INTEGER")])
        t.insert([1, "Alice", 30])
        t.insert([2, "Bob", 25])
        t.insert([3, "Charlie", 35])
        return t

    def test_insert(self):
        t = Table("t", [("x", "INTEGER")])
        rowid = t.insert([42])
        assert rowid == 1

    def test_insert_wrong_count(self):
        t = Table("t", [("x", "INTEGER")])
        with pytest.raises(ValueError, match="Expected 1"):
            t.insert([1, 2])

    def test_scan_all(self, users):
        rows = users.scan()
        assert len(rows) == 3

    def test_scan_with_condition(self, users):
        rows = users.scan(lambda r: r["age"] > 27)
        names = [r["name"] for r in rows]
        assert "Alice" in names
        assert "Charlie" in names
        assert "Bob" not in names

    def test_update(self, users):
        count = users.update({"age": 99}, lambda r: r["name"] == "Bob")
        assert count == 1
        rows = users.scan(lambda r: r["name"] == "Bob")
        assert rows[0]["age"] == 99

    def test_update_all(self, users):
        count = users.update({"age": 0})
        assert count == 3

    def test_delete(self, users):
        count = users.delete(lambda r: r["name"] == "Bob")
        assert count == 1
        assert len(users.scan()) == 2

    def test_delete_all(self, users):
        count = users.delete()
        assert count == 3
        assert len(users.scan()) == 0

    def test_auto_rowid(self, users):
        rows = users.scan()
        rowids = [r["_rowid"] for r in rows]
        assert rowids == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENIZER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenizer:
    """Tests for the SQL tokenizer."""

    def test_empty(self):
        assert tokenize("") == []

    def test_keywords(self):
        tokens = tokenize("SELECT FROM WHERE")
        assert all(t.type == "KEYWORD" for t in tokens)

    def test_identifier(self):
        tokens = tokenize("users")
        assert tokens == [Token("IDENT", "users")]

    def test_number(self):
        tokens = tokenize("42")
        assert tokens == [Token("NUMBER", "42")]

    def test_negative_number(self):
        tokens = tokenize("-5")
        assert tokens == [Token("NUMBER", "-5")]

    def test_float(self):
        tokens = tokenize("3.14")
        assert tokens == [Token("NUMBER", "3.14")]

    def test_string_single_quotes(self):
        tokens = tokenize("'hello'")
        assert tokens == [Token("STRING", "hello")]

    def test_string_double_quotes(self):
        tokens = tokenize('"hello"')
        assert tokens == [Token("STRING", "hello")]

    def test_operators(self):
        tokens = tokenize("= != < > <= >=")
        expected = ["=", "!=", "<", ">", "<=", ">="]
        assert [t.value for t in tokens] == expected

    def test_symbols(self):
        tokens = tokenize("( ) , ; *")
        assert [t.value for t in tokens] == ["(", ")", ",", ";", "*"]

    def test_full_select(self):
        tokens = tokenize("SELECT * FROM users WHERE age > 25")
        types = [t.type for t in tokens]
        assert types == ["KEYWORD", "SYMBOL", "KEYWORD", "IDENT",
                         "KEYWORD", "IDENT", "OP", "NUMBER"]

    def test_unterminated_string(self):
        with pytest.raises(SyntaxError, match="Unterminated"):
            tokenize("'oops")

    def test_unexpected_character(self):
        with pytest.raises(SyntaxError, match="Unexpected"):
            tokenize("@")


# ═══════════════════════════════════════════════════════════════════════════════
# PARSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestParser:
    """Tests for the SQL parser."""

    def test_parse_create(self):
        ast = parse("CREATE TABLE t (id INTEGER, name TEXT)")
        assert isinstance(ast, CreateTable)
        assert ast.name == "t"
        assert ast.columns == [("id", "INTEGER"), ("name", "TEXT")]

    def test_parse_insert(self):
        ast = parse("INSERT INTO t VALUES (1, 'hello')")
        assert isinstance(ast, Insert)
        assert ast.table == "t"
        assert ast.values == [1, "hello"]

    def test_parse_select_star(self):
        ast = parse("SELECT * FROM t")
        assert isinstance(ast, Select)
        assert ast.columns == ["*"]
        assert ast.table == "t"
        assert ast.where is None

    def test_parse_select_columns(self):
        ast = parse("SELECT name, age FROM users")
        assert isinstance(ast, Select)
        assert ast.columns == ["name", "age"]

    def test_parse_select_where(self):
        ast = parse("SELECT * FROM t WHERE age > 25")
        assert isinstance(ast, Select)
        assert ast.where is not None
        assert ast.where.left == "age"
        assert ast.where.op == ">"
        assert ast.where.right == 25

    def test_parse_select_where_and(self):
        ast = parse("SELECT * FROM t WHERE age > 20 AND name = 'Alice'")
        assert ast.where.op == "AND"

    def test_parse_select_order_by(self):
        ast = parse("SELECT * FROM t ORDER BY age DESC")
        assert ast.order_by == ("age", "DESC")

    def test_parse_select_limit(self):
        ast = parse("SELECT * FROM t LIMIT 10")
        assert ast.limit == 10

    def test_parse_update(self):
        ast = parse("UPDATE t SET age = 30 WHERE name = 'Alice'")
        assert isinstance(ast, Update)
        assert ast.table == "t"
        assert ast.assignments == {"age": 30}

    def test_parse_update_multiple(self):
        ast = parse("UPDATE t SET age = 30, name = 'Bob'")
        assert ast.assignments == {"age": 30, "name": "Bob"}

    def test_parse_delete(self):
        ast = parse("DELETE FROM t WHERE id = 1")
        assert isinstance(ast, Delete)
        assert ast.table == "t"
        assert ast.where is not None

    def test_parse_delete_all(self):
        ast = parse("DELETE FROM t")
        assert ast.where is None

    def test_parse_null_value(self):
        ast = parse("INSERT INTO t VALUES (NULL)")
        assert ast.values == [None]

    def test_parse_empty_raises(self):
        with pytest.raises(SyntaxError, match="Empty"):
            parse("")

    def test_parse_invalid_raises(self):
        with pytest.raises(SyntaxError):
            parse("BOGUS STATEMENT")


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE (EXECUTOR) TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabase:
    """Tests for the Database query executor."""

    @pytest.fixture
    def db(self):
        d = Database()
        d.execute("CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)")
        d.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
        d.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
        d.execute("INSERT INTO users VALUES (3, 'Charlie', 35)")
        return d

    # ── CREATE ──────────────────────────────────────────────────────────────

    def test_create_table(self):
        db = Database()
        result = db.execute("CREATE TABLE t (x INTEGER)")
        assert "created" in result

    def test_create_duplicate_raises(self, db):
        with pytest.raises(RuntimeError, match="already exists"):
            db.execute("CREATE TABLE users (x INTEGER)")

    # ── INSERT ──────────────────────────────────────────────────────────────

    def test_insert(self, db):
        rowid = db.execute("INSERT INTO users VALUES (4, 'Diana', 28)")
        assert rowid == 4

    def test_insert_missing_table(self):
        db = Database()
        with pytest.raises(RuntimeError, match="not found"):
            db.execute("INSERT INTO nope VALUES (1)")

    # ── SELECT ──────────────────────────────────────────────────────────────

    def test_select_all(self, db):
        rows = db.execute("SELECT * FROM users")
        assert len(rows) == 3

    def test_select_columns(self, db):
        rows = db.execute("SELECT name FROM users")
        assert all("name" in r and "age" not in r for r in rows)

    def test_select_where_eq(self, db):
        rows = db.execute("SELECT * FROM users WHERE name = 'Alice'")
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"

    def test_select_where_gt(self, db):
        rows = db.execute("SELECT * FROM users WHERE age > 27")
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Charlie"}

    def test_select_where_lt(self, db):
        rows = db.execute("SELECT * FROM users WHERE age < 30")
        assert len(rows) == 1
        assert rows[0]["name"] == "Bob"

    def test_select_where_gte(self, db):
        rows = db.execute("SELECT * FROM users WHERE age >= 30")
        assert len(rows) == 2

    def test_select_where_lte(self, db):
        rows = db.execute("SELECT * FROM users WHERE age <= 30")
        assert len(rows) == 2

    def test_select_where_ne(self, db):
        rows = db.execute("SELECT * FROM users WHERE name != 'Bob'")
        assert len(rows) == 2

    def test_select_where_and(self, db):
        rows = db.execute("SELECT * FROM users WHERE age >= 25 AND age <= 30")
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Bob"}

    def test_select_where_or(self, db):
        rows = db.execute("SELECT * FROM users WHERE name = 'Alice' OR name = 'Bob'")
        assert len(rows) == 2

    def test_select_order_asc(self, db):
        rows = db.execute("SELECT * FROM users ORDER BY age ASC")
        ages = [r["age"] for r in rows]
        assert ages == [25, 30, 35]

    def test_select_order_desc(self, db):
        rows = db.execute("SELECT * FROM users ORDER BY age DESC")
        ages = [r["age"] for r in rows]
        assert ages == [35, 30, 25]

    def test_select_limit(self, db):
        rows = db.execute("SELECT * FROM users LIMIT 2")
        assert len(rows) == 2

    def test_select_order_and_limit(self, db):
        rows = db.execute("SELECT * FROM users ORDER BY age DESC LIMIT 1")
        assert len(rows) == 1
        assert rows[0]["name"] == "Charlie"

    def test_select_empty_result(self, db):
        rows = db.execute("SELECT * FROM users WHERE age > 100")
        assert rows == []

    def test_select_string_where(self, db):
        rows = db.execute("SELECT * FROM users WHERE name = 'Charlie'")
        assert len(rows) == 1
        assert rows[0]["age"] == 35

    # ── UPDATE ──────────────────────────────────────────────────────────────

    def test_update(self, db):
        count = db.execute("UPDATE users SET age = 99 WHERE name = 'Bob'")
        assert count == 1
        rows = db.execute("SELECT * FROM users WHERE name = 'Bob'")
        assert rows[0]["age"] == 99

    def test_update_all(self, db):
        count = db.execute("UPDATE users SET age = 0")
        assert count == 3

    def test_update_no_match(self, db):
        count = db.execute("UPDATE users SET age = 0 WHERE name = 'Nobody'")
        assert count == 0

    def test_update_multiple_columns(self, db):
        db.execute("UPDATE users SET name = 'Alicia', age = 31 WHERE id = 1")
        rows = db.execute("SELECT * FROM users WHERE id = 1")
        assert rows[0]["name"] == "Alicia"
        assert rows[0]["age"] == 31

    # ── DELETE ──────────────────────────────────────────────────────────────

    def test_delete(self, db):
        count = db.execute("DELETE FROM users WHERE name = 'Bob'")
        assert count == 1
        rows = db.execute("SELECT * FROM users")
        assert len(rows) == 2

    def test_delete_all(self, db):
        count = db.execute("DELETE FROM users")
        assert count == 3
        assert db.execute("SELECT * FROM users") == []

    def test_delete_no_match(self, db):
        count = db.execute("DELETE FROM users WHERE name = 'Nobody'")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full workflow integration tests."""

    def test_crud_lifecycle(self):
        db = Database()
        db.execute("CREATE TABLE items (name TEXT, qty INTEGER)")

        db.execute("INSERT INTO items VALUES ('apple', 10)")
        db.execute("INSERT INTO items VALUES ('banana', 5)")
        db.execute("INSERT INTO items VALUES ('cherry', 20)")

        # Read
        rows = db.execute("SELECT * FROM items")
        assert len(rows) == 3

        # Update
        db.execute("UPDATE items SET qty = 15 WHERE name = 'banana'")
        rows = db.execute("SELECT * FROM items WHERE name = 'banana'")
        assert rows[0]["qty"] == 15

        # Delete
        db.execute("DELETE FROM items WHERE qty < 15")
        rows = db.execute("SELECT * FROM items")
        assert len(rows) == 2

    def test_multiple_tables(self):
        db = Database()
        db.execute("CREATE TABLE a (x INTEGER)")
        db.execute("CREATE TABLE b (y TEXT)")

        db.execute("INSERT INTO a VALUES (1)")
        db.execute("INSERT INTO b VALUES ('hello')")

        assert len(db.execute("SELECT * FROM a")) == 1
        assert len(db.execute("SELECT * FROM b")) == 1

    def test_many_inserts(self):
        db = Database()
        db.execute("CREATE TABLE nums (val INTEGER)")
        for i in range(100):
            db.execute(f"INSERT INTO nums VALUES ({i})")

        rows = db.execute("SELECT * FROM nums")
        assert len(rows) == 100

        rows = db.execute("SELECT * FROM nums WHERE val >= 50")
        assert len(rows) == 50

    def test_float_values(self):
        db = Database()
        db.execute("CREATE TABLE prices (item TEXT, price REAL)")
        db.execute("INSERT INTO prices VALUES ('widget', 9.99)")
        db.execute("INSERT INTO prices VALUES ('gadget', 19.50)")

        rows = db.execute("SELECT * FROM prices WHERE price > 10.0")
        assert len(rows) == 1
        assert rows[0]["item"] == "gadget"

    def test_null_values(self):
        db = Database()
        db.execute("CREATE TABLE t (x INTEGER, y TEXT)")
        db.execute("INSERT INTO t VALUES (1, NULL)")
        rows = db.execute("SELECT * FROM t")
        assert rows[0]["y"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
