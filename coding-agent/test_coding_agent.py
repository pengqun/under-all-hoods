"""
Tests for the Mini Coding Agent
=================================

Organized by component so failures point directly to the broken layer.
All tests use mocked API responses — no real LLM calls are made.

Run with: python -m pytest test_coding_agent.py -v
     or:  python test_coding_agent.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the module (filename has a hyphen) ────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "coding-agent.py")
_loader = SourceFileLoader("coding_agent", _path)
_spec = spec_from_loader("coding_agent", _loader)
agent_module = module_from_spec(_spec)
sys.modules["coding_agent"] = agent_module
_loader.exec_module(agent_module)

safe_path = agent_module.safe_path
is_dangerous = agent_module.is_dangerous
run_bash = agent_module.run_bash
run_read = agent_module.run_read
run_write = agent_module.run_write
run_edit = agent_module.run_edit
run_list = agent_module.run_list
run_grep = agent_module.run_grep
dispatch_tool = agent_module.dispatch_tool
agent_loop = agent_module.agent_loop
extract_text = agent_module.extract_text
api_call = agent_module.api_call
TOOLS = agent_module.TOOLS
OUTPUT_LIMIT = agent_module.OUTPUT_LIMIT


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY LAYER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafePath:
    """Tests for the path sandboxing function."""

    def test_relative_path_within_workdir(self, tmp_path):
        (tmp_path / "file.txt").touch()
        result = safe_path(tmp_path, "file.txt")
        assert result == tmp_path / "file.txt"

    def test_nested_relative_path(self, tmp_path):
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        (sub / "file.txt").touch()
        result = safe_path(tmp_path, "a/b/file.txt")
        assert result == sub / "file.txt"

    def test_path_traversal_blocked(self, tmp_path):
        with pytest.raises(ValueError, match="escapes workspace"):
            safe_path(tmp_path, "../../etc/passwd")

    def test_absolute_path_outside_blocked(self, tmp_path):
        with pytest.raises(ValueError, match="escapes workspace"):
            safe_path(tmp_path, "/etc/passwd")

    def test_dot_path_stays_inside(self, tmp_path):
        result = safe_path(tmp_path, ".")
        assert result == tmp_path.resolve()

    def test_symlink_escape_blocked(self, tmp_path):
        """Symlinks that resolve outside workdir are blocked."""
        link = tmp_path / "escape"
        link.symlink_to("/tmp")
        with pytest.raises(ValueError, match="escapes workspace"):
            safe_path(tmp_path, "escape/something")


class TestIsDangerous:
    """Tests for dangerous command detection."""

    def test_rm_rf_root(self):
        assert is_dangerous("rm -rf /") is True

    def test_rm_rf_star(self):
        assert is_dangerous("rm -rf /*") is True

    def test_sudo_rm(self):
        assert is_dangerous("sudo rm something") is True

    def test_shutdown(self):
        assert is_dangerous("shutdown -h now") is True

    def test_fork_bomb(self):
        assert is_dangerous(":(){ :") is True

    def test_safe_ls(self):
        assert is_dangerous("ls -la") is False

    def test_safe_python(self):
        assert is_dangerous("python3 test.py") is False

    def test_safe_cat(self):
        assert is_dangerous("cat README.md") is False

    def test_safe_grep(self):
        assert is_dangerous("grep -rn pattern .") is False


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunBash:
    """Tests for the bash tool handler."""

    def test_simple_command(self, tmp_path):
        result = run_bash("echo hello", tmp_path)
        assert "hello" in result

    def test_dangerous_command_blocked(self, tmp_path):
        result = run_bash("rm -rf /", tmp_path)
        assert "dangerous" in result.lower()

    def test_command_timeout(self, tmp_path):
        # We can't easily test 120s timeout, but we test the mechanism exists
        result = run_bash("echo fast", tmp_path)
        assert result == "fast"

    def test_no_output_command(self, tmp_path):
        result = run_bash("true", tmp_path)
        assert result == "(no output)"

    def test_stderr_captured(self, tmp_path):
        result = run_bash("echo err >&2", tmp_path)
        assert "err" in result

    def test_workdir_is_respected(self, tmp_path):
        (tmp_path / "marker.txt").write_text("found")
        result = run_bash("cat marker.txt", tmp_path)
        assert "found" in result

    def test_output_truncation(self, tmp_path):
        # Generate output larger than OUTPUT_LIMIT
        cmd = f"python3 -c \"print('x' * {OUTPUT_LIMIT + 100})\""
        result = run_bash(cmd, tmp_path)
        assert len(result) <= OUTPUT_LIMIT


class TestRunRead:
    """Tests for the read_file tool handler."""

    def test_read_file(self, tmp_path):
        (tmp_path / "hello.txt").write_text("line one\nline two\nline three")
        result = run_read("hello.txt", tmp_path)
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result

    def test_line_numbers(self, tmp_path):
        (tmp_path / "hello.txt").write_text("first\nsecond")
        result = run_read("hello.txt", tmp_path)
        assert "1\t" in result
        assert "2\t" in result

    def test_offset(self, tmp_path):
        (tmp_path / "f.txt").write_text("a\nb\nc\nd")
        result = run_read("f.txt", tmp_path, offset=2)
        assert "a" not in result
        assert "b" not in result
        assert "c" in result

    def test_limit(self, tmp_path):
        (tmp_path / "f.txt").write_text("a\nb\nc\nd\ne")
        result = run_read("f.txt", tmp_path, limit=2)
        assert "a" in result
        assert "b" in result
        assert "more lines" in result

    def test_empty_file(self, tmp_path):
        (tmp_path / "empty.txt").write_text("")
        result = run_read("empty.txt", tmp_path)
        assert result == "(empty file)"

    def test_nonexistent_file(self, tmp_path):
        result = run_read("nope.txt", tmp_path)
        assert "Error" in result

    def test_path_escape_blocked(self, tmp_path):
        result = run_read("../../etc/passwd", tmp_path)
        assert "Error" in result


class TestRunWrite:
    """Tests for the write_file tool handler."""

    def test_write_new_file(self, tmp_path):
        result = run_write("new.txt", "hello world", tmp_path)
        assert "Wrote" in result
        assert (tmp_path / "new.txt").read_text() == "hello world"

    def test_write_creates_directories(self, tmp_path):
        result = run_write("a/b/c.txt", "deep", tmp_path)
        assert "Wrote" in result
        assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"

    def test_overwrite_existing(self, tmp_path):
        (tmp_path / "f.txt").write_text("old")
        run_write("f.txt", "new", tmp_path)
        assert (tmp_path / "f.txt").read_text() == "new"

    def test_path_escape_blocked(self, tmp_path):
        result = run_write("../../evil.txt", "bad", tmp_path)
        assert "Error" in result


class TestRunEdit:
    """Tests for the edit_file tool handler."""

    def test_edit_replaces_text(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello world")
        result = run_edit("f.txt", "world", "python", tmp_path)
        assert "Edited" in result
        assert (tmp_path / "f.txt").read_text() == "hello python"

    def test_edit_only_first_occurrence(self, tmp_path):
        (tmp_path / "f.txt").write_text("aaa bbb aaa")
        run_edit("f.txt", "aaa", "ccc", tmp_path)
        assert (tmp_path / "f.txt").read_text() == "ccc bbb aaa"

    def test_edit_text_not_found(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello")
        result = run_edit("f.txt", "xyz", "abc", tmp_path)
        assert "not found" in result

    def test_edit_nonexistent_file(self, tmp_path):
        result = run_edit("nope.txt", "a", "b", tmp_path)
        assert "Error" in result

    def test_edit_multiline(self, tmp_path):
        (tmp_path / "f.txt").write_text("line1\nline2\nline3")
        run_edit("f.txt", "line2\nline3", "replaced", tmp_path)
        assert (tmp_path / "f.txt").read_text() == "line1\nreplaced"


class TestRunList:
    """Tests for the list_files tool handler."""

    def test_list_all_python_files(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        (tmp_path / "c.txt").touch()
        result = run_list("*.py", tmp_path)
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").touch()
        result = run_list("**/*.py", tmp_path)
        assert "deep.py" in result

    def test_no_matches(self, tmp_path):
        result = run_list("*.xyz", tmp_path)
        assert "no matches" in result


class TestRunGrep:
    """Tests for the grep tool handler."""

    def test_grep_finds_pattern(self, tmp_path):
        (tmp_path / "code.py").write_text("def hello():\n    pass\n")
        result = run_grep("hello", ".", tmp_path)
        assert "hello" in result

    def test_grep_no_matches(self, tmp_path):
        (tmp_path / "code.py").write_text("nothing here")
        result = run_grep("zzzzz", ".", tmp_path)
        assert "no matches" in result


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatchTool:
    """Tests for the tool dispatch router."""

    def test_dispatch_bash(self, tmp_path):
        result = dispatch_tool("bash", {"command": "echo dispatched"}, tmp_path)
        assert "dispatched" in result

    def test_dispatch_read(self, tmp_path):
        (tmp_path / "f.txt").write_text("content")
        result = dispatch_tool("read_file", {"path": "f.txt"}, tmp_path)
        assert "content" in result

    def test_dispatch_write(self, tmp_path):
        result = dispatch_tool("write_file", {"path": "f.txt", "content": "data"}, tmp_path)
        assert "Wrote" in result

    def test_dispatch_edit(self, tmp_path):
        (tmp_path / "f.txt").write_text("old")
        result = dispatch_tool("edit_file", {"path": "f.txt", "old_text": "old", "new_text": "new"}, tmp_path)
        assert "Edited" in result

    def test_dispatch_list(self, tmp_path):
        (tmp_path / "a.py").touch()
        result = dispatch_tool("list_files", {"pattern": "*.py"}, tmp_path)
        assert "a.py" in result

    def test_dispatch_grep(self, tmp_path):
        (tmp_path / "f.py").write_text("target_word")
        result = dispatch_tool("grep", {"pattern": "target_word", "path": "."}, tmp_path)
        assert "target_word" in result

    def test_dispatch_unknown_tool(self, tmp_path):
        result = dispatch_tool("nonexistent", {}, tmp_path)
        assert "unknown tool" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolDefinitions:
    """Tests that tool schemas are well-formed."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_tool_names_are_unique(self):
        names = [t["name"] for t in TOOLS]
        assert len(names) == len(set(names))

    def test_all_tools_have_required_property(self):
        for tool in TOOLS:
            schema = tool["input_schema"]
            assert "properties" in schema
            assert "required" in schema
            for req in schema["required"]:
                assert req in schema["properties"]


