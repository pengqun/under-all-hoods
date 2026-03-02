"""
A Miniature Git — in Python
==============================

How does Git track every version of every file you've ever committed?
This module implements a mini version control system from scratch, covering
content-addressable storage, the object model (blobs, trees, commits),
a staging area (index), branches, and a handful of porcelain commands —
all in a single file.

Architecture
------------

::

    Working Directory        Index (Staging)         Object Store
    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │  hello.py    │─ add ─→│  hello.py    │─commit→│ blob af3b... │
    │  lib/        │        │  lib/util.py │        │ tree 7c2e... │
    │    util.py   │        └──────────────┘        │ commit a1f...│
    └──────────────┘                                └──────────────┘
                                                          │
                                                    refs/heads/main
                                                          │
                                                         HEAD

Object Model
-------------

Every object is stored as::

    [type] [size]\\0[data]  →  SHA-1 hash  →  zlib compressed  →  .git/objects/ab/cdef...

Three object types:

- **Blob**: raw file contents
- **Tree**: list of (mode, name, sha) entries — a directory snapshot
- **Commit**: tree ref + parent ref(s) + author + message

Reference
---------
- `ugit: Learn Git Internals by Building Git Yourself
  <https://www.leshenko.net/p/ugit/>`_ by Nikita Leshenko
- `Write yourself a Git! <https://wyag.thb.lt/>`_ by Thibault Polge
"""

import hashlib
import os
import stat
import time
import zlib


# ═══════════════════════════════════════════════════════════════════════════════
# OBJECT STORE
# ═══════════════════════════════════════════════════════════════════════════════

def repo_find(path="."):
    """Walk up from *path* to find the repository root (contains .mini-git)."""
    path = os.path.realpath(path)
    if os.path.isdir(os.path.join(path, ".mini-git")):
        return path
    parent = os.path.dirname(path)
    if parent == path:
        raise RuntimeError("Not a mini-git repository (or any parent)")
    return repo_find(parent)


def repo_path(repo, *parts):
    """Return a path inside the .mini-git directory."""
    return os.path.join(repo, ".mini-git", *parts)


def repo_dir(repo, *parts, mkdir=False):
    """Return (and optionally create) a directory inside .mini-git."""
    path = repo_path(repo, *parts)
    if mkdir and not os.path.isdir(path):
        os.makedirs(path)
    return path


def hash_object(repo, data, obj_type="blob", write=True):
    """Hash an object and optionally write it to the object store.

    Format: ``{type} {size}\\0{data}``  →  SHA-1  →  zlib  →  disk

    Returns the 40-char hex SHA-1.
    """
    header = f"{obj_type} {len(data)}\0".encode()
    full = header + data
    sha = hashlib.sha1(full).hexdigest()

    if write:
        obj_dir = repo_dir(repo, "objects", sha[:2], mkdir=True)
        obj_path = os.path.join(obj_dir, sha[2:])
        if not os.path.exists(obj_path):
            with open(obj_path, "wb") as f:
                f.write(zlib.compress(full))

    return sha


def read_object(repo, sha):
    """Read an object from the store. Returns ``(type, data)``."""
    obj_path = repo_path(repo, "objects", sha[:2], sha[2:])
    with open(obj_path, "rb") as f:
        raw = zlib.decompress(f.read())

    # Parse header: "type size\0data"
    null_idx = raw.index(b"\0")
    header = raw[:null_idx].decode()
    obj_type, size_str = header.split(" ", 1)
    data = raw[null_idx + 1:]

    assert len(data) == int(size_str), "Object size mismatch"
    return obj_type, data


# ── tree objects ────────────────────────────────────────────────────────────

def make_tree(entries):
    """Build a tree object from a sorted list of ``(mode, name, sha)`` tuples.

    Binary format per entry: ``{mode} {name}\\0{20-byte SHA}``
    """
    buf = b""
    for mode, name, sha in sorted(entries, key=lambda e: e[1]):
        buf += f"{mode} {name}\0".encode()
        buf += bytes.fromhex(sha)
    return buf


