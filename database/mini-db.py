"""
A Miniature Database — in Python
==================================

How does a database store, index, and query your data? This module
implements a mini relational database from scratch, covering a B-Tree
index, a SQL parser, and a query executor — all in a single file.

Architecture
------------

::

    SQL string
        │
        ▼
    ┌──────────────┐
    │  SQL PARSER   │  Tokenize → parse → AST (Abstract Syntax Tree)
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   EXECUTOR    │  Walk the AST, read/write tables, evaluate WHERE
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │    TABLE      │  Schema (column names & types) + rows of data
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   B-TREE      │  Sorted index for fast lookups by primary key
    │   INDEX       │  O(log n) search, insert, delete
    └──────────────┘

Supported SQL
-------------

- ``CREATE TABLE name (col type, ...)``
- ``INSERT INTO name VALUES (...)``
- ``SELECT col, ... FROM name [WHERE ...]``
- ``UPDATE name SET col=val, ... [WHERE ...]``
- ``DELETE FROM name [WHERE ...]``

Reference
---------
- `DBDB: Dog Bed Database
  <http://aosabook.org/en/500L/dbdb-dog-bed-database.html>`_
  from *500 Lines or Less*
"""


# ═══════════════════════════════════════════════════════════════════════════════
# B-TREE INDEX
# ═══════════════════════════════════════════════════════════════════════════════

class BTreeNode:
    """A node in a B-Tree.

    Each node holds up to ``2 * t - 1`` keys and ``2 * t`` children,
    where *t* is the minimum degree.

    For ``t = 2`` (the default), each node holds 1–3 keys and 2–4
    children. This keeps the tree shallow and lookups fast.
    """

    def __init__(self, leaf=True):
        self.keys = []      # list of keys (sorted)
        self.values = []    # parallel list of values
        self.children = []  # child BTreeNode pointers
        self.leaf = leaf