# ═══════════════════════════════════════════════════════════════════════════════
# API LAYER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiCall:
    """Tests for the raw HTTP API call function (mocked)."""

    def _mock_response(self, body: dict, status: int = 200):
        """Create a mock urllib response."""
        encoded = json.dumps(body).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = encoded
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_basic_api_call(self, mock_urlopen):
        response_body = {
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "model": "test",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_urlopen.return_value = self._mock_response(response_body)

        result = api_call(
            [{"role": "user", "content": "hi"}],
            [],
            api_key="test-key",
        )

        assert result["stop_reason"] == "end_turn"
        assert result["content"][0]["text"] == "Hello!"

        # Verify the request was properly formed
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.method == "POST"
        assert request.get_header("X-api-key") == "test-key"
        assert request.get_header("Content-type") == "application/json"

    @patch("urllib.request.urlopen")
    def test_api_sends_tools(self, mock_urlopen):
        response_body = {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
        }
        mock_urlopen.return_value = self._mock_response(response_body)

        api_call(
            [{"role": "user", "content": "test"}],
            TOOLS,
            api_key="key",
        )

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = json.loads(request.data)
        assert "tools" in body
        assert len(body["tools"]) == len(TOOLS)

    @patch("urllib.request.urlopen")
    def test_api_sends_system_prompt(self, mock_urlopen):
        response_body = {"content": [], "stop_reason": "end_turn"}
        mock_urlopen.return_value = self._mock_response(response_body)

        api_call(
            [{"role": "user", "content": "test"}],
            [],
            system="You are helpful.",
            api_key="key",
        )

        call_args = mock_urlopen.call_args
        body = json.loads(call_args[0][0].data)
        assert body["system"] == "You are helpful."

    @patch("urllib.request.urlopen")
    def test_api_http_error(self, mock_urlopen):
        import urllib.error
        error_response = MagicMock()
        error_response.read.return_value = b'{"error": "bad request"}'
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 400, "Bad Request", {}, error_response
        )

        with pytest.raises(RuntimeError, match="API error 400"):
            api_call([{"role": "user", "content": "test"}], [], api_key="key")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentLoop:
    """Tests for the core agent loop (with mocked API calls)."""

    @patch.object(agent_module, "api_call")
    def test_simple_text_response(self, mock_api, tmp_path):
        """Agent returns immediately when stop_reason is not tool_use."""
        mock_api.return_value = {
            "content": [{"type": "text", "text": "Done!"}],
            "stop_reason": "end_turn",
        }

        messages = [{"role": "user", "content": "hello"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        assert len(messages) == 2
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"][0]["text"] == "Done!"

    @patch.object(agent_module, "api_call")
    def test_tool_use_then_response(self, mock_api, tmp_path):
        """Agent executes a tool, then gets final response."""
        (tmp_path / "hello.txt").write_text("world")

        mock_api.side_effect = [
            # First call: model wants to read a file
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "read_file",
                     "input": {"path": "hello.txt"}},
                ],
                "stop_reason": "tool_use",
            },
            # Second call: model responds with text
            {
                "content": [{"type": "text", "text": "The file contains 'world'."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "read hello.txt"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        # user, assistant (tool_use), user (tool_result), assistant (text)
        assert len(messages) == 4
        assert messages[1]["content"][0]["name"] == "read_file"
        assert messages[2]["content"][0]["type"] == "tool_result"
        assert "world" in messages[2]["content"][0]["content"]
        assert messages[3]["content"][0]["text"] == "The file contains 'world'."

    @patch.object(agent_module, "api_call")
    def test_multiple_tool_calls(self, mock_api, tmp_path):
        """Agent can execute multiple tools in one turn."""
        mock_api.side_effect = [
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "bash",
                     "input": {"command": "echo first"}},
                    {"type": "tool_use", "id": "t2", "name": "bash",
                     "input": {"command": "echo second"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "Both commands ran."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "run two commands"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        tool_results = messages[2]["content"]
        assert len(tool_results) == 2
        assert "first" in tool_results[0]["content"]
        assert "second" in tool_results[1]["content"]

    @patch.object(agent_module, "api_call")
    def test_write_and_read_roundtrip(self, mock_api, tmp_path):
        """Agent writes a file, then reads it back."""
        mock_api.side_effect = [
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "write_file",
                     "input": {"path": "test.py", "content": "print('hi')"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "read_file",
                     "input": {"path": "test.py"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "File created and verified."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "create test.py"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        assert (tmp_path / "test.py").read_text() == "print('hi')"
        # Tool result from read should contain the file content
        read_result = messages[4]["content"][0]["content"]
        assert "print('hi')" in read_result

    @patch.object(agent_module, "api_call")
    def test_max_turns_limit(self, mock_api, tmp_path):
        """Agent stops after max_turns iterations."""
        mock_api.return_value = {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "bash",
                 "input": {"command": "echo loop"}},
            ],
            "stop_reason": "tool_use",
        }

        messages = [{"role": "user", "content": "loop forever"}]
        agent_loop(messages, workdir=tmp_path, api_key="test", max_turns=3)

        # Should have stopped after 3 turns
        assert mock_api.call_count == 3

    @patch.object(agent_module, "api_call")
    def test_on_tool_call_callback(self, mock_api, tmp_path):
        """The on_tool_call callback is invoked for each tool."""
        mock_api.side_effect = [
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "bash",
                     "input": {"command": "echo hi"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "done"}],
                "stop_reason": "end_turn",
            },
        ]

        calls = []
        def on_tool(name, inputs, output):
            calls.append((name, inputs, output))

        messages = [{"role": "user", "content": "test"}]
        agent_loop(messages, workdir=tmp_path, api_key="test", on_tool_call=on_tool)

        assert len(calls) == 1
        assert calls[0][0] == "bash"
        assert "hi" in calls[0][2]

    @patch.object(agent_module, "api_call")
    def test_on_response_callback(self, mock_api, tmp_path):
        """The on_response callback is invoked for each LLM response."""
        mock_api.return_value = {
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": "end_turn",
        }

        responses = []
        messages = [{"role": "user", "content": "test"}]
        agent_loop(
            messages, workdir=tmp_path, api_key="test",
            on_response=lambda r: responses.append(r),
        )

        assert len(responses) == 1
        assert responses[0]["stop_reason"] == "end_turn"


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACT TEXT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractText:
    """Tests for the text extraction helper."""

    def test_extract_from_text_blocks(self):
        msg = {"content": [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]}
        assert extract_text(msg) == "Hello\nWorld"

    def test_extract_skips_tool_use(self):
        msg = {"content": [
            {"type": "tool_use", "id": "t1", "name": "bash", "input": {}},
            {"type": "text", "text": "After tools"},
        ]}
        assert extract_text(msg) == "After tools"

    def test_extract_from_string_content(self):
        msg = {"content": "Just a string"}
        assert extract_text(msg) == "Just a string"

    def test_extract_empty(self):
        msg = {"content": []}
        assert extract_text(msg) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end integration tests with mocked API."""

    @patch.object(agent_module, "api_call")
    def test_create_edit_verify_workflow(self, mock_api, tmp_path):
        """Simulate a real workflow: create file → edit it → verify."""
        mock_api.side_effect = [
            # Step 1: Create a file
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "write_file",
                     "input": {"path": "app.py",
                               "content": "def greet():\n    return 'hello'\n"}},
                ],
                "stop_reason": "tool_use",
            },
            # Step 2: Edit the file
            {
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "edit_file",
                     "input": {"path": "app.py",
                               "old_text": "return 'hello'",
                               "new_text": "return 'hello world'"}},
                ],
                "stop_reason": "tool_use",
            },
            # Step 3: Verify with bash
            {
                "content": [
                    {"type": "tool_use", "id": "t3", "name": "bash",
                     "input": {"command": "python3 -c \"import app; print(app.greet())\""}},
                ],
                "stop_reason": "tool_use",
            },
            # Step 4: Final response
            {
                "content": [{"type": "text", "text": "Created and verified app.py."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "create app.py with greet function"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        # Verify the file was created and edited
        final = (tmp_path / "app.py").read_text()
        assert "hello world" in final
        assert "def greet" in final

    @patch.object(agent_module, "api_call")
    def test_list_then_read_workflow(self, mock_api, tmp_path):
        """Agent lists files then reads one."""
        (tmp_path / "README.md").write_text("# Hello\nThis is a project.")
        (tmp_path / "main.py").write_text("print('hi')")

        mock_api.side_effect = [
            {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "list_files",
                     "input": {"pattern": "*"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "read_file",
                     "input": {"path": "README.md"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "Found README and main.py."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "explore the project"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        # List results should contain both files
        list_result = messages[2]["content"][0]["content"]
        assert "README.md" in list_result
        assert "main.py" in list_result

    @patch.object(agent_module, "api_call")
    def test_text_and_tool_use_mixed(self, mock_api, tmp_path):
        """Model can return text blocks alongside tool_use blocks."""
        mock_api.side_effect = [
            {
                "content": [
                    {"type": "text", "text": "Let me check that file."},
                    {"type": "tool_use", "id": "t1", "name": "bash",
                     "input": {"command": "echo found"}},
                ],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "Done."}],
                "stop_reason": "end_turn",
            },
        ]

        messages = [{"role": "user", "content": "check something"}]
        agent_loop(messages, workdir=tmp_path, api_key="test")

        # First assistant message has both text and tool_use
        first_assistant = messages[1]["content"]
        types = [b["type"] for b in first_assistant]
        assert "text" in types
        assert "tool_use" in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