def parse_tree(data):
    """Parse tree object bytes into a list of ``(mode, name, sha)`` tuples."""
    entries = []
    i = 0
    while i < len(data):
        # Find the space separating mode from name
        space = data.index(b" ", i)
        mode = data[i:space].decode()

        # Find the null separating name from SHA
        null = data.index(b"\0", space)
        name = data[space + 1:null].decode()

        # Next 20 bytes are the binary SHA-1
        sha_bytes = data[null + 1:null + 21]
        sha = sha_bytes.hex()

        entries.append((mode, name, sha))
        i = null + 21

    return entries


# ── commit objects ──────────────────────────────────────────────────────────

def make_commit(tree_sha, parent_sha, message, author=None, timestamp=None):
    """Build a commit object (bytes).

    Format::

        tree <sha>
        parent <sha>        (if not the root commit)
        author <name> <time>
        committer <name> <time>

        <message>
    """
    if author is None:
        author = "Mini-Git User <user@mini-git>"
    if timestamp is None:
        timestamp = int(time.time())

    lines = [f"tree {tree_sha}"]
    if parent_sha:
        lines.append(f"parent {parent_sha}")
    lines.append(f"author {author} {timestamp} +0000")
    lines.append(f"committer {author} {timestamp} +0000")
    lines.append("")
    lines.append(message)

    return "\n".join(lines).encode()


def parse_commit(data):
    """Parse a commit object into a dict with keys:
    ``tree``, ``parent`` (or None), ``author``, ``committer``, ``message``.
    """
    text = data.decode()
    lines = text.split("\n")

    result = {"parent": None}
    i = 0
    while i < len(lines) and lines[i]:
        key, value = lines[i].split(" ", 1)
        result[key] = value
        i += 1

    # Everything after the blank line is the message
    result["message"] = "\n".join(lines[i + 1:])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX (STAGING AREA)
# ═══════════════════════════════════════════════════════════════════════════════