class BTree:
    """A B-Tree: the data structure behind database indexes.

    A B-Tree keeps keys sorted and the tree balanced, guaranteeing
    O(log n) search, insert, and delete. Unlike a binary tree,
    each node can have many keys and children, which makes it
    ideal for disk-based storage (fewer I/O operations).

    This implementation uses minimum degree *t* = 3, so each node
    holds 2–5 keys.
    """

    def __init__(self, t=3):
        self.t = t  # minimum degree
        self.root = BTreeNode(leaf=True)

    def search(self, key):
        """Search for *key*. Returns the value, or None if not found."""
        return self._search(self.root, key)

    def insert(self, key, value):
        """Insert a key-value pair. If the key exists, update its value."""
        root = self.root

        # If root is full, split it first
        if len(root.keys) == 2 * self.t - 1:
            new_root = BTreeNode(leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key, value)

    def delete(self, key):
        """Delete a key from the tree. Returns True if found, False otherwise."""
        found = self._delete(self.root, key)

        # If root has no keys but has a child, shrink the tree
        if not self.root.keys and self.root.children:
            self.root = self.root.children[0]

        return found

    def items(self):
        """Yield all (key, value) pairs in sorted order."""
        yield from self._items(self.root)

    def __len__(self):
        return sum(1 for _ in self.items())

    def __contains__(self, key):
        return self.search(key) is not None

    # ── internal methods ────────────────────────────────────────────────────

    def _search(self, node, key):
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and key == node.keys[i]:
            return node.values[i]

        if node.leaf:
            return None

        return self._search(node.children[i], key)

    def _insert_non_full(self, node, key, value):
        i = len(node.keys) - 1

        if node.leaf:
            # Check for existing key (update)
            for j in range(len(node.keys)):
                if node.keys[j] == key:
                    node.values[j] = value
                    return

            # Insert in sorted position
            node.keys.append(None)
            node.values.append(None)
            while i >= 0 and key < node.keys[i]:
                node.keys[i + 1] = node.keys[i]
                node.values[i + 1] = node.values[i]
                i -= 1
            node.keys[i + 1] = key
            node.values[i + 1] = value
        else:
            # Check for existing key in internal node
            for j in range(len(node.keys)):
                if node.keys[j] == key:
                    node.values[j] = value
                    return

            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1

            if len(node.children[i].keys) == 2 * self.t - 1:
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
                elif key == node.keys[i]:
                    node.values[i] = value
                    return

            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent, i):
        t = self.t
        child = parent.children[i]
        new_node = BTreeNode(leaf=child.leaf)

        # Move the median key up to parent
        mid = t - 1
        parent.keys.insert(i, child.keys[mid])
        parent.values.insert(i, child.values[mid])
        parent.children.insert(i + 1, new_node)

        # Split keys and values
        new_node.keys = child.keys[mid + 1:]
        new_node.values = child.values[mid + 1:]
        child.keys = child.keys[:mid]
        child.values = child.values[:mid]

        # Split children
        if not child.leaf:
            new_node.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]

    def _delete(self, node, key):
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and key == node.keys[i]:
            # Found the key in this node
            if node.leaf:
                node.keys.pop(i)
                node.values.pop(i)
                return True
            else:
                return self._delete_internal(node, i)
        else:
            # Key is not in this node
            if node.leaf:
                return False
            return self._delete_from_child(node, key, i)

    def _delete_internal(self, node, i):
        """Delete node.keys[i] from an internal node."""
        t = self.t

        # Try to replace with predecessor
        if len(node.children[i].keys) >= t:
            pred_node = node.children[i]
            while not pred_node.leaf:
                pred_node = pred_node.children[-1]
            node.keys[i] = pred_node.keys[-1]
            node.values[i] = pred_node.values[-1]
            return self._delete(node.children[i], pred_node.keys[-1])

        # Try to replace with successor
        if len(node.children[i + 1].keys) >= t:
            succ_node = node.children[i + 1]
            while not succ_node.leaf:
                succ_node = succ_node.children[0]
            node.keys[i] = succ_node.keys[0]
            node.values[i] = succ_node.values[0]
            return self._delete(node.children[i + 1], succ_node.keys[0])

        # Merge children[i] and children[i+1]
        self._merge(node, i)
        return self._delete(node.children[i], node.keys[i])

    def _delete_from_child(self, node, key, i):
        """Ensure child[i] has enough keys, then recurse."""
        t = self.t
        child = node.children[i]

        if len(child.keys) < t:
            # Try borrowing from left sibling
            if i > 0 and len(node.children[i - 1].keys) >= t:
                self._borrow_from_left(node, i)
            # Try borrowing from right sibling
            elif i < len(node.children) - 1 and len(node.children[i + 1].keys) >= t:
                self._borrow_from_right(node, i)
            # Merge with a sibling
            else:
                if i < len(node.children) - 1:
                    self._merge(node, i)
                else:
                    self._merge(node, i - 1)
                    i -= 1

        return self._delete(node.children[i], key)

    def _borrow_from_left(self, parent, i):
        child = parent.children[i]
        left = parent.children[i - 1]

        child.keys.insert(0, parent.keys[i - 1])
        child.values.insert(0, parent.values[i - 1])
        parent.keys[i - 1] = left.keys.pop()
        parent.values[i - 1] = left.values.pop()

        if not left.leaf:
            child.children.insert(0, left.children.pop())

    def _borrow_from_right(self, parent, i):
        child = parent.children[i]
        right = parent.children[i + 1]

        child.keys.append(parent.keys[i])
        child.values.append(parent.values[i])
        parent.keys[i] = right.keys.pop(0)
        parent.values[i] = right.values.pop(0)

        if not right.leaf:
            child.children.append(right.children.pop(0))

    def _merge(self, parent, i):
        """Merge children[i] and children[i+1] with parent key[i] as median."""
        left = parent.children[i]
        right = parent.children[i + 1]

        left.keys.append(parent.keys.pop(i))
        left.values.append(parent.values.pop(i))
        left.keys.extend(right.keys)
        left.values.extend(right.values)
        left.children.extend(right.children)

        parent.children.pop(i + 1)

    def _items(self, node):
        for i in range(len(node.keys)):
            if not node.leaf:
                yield from self._items(node.children[i])
            yield node.keys[i], node.values[i]
        if not node.leaf and node.children:
            yield from self._items(node.children[-1])


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE
# ═══════════════════════════════════════════════════════════════════════════════

