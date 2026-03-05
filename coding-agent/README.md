# Coding Agent: Under the Hood

How does a coding agent like Claude Code turn natural-language instructions into executed code changes? This module implements a mini coding agent from scratch, covering raw HTTP calls to an LLM API, a tool-dispatch system, path sandboxing, and the core agent loop — all in a single file using only the Python standard library.

## What it Does

You give it a task in plain English, and it uses an LLM to decide which tools to call — reading files, writing code, running shell commands — until the task is done:

```
agent >> Create a Python function that checks if a number is prime

  > write_file: prime.py
  > bash: python3 -c "from prime import is_prime; print(is_prime(7))"

Created prime.py with an is_prime function. Tested and confirmed
that is_prime(7) returns True.
```

## The Five Layers

Every interaction flows through five layers:

```
User input  →  Agent Loop  →  LLM API  →  Tool Dispatch  →  Tool Handlers
                  ↑                            │                    │
                  └────── tool results ────────┘                    │
                                                                    ↓
                                                              Safety Layer
```

### Layer 1: HTTP / API Layer

No SDK — just raw `urllib.request` calls to the Claude Messages API. This shows exactly what happens when you call an LLM:

```python
POST /v1/messages
Headers:
  x-api-key: sk-...
  anthropic-version: 2023-06-01
  content-type: application/json
Body:
  {model, system, messages, tools, max_tokens}
```

The response comes back as JSON with `content` blocks (text or tool_use) and a `stop_reason` telling us whether the model wants to use a tool or is done talking.

### Layer 2: Agent Loop

The core loop is deceptively simple:

```
1. Send messages[] to the LLM
2. Append the assistant response to messages[]
3. If stop_reason == "tool_use":
     Execute each tool → collect results
     Append tool_results to messages[]
     Go to step 1
4. Else: done — return
```

That's it. The entire "intelligence" of the agent comes from the LLM deciding which tools to call and when to stop. The loop is just plumbing.

### Layer 3: Tool Dispatch

A simple dictionary maps tool names to handler functions:

```python
"bash"       → run_bash(command)
"read_file"  → run_read(path, offset, limit)
"write_file" → run_write(path, content)
"edit_file"  → run_edit(path, old_text, new_text)
"list_files" → run_list(pattern)
"grep"       → run_grep(pattern, path)
```

Each tool also has a JSON schema that tells the LLM what arguments it accepts. The LLM generates structured `tool_use` blocks that match these schemas.

### Layer 4: Tool Handlers

Six tools give the agent everything it needs to explore and modify code:

| Tool | Purpose |
|------|---------|
| `bash` | Run shell commands (with dangerous-command blocking) |
| `read_file` | Read files with line numbers, supports offset/limit |
| `write_file` | Create or overwrite files |
| `edit_file` | Replace exact text in a file (surgical edits) |
| `list_files` | Glob-based file discovery |
| `grep` | Search file contents with regex |

### Layer 5: Safety Layer

Two mechanisms prevent the agent from doing damage:

- **Path sandboxing**: All file operations are confined to the workspace directory. Any attempt to escape via `../../` or absolute paths is blocked.
- **Dangerous command blocklist**: Shell commands matching patterns like `rm -rf /`, `sudo`, `shutdown`, or fork bombs are rejected before execution.

## Running It

```bash
export ANTHROPIC_API_KEY="your-key-here"
cd coding-agent
python coding-agent.py
```

Output:

```
Mini Coding Agent — Python Edition
========================================
  Workspace: /path/to/coding-agent
  Model:     claude-sonnet-4-20250514
  Tools:     bash, read_file, write_file, edit_file, list_files, grep

  Type a task, then watch the agent work.
  Type 'q' or 'exit' to quit.

agent >> List all Python files in this directory
  > list_files: coding-agent.py, test_coding_agent.py

Found 2 Python files: coding-agent.py and test_coding_agent.py.
```

## Running Tests

```bash
cd coding-agent
python -m pytest test_coding_agent.py -v
```

The test suite uses mocked API responses — no real LLM calls needed. It covers path sandboxing, dangerous command detection, all six tool handlers, tool dispatch routing, API request formatting, the agent loop with multi-turn tool use, and end-to-end workflows.

## Implementation: `coding-agent.py`

### References

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) by shareAI-lab — the educational project this implementation draws from
- [Claude Messages API](https://docs.anthropic.com/en/api/messages) — the official API documentation
- [Tool use (function calling)](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — how Claude uses tools