def read_index(repo):
    """Read the index file. Returns a dict: ``{path: sha}``."""
    idx_path = repo_path(repo, "index")
    if not os.path.exists(idx_path):
        return {}

    index = {}
    with open(idx_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                sha, path = line.split(" ", 1)
                index[path] = sha
    return index


def write_index(repo, index):
    """Write the index file. *index* is a dict: ``{path: sha}``."""
    idx_path = repo_path(repo, "index")
    with open(idx_path, "w") as f:
        for path in sorted(index):
            f.write(f"{index[path]} {path}\n")


def build_tree_from_index(repo, index):
    """Convert a flat index ``{path: blob_sha}`` into nested tree objects.

    Returns the SHA of the root tree.

    For a flat listing like::

        src/main.py  →  abc123
        src/util.py  →  def456
        README.md    →  789abc

    This builds::

        root tree:  100644 README.md 789abc
                    40000  src       <subtree-sha>
        src tree:   100644 main.py   abc123
                    100644 util.py   def456
    """
    # Group entries by top-level directory
    trees = {}  # dirname → [(mode, basename, sha)]
    root_entries = []

    for path, blob_sha in sorted(index.items()):
        parts = path.split("/", 1)
        if len(parts) == 1:
            # File at root level
            root_entries.append(("100644", parts[0], blob_sha))
        else:
            dirname, rest = parts
            if dirname not in trees:
                trees[dirname] = {}
            trees[dirname][rest] = blob_sha

    # Recursively build subtrees
    for dirname in sorted(trees):
        subtree_sha = build_tree_from_index(repo, trees[dirname])
        root_entries.append(("40000", dirname, subtree_sha))

    tree_data = make_tree(root_entries)
    return hash_object(repo, tree_data, "tree")


# ═══════════════════════════════════════════════════════════════════════════════
# REFS & BRANCHES
# ═══════════════════════════════════════════════════════════════════════════════

def read_ref(repo, ref_path):
    """Read a reference file. Follows symbolic refs (``ref: ...``).

    Returns the SHA-1 string, or None if the ref doesn't exist.
    """
    full_path = repo_path(repo, ref_path)
    if not os.path.exists(full_path):
        return None

    with open(full_path, "r") as f:
        content = f.read().strip()

    if content.startswith("ref: "):
        # Symbolic ref — follow it
        return read_ref(repo, content[5:])

    return content


def write_ref(repo, ref_path, sha):
    """Write a SHA-1 to a reference file."""
    full_path = repo_path(repo, ref_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(sha + "\n")


def get_head(repo):
    """Get the SHA that HEAD points to. Returns None for an empty repo."""
    return read_ref(repo, "HEAD")


def get_head_ref(repo):
    """Get the symbolic ref that HEAD points to (e.g. ``refs/heads/main``).

    Returns None if HEAD is detached (points directly to a SHA).
    """
    head_path = repo_path(repo, "HEAD")
    if not os.path.exists(head_path):
        return None

    with open(head_path, "r") as f:
        content = f.read().strip()

    if content.startswith("ref: "):
        return content[5:]
    return None


def get_branch_name(repo):
    """Return the current branch name, or None if HEAD is detached."""
    ref = get_head_ref(repo)
    if ref and ref.startswith("refs/heads/"):
        return ref[len("refs/heads/"):]
    return None


def list_branches(repo):
    """Return a list of branch names."""
    heads_dir = repo_path(repo, "refs", "heads")
    if not os.path.isdir(heads_dir):
        return []
    return sorted(os.listdir(heads_dir))


# ═══════════════════════════════════════════════════════════════════════════════
# WORKING TREE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def collect_files(repo):
    """Collect all files in the working directory (relative paths).

    Ignores the ``.mini-git`` directory.
    """
    files = []
    for root, dirs, filenames in os.walk(repo):
        # Skip .mini-git
        dirs[:] = [d for d in dirs if d != ".mini-git"]
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, repo)
            files.append(rel)
    return sorted(files)


def tree_to_flat(repo, tree_sha, prefix=""):
    """Flatten a tree object into ``{path: blob_sha}``."""
    _, data = read_object(repo, tree_sha)
    entries = parse_tree(data)
    result = {}

    for mode, name, sha in entries:
        path = f"{prefix}{name}" if not prefix else f"{prefix}/{name}"
        if mode == "40000":
            # It's a subtree — recurse
            result.update(tree_to_flat(repo, sha, path))
        else:
            result[path] = sha

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PORCELAIN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_init(path="."):
    """Create a new mini-git repository.

    Sets up the ``.mini-git`` directory structure::

        .mini-git/
        ├── objects/
        ├── refs/
        │   └── heads/
        └── HEAD            →  ref: refs/heads/main
    """
    repo = os.path.realpath(path)
    git_dir = os.path.join(repo, ".mini-git")

    if os.path.exists(git_dir):
        raise RuntimeError(f"Already a mini-git repository: {repo}")

    os.makedirs(os.path.join(git_dir, "objects"))
    os.makedirs(os.path.join(git_dir, "refs", "heads"))

    # HEAD points to the main branch (which doesn't exist yet)
    with open(os.path.join(git_dir, "HEAD"), "w") as f:
        f.write("ref: refs/heads/main\n")

    return repo


def cmd_hash_object(repo, filepath):
    """Hash a file and store it as a blob. Returns the SHA."""
    with open(os.path.join(repo, filepath), "rb") as f:
        data = f.read()
    return hash_object(repo, data, "blob")


def cmd_cat_file(repo, sha):
    """Return the contents of an object as ``(type, data)``."""
    return read_object(repo, sha)


def cmd_add(repo, *paths):
    """Stage files: hash their contents and update the index."""
    index = read_index(repo)

    for path in paths:
        # Normalize path
        full = os.path.join(repo, path)
        if not os.path.exists(full):
            raise FileNotFoundError(f"Path does not exist: {path}")

        if os.path.isdir(full):
            # Add all files under the directory
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if d != ".mini-git"]
                for name in files:
                    fpath = os.path.join(root, name)
                    rel = os.path.relpath(fpath, repo)
                    with open(fpath, "rb") as f:
                        data = f.read()
                    sha = hash_object(repo, data, "blob")
                    index[rel] = sha
        else:
            rel = os.path.relpath(full, repo)
            with open(full, "rb") as f:
                data = f.read()
            sha = hash_object(repo, data, "blob")
            index[rel] = sha

    write_index(repo, index)
    return index