class Table:
    """A database table with a schema and B-Tree indexed rows.

    Each row is stored in a B-Tree keyed by an auto-incrementing
    integer ``_rowid``. This mirrors how SQLite stores rows internally.
    """

    def __init__(self, name, columns):
        """Create a table.

        *columns* is a list of ``(name, type_name)`` tuples, e.g.
        ``[("id", "INTEGER"), ("name", "TEXT")]``.
        """
        self.name = name
        self.columns = columns
        self.column_names = [c[0] for c in columns]
        self.column_types = {c[0]: c[1] for c in columns}
        self.rows = BTree()
        self._next_rowid = 1

    def insert(self, values):
        """Insert a row. *values* is a list matching column order."""
        if len(values) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} values, got {len(values)}"
            )

        row = dict(zip(self.column_names, values))
        row["_rowid"] = self._next_rowid
        self.rows.insert(self._next_rowid, row)
        self._next_rowid += 1
        return row["_rowid"]

    def scan(self, condition=None):
        """Return all rows matching *condition* (a callable), or all rows."""
        results = []
        for _, row in self.rows.items():
            if condition is None or condition(row):
                results.append(row)
        return results

    def update(self, assignments, condition=None):
        """Update rows matching *condition*. Returns the count updated."""
        count = 0
        for rowid, row in list(self.rows.items()):
            if condition is None or condition(row):
                for col, val in assignments.items():
                    row[col] = val
                self.rows.insert(rowid, row)
                count += 1
        return count

    def delete(self, condition=None):
        """Delete rows matching *condition*. Returns the count deleted."""
        to_delete = []
        for rowid, row in self.rows.items():
            if condition is None or condition(row):
                to_delete.append(rowid)

        for rowid in to_delete:
            self.rows.delete(rowid)
        return len(to_delete)


# ═══════════════════════════════════════════════════════════════════════════════
# SQL PARSER
# ═══════════════════════════════════════════════════════════════════════════════

# ── tokens ──────────────────────────────────────────────────────────────────

class Token:
    """A single token from the SQL input."""

    def __init__(self, type, value):
        self.type = type
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"

    def __eq__(self, other):
        return (isinstance(other, Token)
                and self.type == other.type
                and self.value == other.value)


# Keywords recognized by the tokenizer
KEYWORDS = {
    "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES",
    "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "AND", "OR",
    "NOT", "NULL", "INTEGER", "TEXT", "REAL", "ORDER", "BY",
    "ASC", "DESC", "LIMIT",
}


def tokenize(sql):
    """Tokenize a SQL string into a list of Tokens."""
    tokens = []
    i = 0
    sql = sql.strip()

    while i < len(sql):
        ch = sql[i]

        # Whitespace
        if ch.isspace():
            i += 1
            continue

        # Single-character tokens
        if ch in "(),;*":
            tokens.append(Token("SYMBOL", ch))
            i += 1
            continue

        # Comparison operators
        if ch in "=<>!":
            if i + 1 < len(sql) and sql[i + 1] == "=":
                tokens.append(Token("OP", ch + "="))
                i += 2
            elif ch in "<>":
                tokens.append(Token("OP", ch))
                i += 1
            elif ch == "=":
                tokens.append(Token("OP", "="))
                i += 1
            else:
                raise SyntaxError(f"Unexpected character: {ch!r}")
            continue

        # String literal
        if ch in ("'", '"'):
            quote = ch
            j = i + 1
            while j < len(sql) and sql[j] != quote:
                j += 1
            if j >= len(sql):
                raise SyntaxError("Unterminated string literal")
            tokens.append(Token("STRING", sql[i + 1:j]))
            i = j + 1
            continue

        # Number
        if ch.isdigit() or (ch == "-" and i + 1 < len(sql) and sql[i + 1].isdigit()):
            j = i + 1 if ch == "-" else i
            while j < len(sql) and (sql[j].isdigit() or sql[j] == "."):
                j += 1
            tokens.append(Token("NUMBER", sql[i:j]))
            i = j
            continue

        # Word (keyword or identifier)
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            word = sql[i:j]
            if word.upper() in KEYWORDS:
                tokens.append(Token("KEYWORD", word.upper()))
            else:
                tokens.append(Token("IDENT", word))
            i = j
            continue

        raise SyntaxError(f"Unexpected character: {ch!r}")

    return tokens


# ── AST nodes ───────────────────────────────────────────────────────────────

class CreateTable:
    def __init__(self, name, columns):
        self.name = name
        self.columns = columns  # [(name, type), ...]

    def __repr__(self):
        return f"CreateTable({self.name!r}, {self.columns!r})"


class Insert:
    def __init__(self, table, values):
        self.table = table
        self.values = values  # [value, ...]

    def __repr__(self):
        return f"Insert({self.table!r}, {self.values!r})"


