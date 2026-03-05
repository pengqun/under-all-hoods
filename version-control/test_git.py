"""
Tests for Mini-Git
===================

Organized by layer so failures point directly to the broken component.
Run with: python -m pytest test_git.py -v
     or:  python test_git.py
"""

import os
import shutil
import sys
import tempfile
import time

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the module (filename has a hyphen) ────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "mini-git.py")
_loader = SourceFileLoader("mini_git", _path)
_spec = spec_from_loader("mini_git", _loader)
git_module = module_from_spec(_spec)
sys.modules["mini_git"] = git_module
_loader.exec_module(git_module)

hash_object = git_module.hash_object
read_object = git_module.read_object
make_tree = git_module.make_tree
parse_tree = git_module.parse_tree
make_commit = git_module.make_commit
parse_commit = git_module.parse_commit
read_index = git_module.read_index
write_index = git_module.write_index
build_tree_from_index = git_module.build_tree_from_index
read_ref = git_module.read_ref
write_ref = git_module.write_ref
get_head = git_module.get_head
get_head_ref = git_module.get_head_ref
get_branch_name = git_module.get_branch_name
list_branches = git_module.list_branches
collect_files = git_module.collect_files
tree_to_flat = git_module.tree_to_flat
cmd_init = git_module.cmd_init
cmd_hash_object = git_module.cmd_hash_object
cmd_cat_file = git_module.cmd_cat_file
cmd_add = git_module.cmd_add
cmd_rm = git_module.cmd_rm
cmd_commit = git_module.cmd_commit
cmd_log = git_module.cmd_log
cmd_status = git_module.cmd_status
cmd_diff = git_module.cmd_diff
cmd_branch = git_module.cmd_branch
cmd_checkout = git_module.cmd_checkout
cmd_tag = git_module.cmd_tag
cmd_ls_tree = git_module.cmd_ls_tree
repo_path = git_module.repo_path


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def repo(tmp_path):
    """Create and return a fresh mini-git repository in a temp directory."""
    return cmd_init(str(tmp_path / "repo"))


def _write_file(repo, path, content):
    """Helper: write a file in the repo."""
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def _read_file(repo, path):
    """Helper: read a file from the repo."""
    with open(os.path.join(repo, path)) as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════════════════════
# OBJECT STORE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestObjectStore:
    """Tests for hash_object and read_object."""

    def test_hash_blob(self, repo):
        sha = hash_object(repo, b"hello world", "blob")
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_read_blob(self, repo):
        data = b"hello world"
        sha = hash_object(repo, data, "blob")
        obj_type, obj_data = read_object(repo, sha)
        assert obj_type == "blob"
        assert obj_data == data

    def test_same_content_same_sha(self, repo):
        sha1 = hash_object(repo, b"same", "blob")
        sha2 = hash_object(repo, b"same", "blob")
        assert sha1 == sha2

    def test_different_content_different_sha(self, repo):
        sha1 = hash_object(repo, b"alpha", "blob")
        sha2 = hash_object(repo, b"beta", "blob")
        assert sha1 != sha2

    def test_different_types_different_sha(self, repo):
        sha1 = hash_object(repo, b"data", "blob")
        sha2 = hash_object(repo, b"data", "commit")
        assert sha1 != sha2

    def test_empty_blob(self, repo):
        sha = hash_object(repo, b"", "blob")
        obj_type, data = read_object(repo, sha)
        assert obj_type == "blob"
        assert data == b""

    def test_hash_without_write(self, repo):
        sha = hash_object(repo, b"ephemeral", "blob", write=False)
        assert len(sha) == 40
        # Object should NOT exist on disk
        obj_path = repo_path(repo, "objects", sha[:2], sha[2:])
        assert not os.path.exists(obj_path)

    def test_binary_data(self, repo):
        data = bytes(range(256))
        sha = hash_object(repo, data, "blob")
        _, result = read_object(repo, sha)
        assert result == data