def cmd_rm(repo, *paths):
    """Unstage files: remove them from the index."""
    index = read_index(repo)
    removed = []
    for path in paths:
        rel = os.path.relpath(os.path.join(repo, path), repo)
        if rel in index:
            del index[rel]
            removed.append(rel)
    write_index(repo, index)
    return removed


def cmd_commit(repo, message, author=None, timestamp=None):
    """Create a commit from the current index.

    Steps:
    1. Read the index
    2. Build a tree object from the index
    3. Get the current HEAD as parent
    4. Create a commit object
    5. Update the branch ref
    """
    index = read_index(repo)
    if not index:
        raise RuntimeError("Nothing to commit (empty index)")

    # 1. Build tree
    tree_sha = build_tree_from_index(repo, index)

    # 2. Get parent
    parent_sha = get_head(repo)

    # 3. Create commit
    commit_data = make_commit(tree_sha, parent_sha, message,
                              author=author, timestamp=timestamp)
    commit_sha = hash_object(repo, commit_data, "commit")

    # 4. Update branch ref (or HEAD directly if detached)
    head_ref = get_head_ref(repo)
    if head_ref:
        write_ref(repo, head_ref, commit_sha)
    else:
        # Detached HEAD
        write_ref(repo, "HEAD", commit_sha)

    return commit_sha


def cmd_log(repo, max_count=None):
    """Walk the commit history from HEAD. Returns a list of commit dicts."""
    sha = get_head(repo)
    commits = []
    count = 0

    while sha:
        if max_count is not None and count >= max_count:
            break
        _, data = read_object(repo, sha)
        info = parse_commit(data)
        info["sha"] = sha
        commits.append(info)
        sha = info.get("parent")
        count += 1

    return commits


def cmd_status(repo):
    """Compute the working tree status.

    Returns a dict with four lists:

    - ``staged``: files in index but not in HEAD commit (new or modified)
    - ``modified``: files in index that differ from working tree
    - ``deleted``: files in index but missing from working tree
    - ``untracked``: files in working tree but not in index
    """
    index = read_index(repo)

    # Get the tree from HEAD (if any commits exist)
    head_sha = get_head(repo)
    head_tree = {}
    if head_sha:
        _, commit_data = read_object(repo, head_sha)
        commit_info = parse_commit(commit_data)
        head_tree = tree_to_flat(repo, commit_info["tree"])

    # Collect working tree files
    work_files = set(collect_files(repo))

    staged = []     # In index, different from HEAD (or new)
    modified = []   # In index, but working tree differs
    deleted = []    # In index, but not in working tree
    untracked = []  # In working tree, but not in index

    # Compare index vs HEAD
    for path, sha in sorted(index.items()):
        if path not in head_tree or head_tree[path] != sha:
            staged.append(path)

    # Compare index vs working tree
    for path, sha in sorted(index.items()):
        full = os.path.join(repo, path)
        if not os.path.exists(full):
            deleted.append(path)
        else:
            with open(full, "rb") as f:
                current_data = f.read()
            current_sha = hash_object(repo, current_data, "blob", write=False)
            if current_sha != sha:
                modified.append(path)

    # Untracked files
    for path in sorted(work_files):
        if path not in index:
            untracked.append(path)

    return {
        "staged": staged,
        "modified": modified,
        "deleted": deleted,
        "untracked": untracked,
    }


def cmd_diff(repo):
    """Show a simple line-by-line diff of modified files (index vs working tree).

    Returns a list of ``(path, diff_lines)`` tuples.
    """
    index = read_index(repo)
    diffs = []

    for path, sha in sorted(index.items()):
        full = os.path.join(repo, path)
        if not os.path.exists(full):
            continue

        # Read the indexed version
        _, indexed_data = read_object(repo, sha)
        indexed_lines = indexed_data.decode(errors="replace").splitlines()

        # Read the working tree version
        with open(full, "rb") as f:
            work_data = f.read()
        work_lines = work_data.decode(errors="replace").splitlines()

        if indexed_lines == work_lines:
            continue

        # Simple diff: show removed and added lines using LCS
        diff_lines = _simple_diff(indexed_lines, work_lines, path)
        if diff_lines:
            diffs.append((path, diff_lines))

    return diffs


