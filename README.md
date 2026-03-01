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
├── LICENSE
└── README.md
```

Each module has its own directory with:
- A **README** explaining the concept and crediting the original source
- A **Python implementation** you can read and run

## Getting Started

Pick any module that interests you, read its README for context, then dive into the code. Each implementation is self-contained and designed to be understood on its own.

## License

This project is released under [CC0 1.0 Universal](LICENSE) — public domain. See individual module READMEs for attribution to original authors and sources.