# ═══════════════════════════════════════════════════════════════════════════════
# TREE OBJECT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTreeObjects:
    """Tests for make_tree and parse_tree."""

    def test_single_entry(self, repo):
        sha = hash_object(repo, b"content", "blob")
        tree_data = make_tree([("100644", "file.txt", sha)])
        entries = parse_tree(tree_data)
        assert entries == [("100644", "file.txt", sha)]

    def test_multiple_entries(self, repo):
        sha1 = hash_object(repo, b"aaa", "blob")
        sha2 = hash_object(repo, b"bbb", "blob")
        tree_data = make_tree([
            ("100644", "b.txt", sha2),
            ("100644", "a.txt", sha1),
        ])
        entries = parse_tree(tree_data)
        # Entries are sorted by name
        assert entries[0][1] == "a.txt"
        assert entries[1][1] == "b.txt"

    def test_roundtrip(self, repo):
        sha1 = hash_object(repo, b"x", "blob")
        sha2 = hash_object(repo, b"y", "blob")
        original = [
            ("100644", "foo.py", sha1),
            ("40000", "lib", sha2),
        ]
        tree_data = make_tree(original)
        parsed = parse_tree(tree_data)
        assert parsed == sorted(original, key=lambda e: e[1])

    def test_store_and_read_tree(self, repo):
        sha1 = hash_object(repo, b"data", "blob")
        tree_data = make_tree([("100644", "f.txt", sha1)])
        tree_sha = hash_object(repo, tree_data, "tree")

        obj_type, data = read_object(repo, tree_sha)
        assert obj_type == "tree"
        entries = parse_tree(data)
        assert entries == [("100644", "f.txt", sha1)]


# ═══════════════════════════════════════════════════════════════════════════════
# COMMIT OBJECT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommitObjects:
    """Tests for make_commit and parse_commit."""

    def test_root_commit(self, repo):
        data = make_commit("abc123", None, "Initial commit",
                           author="Test <t@t>", timestamp=1000)
        info = parse_commit(data)
        assert info["tree"] == "abc123"
        assert info["parent"] is None
        assert info["message"] == "Initial commit"
        assert "Test <t@t>" in info["author"]

    def test_commit_with_parent(self, repo):
        data = make_commit("tree1", "parent1", "Second",
                           author="A <a@a>", timestamp=2000)
        info = parse_commit(data)
        assert info["tree"] == "tree1"
        assert info["parent"] == "parent1"
        assert info["message"] == "Second"

    def test_multiline_message(self, repo):
        msg = "Line one\n\nLine three\nLine four"
        data = make_commit("t", None, msg,
                           author="A <a@a>", timestamp=1000)
        info = parse_commit(data)
        assert info["message"] == msg

    def test_store_and_read_commit(self, repo):
        commit_data = make_commit("treesha", None, "hello",
                                  author="A <a@a>", timestamp=1000)
        sha = hash_object(repo, commit_data, "commit")
        obj_type, data = read_object(repo, sha)
        assert obj_type == "commit"
        info = parse_commit(data)
        assert info["message"] == "hello"


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestIndex:
    """Tests for the staging area (index)."""

    def test_empty_index(self, repo):
        assert read_index(repo) == {}

    def test_write_and_read(self, repo):
        index = {"a.txt": "sha1", "b.txt": "sha2"}
        write_index(repo, index)
        assert read_index(repo) == index

    def test_sorted_output(self, repo):
        index = {"z.txt": "sha1", "a.txt": "sha2"}
        write_index(repo, index)
        result = read_index(repo)
        assert list(result.keys()) == ["a.txt", "z.txt"]

    def test_build_tree_flat(self, repo):
        sha1 = hash_object(repo, b"aaa", "blob")
        sha2 = hash_object(repo, b"bbb", "blob")
        index = {"a.txt": sha1, "b.txt": sha2}

        tree_sha = build_tree_from_index(repo, index)
        entries = parse_tree(read_object(repo, tree_sha)[1])
        assert len(entries) == 2
        assert entries[0] == ("100644", "a.txt", sha1)
        assert entries[1] == ("100644", "b.txt", sha2)

    def test_build_tree_nested(self, repo):
        sha1 = hash_object(repo, b"aaa", "blob")
        sha2 = hash_object(repo, b"bbb", "blob")
        index = {"README.md": sha1, "src/main.py": sha2}

        tree_sha = build_tree_from_index(repo, index)
        entries = parse_tree(read_object(repo, tree_sha)[1])

        names = [e[1] for e in entries]
        assert "README.md" in names
        assert "src" in names

        # The "src" entry should be a subtree
        src_entry = [e for e in entries if e[1] == "src"][0]
        assert src_entry[0] == "40000"

    def test_tree_to_flat_roundtrip(self, repo):
        sha1 = hash_object(repo, b"x", "blob")
        sha2 = hash_object(repo, b"y", "blob")
        original = {"a.txt": sha1, "dir/b.txt": sha2}

        tree_sha = build_tree_from_index(repo, original)
        flat = tree_to_flat(repo, tree_sha)
        assert flat == original