def _simple_diff(old_lines, new_lines, path):
    """Produce a minimal unified-style diff using longest common subsequence."""
    lcs = _lcs(old_lines, new_lines)
    lines = [f"--- a/{path}", f"+++ b/{path}"]

    i, j, k = 0, 0, 0
    while k < len(lcs):
        while i < len(old_lines) and old_lines[i] != lcs[k]:
            lines.append(f"- {old_lines[i]}")
            i += 1
        while j < len(new_lines) and new_lines[j] != lcs[k]:
            lines.append(f"+ {new_lines[j]}")
            j += 1
        lines.append(f"  {lcs[k]}")
        i += 1
        j += 1
        k += 1

    while i < len(old_lines):
        lines.append(f"- {old_lines[i]}")
        i += 1
    while j < len(new_lines):
        lines.append(f"+ {new_lines[j]}")
        j += 1

    return lines


def _lcs(a, b):
    """Compute the longest common subsequence of two lists."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to find the actual subsequence
    result = []
    i, j = m, n
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            result.append(a[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    return result[::-1]


def cmd_branch(repo, name=None):
    """Create a branch, or list branches if *name* is None.

    Creating a branch just writes the current HEAD SHA to
    ``.mini-git/refs/heads/<name>``.
    """
    if name is None:
        return list_branches(repo)

    head = get_head(repo)
    if head is None:
        raise RuntimeError("Cannot create branch: no commits yet")

    write_ref(repo, f"refs/heads/{name}", head)
    return name


def cmd_checkout(repo, target):
    """Switch branches or restore working tree from a commit.

    Steps:
    1. Resolve *target* to a SHA (branch name or raw SHA)
    2. Read the commit's tree
    3. Clear the working tree (except .mini-git)
    4. Write out the tree's files
    5. Update HEAD and the index
    """
    # Resolve target
    branch_ref = f"refs/heads/{target}"
    sha = read_ref(repo, branch_ref)

    if sha:
        # It's a branch name
        is_branch = True
    else:
        # Treat as a raw SHA
        sha = target
        is_branch = False

    # Read the commit
    obj_type, data = read_object(repo, sha)
    if obj_type != "commit":
        raise RuntimeError(f"Cannot checkout: {sha[:8]} is a {obj_type}, not a commit")

    commit_info = parse_commit(data)
    tree_files = tree_to_flat(repo, commit_info["tree"])

    # Clear working tree (except .mini-git)
    for path in collect_files(repo):
        os.remove(os.path.join(repo, path))
    # Remove empty directories
    for root, dirs, files in os.walk(repo, topdown=False):
        dirs[:] = [d for d in dirs if d != ".mini-git"]
        if not files and not dirs and root != repo:
            rel = os.path.relpath(root, repo)
            if not rel.startswith(".mini-git"):
                try:
                    os.rmdir(root)
                except OSError:
                    pass

    # Write out the tree
    for path, blob_sha in tree_files.items():
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        _, blob_data = read_object(repo, blob_sha)
        with open(full, "wb") as f:
            f.write(blob_data)

    # Update index
    write_index(repo, tree_files)

    # Update HEAD
    head_path = repo_path(repo, "HEAD")
    if is_branch:
        with open(head_path, "w") as f:
            f.write(f"ref: {branch_ref}\n")
    else:
        with open(head_path, "w") as f:
            f.write(sha + "\n")

    return sha


def cmd_tag(repo, name, sha=None):
    """Create a lightweight tag pointing to *sha* (default: HEAD)."""
    if sha is None:
        sha = get_head(repo)
    if sha is None:
        raise RuntimeError("Cannot create tag: no commits yet")
    write_ref(repo, f"refs/tags/{name}", sha)
    return name


def cmd_ls_tree(repo, tree_sha):
    """List the contents of a tree object."""
    _, data = read_object(repo, tree_sha)
    return parse_tree(data)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — demo
# ═══════════════════════════════════════════════════════════════════════════════

def _demo():
    """Run a self-contained demo that creates a repo, makes commits,
    branches, and shows the log — all in a temp directory."""
    import shutil
    import tempfile

    workdir = tempfile.mkdtemp(prefix="mini-git-demo-")

    try:
        print("Mini-Git — Python Edition")
        print("=" * 40)

        # ── init ──
        repo = cmd_init(workdir)
        print(f"\n  init: created repository at {workdir}")

        # ── first commit ──
        with open(os.path.join(repo, "hello.py"), "w") as f:
            f.write('print("hello, world!")\n')

        with open(os.path.join(repo, "README.md"), "w") as f:
            f.write("# My Project\n\nA demo project.\n")

        cmd_add(repo, "hello.py", "README.md")
        sha1 = cmd_commit(repo, "Initial commit", timestamp=1700000000)
        print(f"\n  commit 1: {sha1[:8]}  Initial commit")
        print(f"    branch: {get_branch_name(repo)}")

        # ── status (clean) ──
        status = cmd_status(repo)
        print(f"\n  status: {status}")

        # ── modify a file ──
        with open(os.path.join(repo, "hello.py"), "w") as f:
            f.write('import sys\nprint(f"hello, {sys.argv[1]}!")\n')

        status = cmd_status(repo)
        print(f"\n  (modified hello.py)")
        print(f"  status: modified={status['modified']}")

        # ── diff ──
        diffs = cmd_diff(repo)
        if diffs:
            print(f"\n  diff:")
            for path, lines in diffs:
                for line in lines:
                    print(f"    {line}")

        # ── second commit ──
        cmd_add(repo, "hello.py")
        sha2 = cmd_commit(repo, "Add CLI argument support", timestamp=1700001000)
        print(f"\n  commit 2: {sha2[:8]}  Add CLI argument support")

        # ── add a subdirectory ──
        os.makedirs(os.path.join(repo, "lib"))
        with open(os.path.join(repo, "lib", "util.py"), "w") as f:
            f.write("def greet(name):\n    return f'hello, {name}!'\n")

        cmd_add(repo, "lib")
        sha3 = cmd_commit(repo, "Add lib/util.py helper", timestamp=1700002000)
        print(f"\n  commit 3: {sha3[:8]}  Add lib/util.py helper")

        # ── create a branch ──
        cmd_branch(repo, "feature")
        branches = cmd_branch(repo)
        print(f"\n  branches: {branches}")

        # ── log ──
        print(f"\n  log:")
        for c in cmd_log(repo):
            print(f"    {c['sha'][:8]}  {c['message']}")

        # ── tag ──
        cmd_tag(repo, "v0.1")
        tag_sha = read_ref(repo, "refs/tags/v0.1")
        print(f"\n  tag v0.1 → {tag_sha[:8]}")

        # ── checkout the first commit ──
        cmd_checkout(repo, sha1)
        files = collect_files(repo)
        print(f"\n  checkout {sha1[:8]}:")
        print(f"    files: {files}")
        with open(os.path.join(repo, "hello.py")) as f:
            print(f"    hello.py: {f.read().strip()!r}")

        # ── checkout back to main ──
        cmd_checkout(repo, "main")
        files = collect_files(repo)
        print(f"\n  checkout main:")
        print(f"    files: {files}")
        with open(os.path.join(repo, "hello.py")) as f:
            print(f"    hello.py: {f.read().strip()!r}")

        # ── show object internals ──
        print(f"\n  Object store:")
        obj_type, data = cmd_cat_file(repo, sha3)
        print(f"    commit {sha3[:8]}:")
        for line in data.decode().split("\n")[:4]:
            print(f"      {line}")

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n  (cleaned up {workdir})")
    print("  Done.")


if __name__ == "__main__":
    _demo()
