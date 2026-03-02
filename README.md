# Under All Hoods

A collection of code files and explanations to help you understand what's going on **under the hood** of everything interesting.

## About

Ever wondered how a search engine finds results so fast, how programming languages understand your code, or how a compiler transforms source into something a machine can run? This repository breaks down complex systems into small, readable implementations — each one based on real-world educational resources and attributed to the original authors.

The goal is simple: **read the code, understand the concept.** No frameworks, no bloat — just the core ideas laid bare.

## Modules

| Module | Description | Based On |
|--------|-------------|----------|
| [Search Engine](search-engine/) | A minimal search engine in Python | [A search engine in 80 lines of Python](https://www.alexmolas.com/2024/02/05/a-search-engine-in-80-lines.html) |
| [Language Interpreter](language-interpreter/) | A Lisp interpreter written in Python | [How to Write a (Lisp) Interpreter (in Python)](https://www.norvig.com/lispy.html) |
| [Language Compiler](language-compiler/) | A super tiny JavaScript compiler | [the-super-tiny-compiler](https://github.com/jamiebuilds/the-super-tiny-compiler) |
| [Key-Value Store](key-value-store/) | A mini Redis server with RESP protocol | [Building a simple Redis server with Python](http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/) |
| [Version Control](version-control/) | A mini Git with content-addressable storage | [ugit: Learn Git Internals by Building Git Yourself](https://www.leshenko.net/p/ugit/) |

## Repository Structure

```
under-all-hoods/
├── search-engine/
│   ├── README.md
│   └── search-engine-alexmolas.py
├── language-interpreter/
│   ├── README.md
│   ├── lisp-interpreter-norvig.py
│   └── test_interpreter.py
├── language-compiler/
│   ├── README.md
│   ├── tiny-compiler.py
│   └── test_compiler.py
├── key-value-store/
│   ├── README.md
│   ├── mini-redis.py
│   └── test_redis.py
├── version-control/
│   ├── README.md
│   ├── mini-git.py
│   └── test_git.py
├── LICENSE
└── README.md
```

Each module has its own directory with:
- A **README** explaining the concept and crediting the original source
- A **Python implementation** you can read and run

## Roadmap

Planned modules, ranked by developer interest and educational value:

### Tier 1: Most Popular

| Module | Description | Key Concepts | Reference |
|--------|-------------|--------------|-----------|
| Database (SQLite) | A simple relational database | B-Tree indexing, SQL parsing, storage engine, ACID | [DBDB: Dog Bed Database](http://aosabook.org/en/500L/dbdb-dog-bed-database.html) |

### Tier 2: Very Popular

| Module | Description | Key Concepts | Reference |
|--------|-------------|--------------|-----------|
| Web Server | An HTTP server from scratch | HTTP protocol, socket programming, routing, concurrency | [A Simple Web Server — 500 Lines or Less](https://aosabook.org/en/500L/a-simple-web-server.html) |
| Regex Engine | A regular expression engine | NFA/DFA, Thompson's construction, finite automata | [Regular Expression Matching Can Be Simple And Fast](https://swtch.com/~rsc/regexp/regexp1.html) |
| Container Runtime | A Docker-like container runtime | Linux namespaces, cgroups, chroot, process isolation | [Rubber Docker](https://github.com/Fewbytes/rubber-docker) |

### Tier 3: Classic & Practical

| Module | Description | Key Concepts | Reference |
|--------|-------------|--------------|-----------|
| Shell | A Unix shell | fork/exec, pipes, I/O redirection, signal handling | [Write a Shell in Python](https://danishpraka.sh/posts/write-a-shell/) |
| DNS Resolver | A DNS resolver from scratch | DNS protocol, UDP, recursive resolution, caching | [Implement DNS in a Weekend](https://implement-dns.wizardzines.com/) |
| Template Engine | A Jinja-like template engine | Template parsing, code generation, sandbox execution | [A Template Engine — 500 Lines or Less](https://aosabook.org/en/500L/a-template-engine.html) |
| Diff Tool | A diff algorithm implementation | Myers diff algorithm, LCS, dynamic programming | [The Myers Diff Algorithm](https://blog.robertelder.org/diff-algorithm/) |

## Getting Started

Pick any module that interests you, read its README for context, then dive into the code. Each implementation is self-contained and designed to be understood on its own.

## License

This project is released under [CC0 1.0 Universal](LICENSE) — public domain. See individual module READMEs for attribution to original authors and sources.