# ═══════════════════════════════════════════════════════════════════════════════
# REFS TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRefs:
    """Tests for references (branches, HEAD)."""

    def test_write_and_read_ref(self, repo):
        write_ref(repo, "refs/heads/main", "abc123")
        assert read_ref(repo, "refs/heads/main") == "abc123"

    def test_read_missing_ref(self, repo):
        assert read_ref(repo, "refs/heads/nope") is None

    def test_symbolic_ref(self, repo):
        """HEAD is a symbolic ref pointing to refs/heads/main."""
        write_ref(repo, "refs/heads/main", "abc123")
        # HEAD is already set to "ref: refs/heads/main" by init
        assert get_head(repo) == "abc123"

    def test_head_ref(self, repo):
        assert get_head_ref(repo) == "refs/heads/main"

    def test_branch_name(self, repo):
        assert get_branch_name(repo) == "main"

    def test_empty_head(self, repo):
        """HEAD on a fresh repo with no commits returns None."""
        assert get_head(repo) is None


# ═══════════════════════════════════════════════════════════════════════════════
# INIT COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdInit:
    """Tests for cmd_init."""

    def test_creates_structure(self, tmp_path):
        repo = cmd_init(str(tmp_path / "new"))
        assert os.path.isdir(os.path.join(repo, ".mini-git"))
        assert os.path.isdir(os.path.join(repo, ".mini-git", "objects"))
        assert os.path.isdir(os.path.join(repo, ".mini-git", "refs", "heads"))
        assert os.path.isfile(os.path.join(repo, ".mini-git", "HEAD"))

    def test_head_content(self, tmp_path):
        repo = cmd_init(str(tmp_path / "new"))
        with open(os.path.join(repo, ".mini-git", "HEAD")) as f:
            assert f.read().strip() == "ref: refs/heads/main"

    def test_double_init_raises(self, repo):
        with pytest.raises(RuntimeError, match="Already"):
            cmd_init(repo)


