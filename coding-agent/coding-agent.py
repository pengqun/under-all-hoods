"""
A Miniature Coding Agent — in Python
======================================

How does a coding agent like Claude Code turn natural-language instructions
into executed code changes? This module implements a mini coding agent from
scratch, covering raw HTTP calls to an LLM API, a tool-dispatch system,
path sandboxing, and the core agent loop — all in a single file using only
the Python standard library.

Architecture
------------

::

    ┌──────────────────────────────────────────────────────────┐
    │                       REPL (main)                        │
    │  Read user input → feed to agent loop → print response   │
    └──────────────────────┬───────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────┐
    │                     AGENT LOOP                           │
    │                                                          │
    │  messages[] ──► LLM API ──► response                     │
    │                                │                         │
    │                    ┌───────────┴───────────┐             │
    │                    │  stop_reason          │             │
    │                    │  == "tool_use"?       │             │
    │                    └───┬──────────┬────────┘             │
    │                   yes  │          │  no                  │
    │                        ▼          ▼                      │
    │              ┌─────────────┐   return                    │
    │              │ TOOL SYSTEM │   (done)                    │
    │              │  dispatch   │                              │
    │              └──────┬──────┘                              │
    │                     │                                    │
    │              append tool_results                          │
    │              to messages[]                                │
    │                     │                                    │
    │                     └──────► loop back to LLM API        │
    └──────────────────────────────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────┐
    │                    TOOL DISPATCH                          │
    │                                                          │
    │   "bash"       → run_bash(command)                       │
    │   "read_file"  → run_read(path, offset, limit)           │
    │   "write_file" → run_write(path, content)                │
    │   "edit_file"  → run_edit(path, old_text, new_text)      │
    │   "list_files" → run_list(pattern)                       │
    │   "grep"       → run_grep(pattern, path)                 │
    └──────────────────────┬───────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────┐
    │                   SAFETY LAYER                            │
    │                                                          │
    │   • Path sandboxing: all file ops confined to WORKDIR    │
    │   • Dangerous command blocklist for bash                 │
    │   • Timeout on shell execution (120s)                    │
    │   • Output truncation (50 KB cap)                        │
    └──────────────────────────────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────┐
    │                   HTTP / API LAYER                        │
    │                                                          │
    │   Raw urllib.request calls to the Claude Messages API.   │
    │   No SDK — just JSON over HTTPS.                         │
    │                                                          │
    │   POST /v1/messages                                      │
    │   Headers: x-api-key, anthropic-version, content-type    │
    │   Body: {model, system, messages, tools, max_tokens}     │
    │   Response: {content: [...], stop_reason: ...}           │
    └──────────────────────────────────────────────────────────┘

Reference
---------
- `learn-claude-code <https://github.com/shareAI-lab/learn-claude-code>`_
  by shareAI-lab — the educational project this implementation draws from
- `Claude Messages API <https://docs.anthropic.com/en/api/messages>`_
  — the official Claude API documentation
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP / API LAYER
# ═══════════════════════════════════════════════════════════════════════════════

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8096


def api_call(
    messages: list[dict],
    tools: list[dict],
    *,
    system: str = "",
    model: str = "",
    api_key: str = "",
    api_url: str = "",
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """Send a request to the Claude Messages API using raw HTTP.

    This function builds the JSON payload, sets the required headers, and
    makes a POST request via ``urllib.request``.  No SDK needed — just
    standard-library HTTP.

    Returns the parsed JSON response as a dict with keys like ``content``,
    ``stop_reason``, ``model``, and ``usage``.
    """
    url = api_url or os.environ.get("ANTHROPIC_BASE_URL") or API_URL
    if not url.endswith("/v1/messages") and "v1/messages" not in url:
        url = url.rstrip("/") + "/v1/messages"
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    body = {
        "model": model or os.environ.get("MODEL_ID") or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": API_VERSION,
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode() if exc.fp else str(exc)
        raise RuntimeError(
            f"API error {exc.code}: {error_body}"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY LAYER
# ═══════════════════════════════════════════════════════════════════════════════

DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "sudo rm",
    "mkfs.",
    "dd if=",
    "shutdown",
    "reboot",
    "> /dev/sd",
    ":(){ :",           # fork bomb
    "chmod -R 777 /",
]

OUTPUT_LIMIT = 50_000  # characters


def safe_path(workdir: Path, p: str) -> Path:
    """Resolve *p* relative to *workdir* and ensure it stays inside.

    Raises ``ValueError`` if the resolved path escapes the workspace.
    """
    resolved = (workdir / p).resolve()
    if not resolved.is_relative_to(workdir.resolve()):
        raise ValueError(f"Path escapes workspace: {p}")
    return resolved


def is_dangerous(command: str) -> bool:
    """Return ``True`` if *command* matches any entry in the blocklist."""
    lower = command.lower().strip()
    return any(d in lower for d in DANGEROUS_COMMANDS)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def run_bash(command: str, workdir: Path) -> str:
    """Execute a shell command inside *workdir* and return its output.

    Dangerous commands are blocked.  Execution is capped at 120 seconds.
    Output is truncated to ``OUTPUT_LIMIT`` characters.
    """
    if is_dangerous(command):
        return "Error: dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout + result.stderr).strip()
        if not out:
            return "(no output)"
        return out[:OUTPUT_LIMIT]
    except subprocess.TimeoutExpired:
        return "Error: command timed out (120s)"
    except Exception as exc:
        return f"Error: {exc}"


def run_read(path: str, workdir: Path, offset: int = 0, limit: int = 0) -> str:
    """Read a file and return its contents with line numbers.

    *offset* and *limit* allow reading a window of lines (1-indexed offset).
    """
    try:
        fp = safe_path(workdir, path)
        text = fp.read_text()
        lines = text.splitlines()
        total = len(lines)

        start = max(0, offset)
        end = (start + limit) if limit > 0 else total
        window = lines[start:end]

        numbered = [f"{start + i + 1:>6}\t{line}" for i, line in enumerate(window)]
        result = "\n".join(numbered)
        if end < total:
            result += f"\n... ({total - end} more lines)"
        return result[:OUTPUT_LIMIT] if result else "(empty file)"
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str, workdir: Path) -> str:
    """Write *content* to a file, creating parent directories as needed."""
    try:
        fp = safe_path(workdir, path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str, workdir: Path) -> str:
    """Replace the first occurrence of *old_text* with *new_text* in a file."""
    try:
        fp = safe_path(workdir, path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_list(pattern: str, workdir: Path) -> str:
    """List files under *workdir* matching a glob *pattern*."""
    try:
        matches = sorted(workdir.glob(pattern))
        if not matches:
            return "(no matches)"
        lines = [str(m.relative_to(workdir)) for m in matches[:200]]
        result = "\n".join(lines)
        if len(matches) > 200:
            result += f"\n... ({len(matches) - 200} more files)"
        return result
    except Exception as exc:
        return f"Error: {exc}"


def run_grep(pattern: str, path: str, workdir: Path) -> str:
    """Search for *pattern* in files under *path* (relative to workdir).

    Uses ``subprocess`` to call ``grep -rn`` for simplicity.
    """
    try:
        target = safe_path(workdir, path) if path else workdir
        result = subprocess.run(
            ["grep", "-rn", "--include=*", pattern, str(target)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workdir,
        )
        out = result.stdout.strip()
        if not out:
            return "(no matches)"
        return out[:OUTPUT_LIMIT]
    except subprocess.TimeoutExpired:
        return "Error: grep timed out (30s)"
    except Exception as exc:
        return f"Error: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS & DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command in the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file with line numbers. Supports offset/limit for large files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace."},
                "offset": {"type": "integer", "description": "Start line (0-indexed). Default 0."},
                "limit": {"type": "integer", "description": "Max lines to read. Default 0 (all)."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace the first occurrence of old_text with new_text in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace."},
                "old_text": {"type": "string", "description": "Exact text to find."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_files",
        "description": "List files matching a glob pattern (e.g. '**/*.py').",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a regex pattern in files under a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)."},
                "path": {"type": "string", "description": "Directory to search in (relative to workspace). Default: workspace root."},
            },
            "required": ["pattern"],
        },
    },
]


def dispatch_tool(name: str, inputs: dict, workdir: Path) -> str:
    """Route a tool call to the correct handler and return its output."""
    if name == "bash":
        return run_bash(inputs["command"], workdir)
    if name == "read_file":
        return run_read(inputs["path"], workdir, inputs.get("offset", 0), inputs.get("limit", 0))
    if name == "write_file":
        return run_write(inputs["path"], inputs["content"], workdir)
    if name == "edit_file":
        return run_edit(inputs["path"], inputs["old_text"], inputs["new_text"], workdir)
    if name == "list_files":
        return run_list(inputs["pattern"], workdir)
    if name == "grep":
        return run_grep(inputs["pattern"], inputs.get("path", "."), workdir)
    return f"Error: unknown tool '{name}'"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def agent_loop(
    messages: list[dict],
    *,
    workdir: Path | None = None,
    system: str = "",
    model: str = "",
    api_key: str = "",
    api_url: str = "",
    max_turns: int = 50,
    on_tool_call: object = None,
    on_response: object = None,
) -> list[dict]:
    """Run the core agent loop.

    The loop repeatedly:
    1. Sends ``messages`` to the LLM.
    2. Appends the assistant response to ``messages``.
    3. If the response contains tool-use blocks, executes each tool,
       appends the results, and loops back to step 1.
    4. If the response's ``stop_reason`` is not ``"tool_use"``, returns.

    Parameters
    ----------
    messages : list[dict]
        The conversation so far (mutated in place).
    workdir : Path
        Sandbox directory for file operations.
    system : str
        System prompt for the LLM.
    model : str
        Model identifier (default from env or ``DEFAULT_MODEL``).
    api_key : str
        Anthropic API key (default from ``ANTHROPIC_API_KEY`` env var).
    api_url : str
        Override base URL for the API.
    max_turns : int
        Safety cap on loop iterations (default 50).
    on_tool_call : callable, optional
        ``fn(name, inputs, output)`` — called after each tool execution.
    on_response : callable, optional
        ``fn(response_dict)`` — called after each LLM response.

    Returns
    -------
    list[dict]
        The mutated ``messages`` list.
    """
    wd = (workdir or Path.cwd()).resolve()

    if not system:
        system = (
            f"You are a coding agent. Your workspace is: {wd}\n"
            f"Use the provided tools to explore, understand, and modify code.\n"
            f"Prefer reading files before editing them. Be precise and concise."
        )

    for _turn in range(max_turns):
        response = api_call(
            messages, TOOLS, system=system, model=model,
            api_key=api_key, api_url=api_url,
        )

        if on_response:
            on_response(response)

        # Build the assistant message from the response content blocks.
        assistant_content = response.get("content", [])
        messages.append({"role": "assistant", "content": assistant_content})

        # If the model is done (no tool use), we're finished.
        if response.get("stop_reason") != "tool_use":
            return messages

        # Execute each tool-use block and collect results.
        tool_results = []
        for block in assistant_content:
            if block.get("type") != "tool_use":
                continue

            tool_name = block["name"]
            tool_input = block["input"]
            tool_id = block["id"]

            output = dispatch_tool(tool_name, tool_input, wd)

            if on_tool_call:
                on_tool_call(tool_name, tool_input, output)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": output,
            })

        messages.append({"role": "user", "content": tool_results})

    return messages


# ═══════════════════════════════════════════════════════════════════════════════
# REPL
# ═══════════════════════════════════════════════════════════════════════════════

def extract_text(message: dict) -> str:
    """Extract printable text from an assistant message."""
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts)


def repl(workdir: Path | None = None) -> None:
    """Interactive read-eval-print loop for the coding agent.

    Type a task, and the agent will use tools to accomplish it.
    Type ``q``, ``exit``, or press Ctrl-C / Ctrl-D to quit.
    """
    wd = (workdir or Path.cwd()).resolve()
    history: list[dict] = []

    print("Mini Coding Agent — Python Edition")
    print("=" * 40)
    print(f"  Workspace: {wd}")
    print(f"  Model:     {os.environ.get('MODEL_ID') or DEFAULT_MODEL}")
    print(f"  Tools:     {', '.join(t['name'] for t in TOOLS)}")
    print()
    print("  Type a task, then watch the agent work.")
    print("  Type 'q' or 'exit' to quit.")
    print()

    def on_tool_call(name, inputs, output):
        preview = output[:200].replace("\n", "\\n")
        if name == "bash":
            print(f"  \033[33m> bash:\033[0m {inputs['command']}")
        elif name in ("read_file", "write_file", "edit_file"):
            print(f"  \033[33m> {name}:\033[0m {inputs['path']}")
        else:
            print(f"  \033[33m> {name}:\033[0m {preview}")

    while True:
        try:
            query = input("\033[36magent >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if query.strip().lower() in ("q", "exit", "quit", ""):
            if query.strip().lower() in ("q", "exit", "quit"):
                print("Bye!")
            break

        history.append({"role": "user", "content": query})

        try:
            agent_loop(
                history,
                workdir=wd,
                on_tool_call=on_tool_call,
            )
        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m")
            continue

        # Print the final assistant text.
        if history and history[-1].get("role") == "assistant":
            text = extract_text(history[-1])
            if text:
                print(f"\n{text}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN / DEMO
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    repl()
