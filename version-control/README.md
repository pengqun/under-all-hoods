# Version Control (Git): Under the Hood

How does Git track every version of every file you've ever committed? This module implements a mini version control system from scratch, covering content-addressable storage, the object model (blobs, trees, commits), a staging area, branches, and checkout — all in a single file.

## What it Does

This is a working version control system that you can init, add, commit, branch, and checkout with:

```
COMMAND                                 RESULT
───────                                 ──────
init                               →    Create .mini-git/ repository
add hello.py README.md             →    Stage files for commit
commit "Initial commit"            →    Create snapshot  92872f49
log                                →    92872f49  Initial commit
branch feature                     →    Create branch at current commit
checkout feature                   →    Switch to feature branch
```

## The Three Core Ideas

### Idea 1: Content-Addressable Storage

Every piece of data Git stores — files, directories, commits — goes through the same pipeline:

```
raw data  →  prepend header  →  SHA-1 hash  →  zlib compress  →  store on disk
                  │                  │                                  │
          "blob 12\0hello"    →  af3b1c...                  →  .mini-git/objects/af/3b1c...
```

The SHA-1 hash becomes the object's **name**. Same content always produces the same hash, so identical files are stored only once. This is why Git is so space-efficient.

### Idea 2: Three Object Types

Git's entire data model is built from just three types of objects:

| Object | What it stores | Analogy |
|--------|----------------|---------|
| **Blob** | Raw file contents | A file |
| **Tree** | List of (mode, name, sha) entries | A directory listing |
| **Commit** | Tree ref + parent ref + author + message | A snapshot with history |

They compose like this:

```
commit a1f3...
├── tree: 7c2e...
│   ├── 100644 README.md  →  blob 789a...
│   ├── 100644 hello.py   →  blob af3b...
│   └── 40000  lib/       →  tree 5d1e...
│       └── 100644 util.py → blob b2c4...
└── parent: 92872f49...    (previous commit)
```

A commit points to a tree. A tree points to blobs (files) and other trees (subdirectories). Every SHA depends on its content, which depends on its children's content — so changing one file changes every SHA up to the root commit. This is a **Merkle tree**, the same structure behind Bitcoin and blockchain.

### Idea 3: Refs Are Just Files Containing SHAs

A branch is just a file containing a 40-character SHA:

```
.mini-git/refs/heads/main      →  "a1f3c2..."
.mini-git/refs/heads/feature   →  "7b8d4e..."
.mini-git/HEAD                 →  "ref: refs/heads/main"
```

Creating a branch = writing a new file. Switching branches = changing what HEAD points to and restoring the commit's tree. That's it. No copying, no complex data structures — just a pointer.

## The Staging Area (Index)

Between your working directory and the object store sits the **index** — a list of `(path, blob_sha)` pairs representing what will go into the next commit:

```
Working Directory         Index               Object Store
     │                      │                       │
     │── git add ──→        │                       │
     │                      │── git commit ──→      │
     │                      │                       │
```

When you `add` a file, its content is hashed into a blob and the index is updated. When you `commit`, the index is converted into tree objects and a commit object is created. This two-step process is what lets you commit only some of your changes.

## Running It

```bash
cd version-control
python mini-git.py
```

Output:

```
Mini-Git — Python Edition
========================================

  init: created repository at /tmp/mini-git-demo-...

  commit 1: 92872f49  Initial commit
    branch: main

  status: {'staged': [], 'modified': [], 'deleted': [], 'untracked': []}

  (modified hello.py)
  status: modified=['hello.py']

  diff:
    --- a/hello.py
    +++ b/hello.py
    - print("hello, world!")
    + import sys
    + print(f"hello, {sys.argv[1]}!")

  commit 2: 195ff95d  Add CLI argument support

  commit 3: cf72ca51  Add lib/util.py helper

  branches: ['feature', 'main']

  log:
    cf72ca51  Add lib/util.py helper
    195ff95d  Add CLI argument support
    92872f49  Initial commit

  tag v0.1 → cf72ca51

  checkout 92872f49:
    files: ['README.md', 'hello.py']
    hello.py: 'print("hello, world!")'

  checkout main:
    files: ['README.md', 'hello.py', 'lib/util.py']
    hello.py: 'import sys\nprint(f"hello, {sys.argv[1]}!")'

  Object store:
    commit cf72ca51:
      tree b0e11848ff3b1760e4602817fa89885fd1907571
      parent 195ff95d32f0b88af74045232ede38ce3eabb853
      author Mini-Git User <user@mini-git> 1700002000 +0000
      committer Mini-Git User <user@mini-git> 1700002000 +0000

  (cleaned up /tmp/mini-git-demo-...)
  Done.
```

## Running Tests

```bash
cd version-control
python -m pytest test_git.py -v
```

The test suite covers each layer in isolation plus end-to-end workflow tests — 77 test cases covering the object store, tree/commit parsing, index operations, refs, and all porcelain commands.

## Implementation: `mini-git.py`

### References

- [ugit: Learn Git Internals by Building Git Yourself](https://www.leshenko.net/p/ugit/) by Nikita Leshenko — the tutorial this implementation draws from
- [Write yourself a Git!](https://wyag.thb.lt/) by Thibault Polge — another excellent "build Git from scratch" guide
- [Git Internals - Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects) — the official Pro Git book chapter on how objects work