# ═══════════════════════════════════════════════════════════════════════════════
# ADD COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdAdd:
    """Tests for cmd_add."""

    def test_add_single_file(self, repo):
        _write_file(repo, "a.txt", "hello")
        index = cmd_add(repo, "a.txt")
        assert "a.txt" in index

    def test_add_multiple_files(self, repo):
        _write_file(repo, "a.txt", "aaa")
        _write_file(repo, "b.txt", "bbb")
        index = cmd_add(repo, "a.txt", "b.txt")
        assert "a.txt" in index
        assert "b.txt" in index

    def test_add_directory(self, repo):
        _write_file(repo, "src/main.py", "main")
        _write_file(repo, "src/util.py", "util")
        index = cmd_add(repo, "src")
        assert "src/main.py" in index
        assert "src/util.py" in index

    def test_add_nonexistent_raises(self, repo):
        with pytest.raises(FileNotFoundError):
            cmd_add(repo, "nope.txt")

    def test_add_updates_existing(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        sha1 = read_index(repo)["a.txt"]

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        sha2 = read_index(repo)["a.txt"]

        assert sha1 != sha2

    def test_add_stores_blob(self, repo):
        _write_file(repo, "a.txt", "content")
        cmd_add(repo, "a.txt")
        sha = read_index(repo)["a.txt"]
        obj_type, data = read_object(repo, sha)
        assert obj_type == "blob"
        assert data == b"content"


# ═══════════════════════════════════════════════════════════════════════════════
# RM COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdRm:
    """Tests for cmd_rm."""

    def test_rm_staged_file(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        removed = cmd_rm(repo, "a.txt")
        assert removed == ["a.txt"]
        assert read_index(repo) == {}

    def test_rm_nonexistent(self, repo):
        removed = cmd_rm(repo, "nope.txt")
        assert removed == []


# ═══════════════════════════════════════════════════════════════════════════════
# COMMIT COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdCommit:
    """Tests for cmd_commit."""

    def test_first_commit(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha = cmd_commit(repo, "First", timestamp=1000)

        assert len(sha) == 40
        obj_type, data = read_object(repo, sha)
        assert obj_type == "commit"
        info = parse_commit(data)
        assert info["message"] == "First"
        assert info["parent"] is None

    def test_commit_updates_head(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha = cmd_commit(repo, "First", timestamp=1000)
        assert get_head(repo) == sha

    def test_second_commit_has_parent(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        sha1 = cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        sha2 = cmd_commit(repo, "Second", timestamp=2000)

        _, data = read_object(repo, sha2)
        info = parse_commit(data)
        assert info["parent"] == sha1

    def test_commit_empty_index_raises(self, repo):
        with pytest.raises(RuntimeError, match="Nothing to commit"):
            cmd_commit(repo, "empty")

    def test_commit_tree_structure(self, repo):
        _write_file(repo, "a.txt", "aaa")
        _write_file(repo, "dir/b.txt", "bbb")
        cmd_add(repo, "a.txt", "dir/b.txt")
        sha = cmd_commit(repo, "Structured", timestamp=1000)

        _, data = read_object(repo, sha)
        info = parse_commit(data)
        flat = tree_to_flat(repo, info["tree"])
        assert "a.txt" in flat
        assert "dir/b.txt" in flat


# ═══════════════════════════════════════════════════════════════════════════════
# LOG COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdLog:
    """Tests for cmd_log."""

    def test_log_empty_repo(self, repo):
        assert cmd_log(repo) == []

    def test_log_single_commit(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha = cmd_commit(repo, "First", timestamp=1000)

        log = cmd_log(repo)
        assert len(log) == 1
        assert log[0]["sha"] == sha
        assert log[0]["message"] == "First"

    def test_log_multiple_commits(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Second", timestamp=2000)

        _write_file(repo, "a.txt", "v3")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Third", timestamp=3000)

        log = cmd_log(repo)
        assert len(log) == 3
        assert log[0]["message"] == "Third"
        assert log[1]["message"] == "Second"
        assert log[2]["message"] == "First"

    def test_log_max_count(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Second", timestamp=2000)

        log = cmd_log(repo, max_count=1)
        assert len(log) == 1
        assert log[0]["message"] == "Second"


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdStatus:
    """Tests for cmd_status."""

    def test_clean_after_commit(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)

        status = cmd_status(repo)
        assert status["staged"] == []
        assert status["modified"] == []
        assert status["deleted"] == []
        assert status["untracked"] == []

    def test_untracked_file(self, repo):
        _write_file(repo, "a.txt", "hello")
        status = cmd_status(repo)
        assert status["untracked"] == ["a.txt"]

    def test_staged_file(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        status = cmd_status(repo)
        assert status["staged"] == ["a.txt"]

    def test_modified_file(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        status = cmd_status(repo)
        assert status["modified"] == ["a.txt"]

    def test_deleted_file(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)
        os.remove(os.path.join(repo, "a.txt"))

        status = cmd_status(repo)
        assert status["deleted"] == ["a.txt"]

    def test_mixed_status(self, repo):
        _write_file(repo, "committed.txt", "c")
        _write_file(repo, "to_modify.txt", "v1")
        cmd_add(repo, "committed.txt", "to_modify.txt")
        cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "to_modify.txt", "v2")
        _write_file(repo, "new_staged.txt", "staged")
        cmd_add(repo, "new_staged.txt")
        _write_file(repo, "untracked.txt", "u")

        status = cmd_status(repo)
        assert "new_staged.txt" in status["staged"]
        assert "to_modify.txt" in status["modified"]
        assert "untracked.txt" in status["untracked"]


# ═══════════════════════════════════════════════════════════════════════════════
# DIFF COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdDiff:
    """Tests for cmd_diff."""

    def test_no_diff_clean(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        assert cmd_diff(repo) == []

    def test_diff_modified(self, repo):
        _write_file(repo, "a.txt", "line1\nline2\n")
        cmd_add(repo, "a.txt")

        _write_file(repo, "a.txt", "line1\nchanged\n")
        diffs = cmd_diff(repo)
        assert len(diffs) == 1
        path, lines = diffs[0]
        assert path == "a.txt"
        # Should show removed and added lines
        assert any("- line2" in line for line in lines)
        assert any("+ changed" in line for line in lines)

    def test_diff_added_lines(self, repo):
        _write_file(repo, "a.txt", "line1\n")
        cmd_add(repo, "a.txt")

        _write_file(repo, "a.txt", "line1\nline2\n")
        diffs = cmd_diff(repo)
        assert len(diffs) == 1
        _, lines = diffs[0]
        assert any("+ line2" in line for line in lines)

    def test_diff_removed_lines(self, repo):
        _write_file(repo, "a.txt", "line1\nline2\n")
        cmd_add(repo, "a.txt")

        _write_file(repo, "a.txt", "line1\n")
        diffs = cmd_diff(repo)
        assert len(diffs) == 1
        _, lines = diffs[0]
        assert any("- line2" in line for line in lines)


# ═══════════════════════════════════════════════════════════════════════════════
# BRANCH COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdBranch:
    """Tests for cmd_branch."""

    def test_list_branches_initial(self, repo):
        """Before any commits, main doesn't have a ref file yet."""
        assert cmd_branch(repo) == []

    def test_list_branches_after_commit(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)
        assert cmd_branch(repo) == ["main"]

    def test_create_branch(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "First", timestamp=1000)

        cmd_branch(repo, "feature")
        branches = cmd_branch(repo)
        assert "main" in branches
        assert "feature" in branches

    def test_create_branch_no_commits_raises(self, repo):
        with pytest.raises(RuntimeError, match="no commits"):
            cmd_branch(repo, "feature")

    def test_branch_points_to_head(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha = cmd_commit(repo, "First", timestamp=1000)

        cmd_branch(repo, "feature")
        assert read_ref(repo, "refs/heads/feature") == sha


# ═══════════════════════════════════════════════════════════════════════════════
# CHECKOUT COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdCheckout:
    """Tests for cmd_checkout."""

    def test_checkout_branch(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        sha1 = cmd_commit(repo, "First", timestamp=1000)

        cmd_branch(repo, "feature")

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        sha2 = cmd_commit(repo, "Second on main", timestamp=2000)

        # Switch to feature (which still points to sha1)
        cmd_checkout(repo, "feature")
        assert _read_file(repo, "a.txt") == "v1"
        assert get_branch_name(repo) == "feature"

        # Switch back to main
        cmd_checkout(repo, "main")
        assert _read_file(repo, "a.txt") == "v2"
        assert get_branch_name(repo) == "main"

    def test_checkout_sha(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        sha1 = cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Second", timestamp=2000)

        cmd_checkout(repo, sha1)
        assert _read_file(repo, "a.txt") == "v1"
        # Detached HEAD
        assert get_branch_name(repo) is None

    def test_checkout_restores_files(self, repo):
        _write_file(repo, "a.txt", "aaa")
        _write_file(repo, "b.txt", "bbb")
        cmd_add(repo, "a.txt", "b.txt")
        sha1 = cmd_commit(repo, "Two files", timestamp=1000)

        _write_file(repo, "c.txt", "ccc")
        cmd_add(repo, "c.txt")
        sha2 = cmd_commit(repo, "Three files", timestamp=2000)

        cmd_checkout(repo, sha1)
        assert os.path.exists(os.path.join(repo, "a.txt"))
        assert os.path.exists(os.path.join(repo, "b.txt"))
        assert not os.path.exists(os.path.join(repo, "c.txt"))

    def test_checkout_updates_index(self, repo):
        _write_file(repo, "a.txt", "v1")
        cmd_add(repo, "a.txt")
        sha1 = cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Second", timestamp=2000)

        cmd_checkout(repo, sha1)
        index = read_index(repo)
        assert "a.txt" in index

    def test_checkout_subdirectory(self, repo):
        _write_file(repo, "src/main.py", "main")
        cmd_add(repo, "src/main.py")
        sha1 = cmd_commit(repo, "With src", timestamp=1000)

        cmd_checkout(repo, sha1)
        assert _read_file(repo, "src/main.py") == "main"

    def test_checkout_non_commit_raises(self, repo):
        sha = hash_object(repo, b"not a commit", "blob")
        with pytest.raises(RuntimeError, match="not a commit"):
            cmd_checkout(repo, sha)


# ═══════════════════════════════════════════════════════════════════════════════
# TAG COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdTag:
    """Tests for cmd_tag."""

    def test_create_tag(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha = cmd_commit(repo, "First", timestamp=1000)

        cmd_tag(repo, "v1.0")
        assert read_ref(repo, "refs/tags/v1.0") == sha

    def test_tag_specific_sha(self, repo):
        _write_file(repo, "a.txt", "hello")
        cmd_add(repo, "a.txt")
        sha1 = cmd_commit(repo, "First", timestamp=1000)

        _write_file(repo, "a.txt", "v2")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Second", timestamp=2000)

        cmd_tag(repo, "old", sha1)
        assert read_ref(repo, "refs/tags/old") == sha1

    def test_tag_no_commits_raises(self, repo):
        with pytest.raises(RuntimeError, match="no commits"):
            cmd_tag(repo, "v1.0")


# ═══════════════════════════════════════════════════════════════════════════════
# HASH-OBJECT & CAT-FILE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdHashObjectCatFile:
    """Tests for cmd_hash_object and cmd_cat_file."""

    def test_hash_and_cat(self, repo):
        _write_file(repo, "a.txt", "hello world")
        sha = cmd_hash_object(repo, "a.txt")
        obj_type, data = cmd_cat_file(repo, sha)
        assert obj_type == "blob"
        assert data == b"hello world"


# ═══════════════════════════════════════════════════════════════════════════════
# LS-TREE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdLsTree:
    """Tests for cmd_ls_tree."""

    def test_ls_tree(self, repo):
        _write_file(repo, "a.txt", "aaa")
        _write_file(repo, "b.txt", "bbb")
        cmd_add(repo, "a.txt", "b.txt")
        sha = cmd_commit(repo, "Two files", timestamp=1000)

        _, data = read_object(repo, sha)
        tree_sha = parse_commit(data)["tree"]

        entries = cmd_ls_tree(repo, tree_sha)
        names = [e[1] for e in entries]
        assert "a.txt" in names
        assert "b.txt" in names


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full workflow integration tests."""

    def test_full_workflow(self, repo):
        """init → add → commit → modify → add → commit → log → checkout."""
        # First commit
        _write_file(repo, "main.py", "print('v1')\n")
        cmd_add(repo, "main.py")
        sha1 = cmd_commit(repo, "v1", timestamp=1000)

        # Second commit
        _write_file(repo, "main.py", "print('v2')\n")
        cmd_add(repo, "main.py")
        sha2 = cmd_commit(repo, "v2", timestamp=2000)

        # Log shows both
        log = cmd_log(repo)
        assert len(log) == 2

        # Checkout v1
        cmd_checkout(repo, sha1)
        assert _read_file(repo, "main.py") == "print('v1')\n"

        # Checkout back to main
        cmd_checkout(repo, "main")
        assert _read_file(repo, "main.py") == "print('v2')\n"

    def test_branch_divergence(self, repo):
        """Two branches with different content."""
        _write_file(repo, "a.txt", "shared")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Base", timestamp=1000)

        # Create feature branch
        cmd_branch(repo, "feature")

        # Commit on main
        _write_file(repo, "a.txt", "main version")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Main change", timestamp=2000)

        # Switch to feature and commit
        cmd_checkout(repo, "feature")
        assert _read_file(repo, "a.txt") == "shared"

        _write_file(repo, "a.txt", "feature version")
        cmd_add(repo, "a.txt")
        cmd_commit(repo, "Feature change", timestamp=3000)

        assert _read_file(repo, "a.txt") == "feature version"

        # Switch back to main
        cmd_checkout(repo, "main")
        assert _read_file(repo, "a.txt") == "main version"

    def test_object_integrity(self, repo):
        """Objects are content-addressable: same content = same SHA."""
        _write_file(repo, "a.txt", "identical")
        _write_file(repo, "b.txt", "identical")
        cmd_add(repo, "a.txt", "b.txt")

        index = read_index(repo)
        # Both files have the same content, so same blob SHA
        assert index["a.txt"] == index["b.txt"]


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