class Select:
    def __init__(self, columns, table, where=None, order_by=None, limit=None):
        self.columns = columns  # ["*"] or ["col1", "col2"]
        self.table = table
        self.where = where      # WhereClause or None
        self.order_by = order_by  # (column, "ASC"/"DESC") or None
        self.limit = limit        # int or None

    def __repr__(self):
        return f"Select({self.columns!r}, {self.table!r})"


class Update:
    def __init__(self, table, assignments, where=None):
        self.table = table
        self.assignments = assignments  # {col: value, ...}
        self.where = where

    def __repr__(self):
        return f"Update({self.table!r}, {self.assignments!r})"


class Delete:
    def __init__(self, table, where=None):
        self.table = table
        self.where = where

    def __repr__(self):
        return f"Delete({self.table!r})"


class WhereClause:
    """A WHERE condition: ``column op value`` or compound ``AND``/``OR``."""

    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self):
        return f"Where({self.left!r} {self.op} {self.right!r})"


# ── parser ──────────────────────────────────────────────────────────────────

class Parser:
    """Recursive descent parser for a subset of SQL."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, type, value=None):
        token = self.peek()
        if token is None:
            raise SyntaxError(f"Expected {type} {value!r}, got end of input")
        if token.type != type or (value is not None and token.value != value):
            raise SyntaxError(
                f"Expected {type} {value!r}, got {token.type} {token.value!r}"
            )
        return self.advance()

    def match(self, type, value=None):
        token = self.peek()
        if token and token.type == type:
            if value is None or token.value == value:
                return self.advance()
        return None

    def parse(self):
        token = self.peek()
        if token is None:
            raise SyntaxError("Empty SQL statement")

        if token.type == "KEYWORD":
            if token.value == "CREATE":
                return self.parse_create()
            if token.value == "INSERT":
                return self.parse_insert()
            if token.value == "SELECT":
                return self.parse_select()
            if token.value == "UPDATE":
                return self.parse_update()
            if token.value == "DELETE":
                return self.parse_delete()

        raise SyntaxError(f"Unexpected token: {token.value!r}")

    # ── CREATE TABLE ────────────────────────────────────────────────────────

    def parse_create(self):
        self.expect("KEYWORD", "CREATE")
        self.expect("KEYWORD", "TABLE")
        name = self.expect("IDENT").value
        self.expect("SYMBOL", "(")

        columns = []
        while True:
            col_name = self.expect("IDENT").value
            col_type = self.expect("KEYWORD").value
            columns.append((col_name, col_type))
            if not self.match("SYMBOL", ","):
                break

        self.expect("SYMBOL", ")")
        return CreateTable(name, columns)

    # ── INSERT ──────────────────────────────────────────────────────────────

    def parse_insert(self):
        self.expect("KEYWORD", "INSERT")
        self.expect("KEYWORD", "INTO")
        table = self.expect("IDENT").value
        self.expect("KEYWORD", "VALUES")
        self.expect("SYMBOL", "(")

        values = []
        while True:
            values.append(self.parse_value())
            if not self.match("SYMBOL", ","):
                break

        self.expect("SYMBOL", ")")
        return Insert(table, values)

    # ── SELECT ──────────────────────────────────────────────────────────────

    def parse_select(self):
        self.expect("KEYWORD", "SELECT")

        # Columns
        columns = []
        if self.match("SYMBOL", "*"):
            columns = ["*"]
        else:
            columns.append(self.expect("IDENT").value)
            while self.match("SYMBOL", ","):
                columns.append(self.expect("IDENT").value)

        self.expect("KEYWORD", "FROM")
        table = self.expect("IDENT").value

        where = None
        if self.match("KEYWORD", "WHERE"):
            where = self.parse_where()

        order_by = None
        if self.match("KEYWORD", "ORDER"):
            self.expect("KEYWORD", "BY")
            col = self.expect("IDENT").value
            direction = "ASC"
            tok = self.match("KEYWORD", "ASC") or self.match("KEYWORD", "DESC")
            if tok:
                direction = tok.value
            order_by = (col, direction)

        limit = None
        if self.match("KEYWORD", "LIMIT"):
            limit = int(self.expect("NUMBER").value)

        return Select(columns, table, where, order_by, limit)

    # ── UPDATE ──────────────────────────────────────────────────────────────

    def parse_update(self):
        self.expect("KEYWORD", "UPDATE")
        table = self.expect("IDENT").value
        self.expect("KEYWORD", "SET")

        assignments = {}
        while True:
            col = self.expect("IDENT").value
            self.expect("OP", "=")
            val = self.parse_value()
            assignments[col] = val
            if not self.match("SYMBOL", ","):
                break

        where = None
        if self.match("KEYWORD", "WHERE"):
            where = self.parse_where()

        return Update(table, assignments, where)

    # ── DELETE ──────────────────────────────────────────────────────────────

    def parse_delete(self):
        self.expect("KEYWORD", "DELETE")
        self.expect("KEYWORD", "FROM")
        table = self.expect("IDENT").value

        where = None
        if self.match("KEYWORD", "WHERE"):
            where = self.parse_where()

        return Delete(table, where)

    # ── WHERE clause ────────────────────────────────────────────────────────

    def parse_where(self):
        left = self.parse_comparison()

        while True:
            tok = self.match("KEYWORD", "AND") or self.match("KEYWORD", "OR")
            if not tok:
                break
            right = self.parse_comparison()
            left = WhereClause(left, tok.value, right)

        return left

    def parse_comparison(self):
        left = self.expect("IDENT").value
        op = self.expect("OP").value
        right = self.parse_value()
        return WhereClause(left, op, right)

    # ── value ───────────────────────────────────────────────────────────────

    def parse_value(self):
        tok = self.peek()

        if tok and tok.type == "NUMBER":
            self.advance()
            if "." in tok.value:
                return float(tok.value)
            return int(tok.value)

        if tok and tok.type == "STRING":
            self.advance()
            return tok.value

        if tok and tok.type == "KEYWORD" and tok.value == "NULL":
            self.advance()
            return None

        raise SyntaxError(f"Expected a value, got {tok!r}")


def parse(sql):
    """Parse a SQL string into an AST node."""
    tokens = tokenize(sql)
    parser = Parser(tokens)
    return parser.parse()


# ═══════════════════════════════════════════════════════════════════════════════
# QUERY EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    """A miniature relational database.

    Stores tables in memory with B-Tree indexes. Executes SQL
    statements by parsing them into ASTs and walking the tree.
    """

    def __init__(self):
        self.tables = {}  # name → Table

    def execute(self, sql):
        """Execute a SQL string. Returns a result depending on the statement type.

        - ``CREATE TABLE`` → ``"Table created: <name>"``
        - ``INSERT`` → ``rowid`` (integer)
        - ``SELECT`` → list of dicts ``[{col: val, ...}, ...]``
        - ``UPDATE`` → count of rows updated
        - ``DELETE`` → count of rows deleted
        """
        ast = parse(sql)

        if isinstance(ast, CreateTable):
            return self._exec_create(ast)
        if isinstance(ast, Insert):
            return self._exec_insert(ast)
        if isinstance(ast, Select):
            return self._exec_select(ast)
        if isinstance(ast, Update):
            return self._exec_update(ast)
        if isinstance(ast, Delete):
            return self._exec_delete(ast)

        raise RuntimeError(f"Unknown statement type: {type(ast).__name__}")

    def _get_table(self, name):
        if name not in self.tables:
            raise RuntimeError(f"Table not found: {name}")
        return self.tables[name]

    # ── CREATE TABLE ────────────────────────────────────────────────────────

    def _exec_create(self, ast):
        if ast.name in self.tables:
            raise RuntimeError(f"Table already exists: {ast.name}")
        self.tables[ast.name] = Table(ast.name, ast.columns)
        return f"Table created: {ast.name}"

    # ── INSERT ──────────────────────────────────────────────────────────────

    def _exec_insert(self, ast):
        table = self._get_table(ast.table)
        return table.insert(ast.values)

    # ── SELECT ──────────────────────────────────────────────────────────────

    def _exec_select(self, ast):
        table = self._get_table(ast.table)

        # Build WHERE condition
        condition = self._build_condition(ast.where) if ast.where else None
        rows = table.scan(condition)

        # ORDER BY
        if ast.order_by:
            col, direction = ast.order_by
            reverse = direction == "DESC"
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=reverse)

        # LIMIT
        if ast.limit is not None:
            rows = rows[:ast.limit]

        # Project columns
        if ast.columns != ["*"]:
            rows = [{c: row.get(c) for c in ast.columns} for row in rows]
        else:
            # Exclude internal _rowid
            rows = [{k: v for k, v in row.items() if k != "_rowid"}
                    for row in rows]

        return rows

    # ── UPDATE ──────────────────────────────────────────────────────────────

    def _exec_update(self, ast):
        table = self._get_table(ast.table)
        condition = self._build_condition(ast.where) if ast.where else None
        return table.update(ast.assignments, condition)

    # ── DELETE ──────────────────────────────────────────────────────────────

    def _exec_delete(self, ast):
        table = self._get_table(ast.table)
        condition = self._build_condition(ast.where) if ast.where else None
        return table.delete(condition)

    # ── condition builder ───────────────────────────────────────────────────

    def _build_condition(self, where):
        """Convert a WhereClause AST into a callable ``row → bool``."""
        if where is None:
            return None

        # Compound: AND / OR
        if where.op in ("AND", "OR"):
            left_fn = self._build_condition(where.left)
            right_fn = self._build_condition(where.right)
            if where.op == "AND":
                return lambda row: left_fn(row) and right_fn(row)
            return lambda row: left_fn(row) or right_fn(row)

        # Comparison
        col = where.left
        op = where.op
        val = where.right

        if op == "=":
            return lambda row, c=col, v=val: row.get(c) == v
        if op == "!=":
            return lambda row, c=col, v=val: row.get(c) != v
        if op == "<":
            return lambda row, c=col, v=val: row.get(c) is not None and row.get(c) < v
        if op == ">":
            return lambda row, c=col, v=val: row.get(c) is not None and row.get(c) > v
        if op == "<=":
            return lambda row, c=col, v=val: row.get(c) is not None and row.get(c) <= v
        if op == ">=":
            return lambda row, c=col, v=val: row.get(c) is not None and row.get(c) >= v

        raise RuntimeError(f"Unknown operator: {op}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — demo
# ═══════════════════════════════════════════════════════════════════════════════

def _demo():
    print("Mini-DB — Python Edition")
    print("=" * 40)

    db = Database()

    demos = [
        ("CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)",
         "Create a table"),
        ("INSERT INTO users VALUES (1, 'Alice', 30)",
         "Insert Alice"),
        ("INSERT INTO users VALUES (2, 'Bob', 25)",
         "Insert Bob"),
        ("INSERT INTO users VALUES (3, 'Charlie', 35)",
         "Insert Charlie"),
        ("INSERT INTO users VALUES (4, 'Diana', 28)",
         "Insert Diana"),
        ("SELECT * FROM users",
         "Select all users"),
        ("SELECT name, age FROM users WHERE age > 27",
         "Select users older than 27"),
        ("SELECT name FROM users WHERE age >= 25 AND age <= 30",
         "Select users aged 25-30"),
        ("SELECT * FROM users ORDER BY age DESC",
         "Order by age descending"),
        ("SELECT * FROM users ORDER BY name ASC LIMIT 2",
         "First 2 by name"),
        ("UPDATE users SET age = 31 WHERE name = 'Alice'",
         "Update Alice's age"),
        ("SELECT name, age FROM users WHERE name = 'Alice'",
         "Verify update"),
        ("DELETE FROM users WHERE age < 28",
         "Delete users under 28"),
        ("SELECT * FROM users",
         "Remaining users"),
    ]

    for sql, label in demos:
        result = db.execute(sql)
        print(f"\n  {label}:")
        print(f"    > {sql}")
        if isinstance(result, list):
            if not result:
                print("    (empty)")
            for row in result:
                print(f"    {row}")
        else:
            print(f"    {result!r}")

    # B-Tree demo
    print("\n" + "=" * 40)
    print("B-Tree internals:")
    tree = BTree(t=2)
    for i in [10, 20, 5, 6, 12, 30, 7, 17]:
        tree.insert(i, f"val_{i}")
    print(f"  Inserted: [10, 20, 5, 6, 12, 30, 7, 17]")
    print(f"  Sorted:   {[k for k, v in tree.items()]}")
    print(f"  Search 12: {tree.search(12)!r}")
    print(f"  Search 99: {tree.search(99)!r}")
    tree.delete(6)
    tree.delete(20)
    print(f"  After deleting 6, 20: {[k for k, v in tree.items()]}")
    print(f"  Size: {len(tree)}")


if __name__ == "__main__":
    _demo()
