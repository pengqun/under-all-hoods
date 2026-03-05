# Database (SQLite): Under the Hood

How does a database store, index, and query your data? This module implements a mini relational database from scratch, covering a B-Tree index, a SQL parser, and a query executor — all in a single file.

## What it Does

This database understands real SQL syntax and executes it against in-memory tables:

```sql
CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)
INSERT INTO users VALUES (1, 'Alice', 30)
INSERT INTO users VALUES (2, 'Bob', 25)
INSERT INTO users VALUES (3, 'Charlie', 35)

SELECT name, age FROM users WHERE age > 27
→ [{'name': 'Alice', 'age': 30}, {'name': 'Charlie', 'age': 35}]

SELECT * FROM users ORDER BY age DESC LIMIT 2
→ [{'id': 3, 'name': 'Charlie', 'age': 35}, {'id': 1, 'name': 'Alice', 'age': 30}]

UPDATE users SET age = 31 WHERE name = 'Alice'
→ 1 (row updated)

DELETE FROM users WHERE age < 28
→ 1 (row deleted)
```

## The Three Layers

Every SQL query flows through three layers:

```
SQL string  →  Parser  →  AST  →  Executor  →  Table + B-Tree  →  Result
                Layer 1           Layer 2          Layer 3
```

### Layer 1: SQL Parser

The parser converts a SQL string into an **Abstract Syntax Tree** (AST) in two steps:

**Tokenize**: Break the string into tokens:
```
"SELECT name FROM users WHERE age > 25"
→ [KEYWORD:SELECT, IDENT:name, KEYWORD:FROM, IDENT:users, KEYWORD:WHERE, IDENT:age, OP:>, NUMBER:25]
```

**Parse**: A recursive descent parser reads tokens left-to-right and builds the AST:
```
Select(
    columns=["name"],
    table="users",
    where=Where("age" > 25),
)
```

Five SQL statement types are supported: `CREATE TABLE`, `INSERT`, `SELECT` (with WHERE, ORDER BY, LIMIT), `UPDATE`, and `DELETE`.

### Layer 2: Query Executor

The executor walks the AST and calls the appropriate table operations:

- `CREATE TABLE` → create a new `Table` object
- `INSERT` → add a row to the table's B-Tree
- `SELECT` → scan rows, filter by WHERE, sort by ORDER BY, apply LIMIT
- `UPDATE` → find matching rows and modify them
- `DELETE` → find matching rows and remove them

WHERE clauses are compiled into Python callables: `WHERE age > 25 AND name = 'Alice'` becomes a lambda that checks both conditions. Compound conditions (`AND`, `OR`) compose these lambdas.

### Layer 3: Table & B-Tree Index

#### Tables

Each table has a **schema** (column names and types) and stores its rows in a B-Tree keyed by an auto-incrementing `_rowid`. This mirrors how SQLite stores rows internally.

#### B-Tree: Why Not a Binary Tree?

A binary search tree gives O(log n) lookups, but with branching factor 2, a tree with a million keys is ~20 levels deep. A B-Tree with branching factor 100 stores the same data in ~3 levels. Fewer levels = fewer disk reads = faster.

```
Binary Tree (branching factor 2):     B-Tree (branching factor 6):

         4                              [10 | 20 | 30]
        / \                            /    |    |    \
       2   6                      [5,7] [12,15] [22,25] [35,40,45]
      / \ / \
     1  3 5  7

   7 keys = 3 levels               11 keys = 2 levels
```

Each B-Tree node holds up to `2t - 1` keys (where `t` is the minimum degree). When a node is full, it **splits** into two nodes and pushes the median key up to the parent. This keeps the tree perfectly balanced at all times.

Operations:
- **Search**: Start at root, binary-search within each node, follow the right child pointer. O(log n).
- **Insert**: Find the leaf, insert the key. If the leaf is full, split it. Splits may cascade up. O(log n).
- **Delete**: Find the key, remove it. If the node becomes too small, borrow from a sibling or merge. O(log n).

## Running It

```bash
cd database
python mini-db.py
```

Output:

```
Mini-DB — Python Edition
========================================

  Create a table:
    > CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)
    'Table created: users'

  Insert Alice:
    > INSERT INTO users VALUES (1, 'Alice', 30)
    1

  ...

  Select users older than 27:
    > SELECT name, age FROM users WHERE age > 27
    {'name': 'Alice', 'age': 30}
    {'name': 'Charlie', 'age': 35}
    {'name': 'Diana', 'age': 28}

  Order by age descending:
    > SELECT * FROM users ORDER BY age DESC
    {'id': 3, 'name': 'Charlie', 'age': 35}
    {'id': 1, 'name': 'Alice', 'age': 30}
    {'id': 4, 'name': 'Diana', 'age': 28}
    {'id': 2, 'name': 'Bob', 'age': 25}

  ...

========================================
B-Tree internals:
  Inserted: [10, 20, 5, 6, 12, 30, 7, 17]
  Sorted:   [5, 6, 7, 10, 12, 17, 20, 30]
  Search 12: 'val_12'
  Search 99: None
  After deleting 6, 20: [5, 7, 10, 12, 17, 30]
  Size: 6
```

## Running Tests

```bash
cd database
python -m pytest test_db.py -v
```

The test suite covers each layer in isolation plus end-to-end integration tests — 85 test cases covering the B-Tree (insert, delete, search, ordering), table operations, SQL tokenizing, parsing, and full CRUD workflows.

## Implementation: `mini-db.py`

### References

- [DBDB: Dog Bed Database](http://aosabook.org/en/500L/dbdb-dog-bed-database.html) from *500 Lines or Less* — the tutorial this implementation draws from
- [SQLite Architecture](https://www.sqlite.org/arch.html) — how the real SQLite organizes its code
- [Introduction to Algorithms (CLRS)](https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/) — the definitive reference for B-Tree algorithms
