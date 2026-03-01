"""
Tests for the Mini Redis Server
================================

Organized by component so failures point directly to the broken layer.
Run with: python -m pytest test_redis.py -v
     or:  python test_redis.py
"""

import io
import os
import sys
import threading
import time

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# ── Import the module (filename has a hyphen) ────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
_path = os.path.join(_dir, "mini-redis.py")
_loader = SourceFileLoader("mini_redis", _path)
_spec = spec_from_loader("mini_redis", _loader)
redis_module = module_from_spec(_spec)
sys.modules["mini_redis"] = redis_module
_loader.exec_module(redis_module)

Error = redis_module.Error
encode = redis_module.encode
decode = redis_module.decode
Storage = redis_module.Storage
CommandProcessor = redis_module.CommandProcessor
RedisServer = redis_module.RedisServer
RedisClient = redis_module.RedisClient


# ═══════════════════════════════════════════════════════════════════════════════
# RESP ENCODER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRESPEncoder:
    """Tests for the encode() function."""

    def test_encode_none(self):
        """None encodes to null bulk string."""
        assert encode(None) == b"$-1\r\n"

    def test_encode_integer_zero(self):
        assert encode(0) == b":0\r\n"

    def test_encode_positive_integer(self):
        assert encode(42) == b":42\r\n"

    def test_encode_negative_integer(self):
        assert encode(-1) == b":-1\r\n"

    def test_encode_large_integer(self):
        assert encode(1000000) == b":1000000\r\n"

    def test_encode_bool_true(self):
        """True encodes as integer 1."""
        assert encode(True) == b":1\r\n"

    def test_encode_bool_false(self):
        """False encodes as integer 0."""
        assert encode(False) == b":0\r\n"

    def test_encode_simple_string(self):
        assert encode("hello") == b"$5\r\nhello\r\n"

    def test_encode_empty_string(self):
        assert encode("") == b"$0\r\n\r\n"

    def test_encode_string_with_spaces(self):
        assert encode("hello world") == b"$11\r\nhello world\r\n"

    def test_encode_bytes(self):
        assert encode(b"data") == b"$4\r\ndata\r\n"

    def test_encode_error(self):
        assert encode(Error("ERR bad")) == b"-ERR bad\r\n"

    def test_encode_empty_list(self):
        assert encode([]) == b"*0\r\n"

    def test_encode_list_of_strings(self):
        result = encode(["hello", "world"])
        expected = b"*2\r\n$5\r\nhello\r\n$5\r\nworld\r\n"
        assert result == expected

    def test_encode_list_of_integers(self):
        result = encode([1, 2, 3])
        expected = b"*3\r\n:1\r\n:2\r\n:3\r\n"
        assert result == expected

    def test_encode_mixed_list(self):
        result = encode(["hello", 42, None])
        expected = b"*3\r\n$5\r\nhello\r\n:42\r\n$-1\r\n"
        assert result == expected

    def test_encode_nested_list(self):
        result = encode([["a", "b"], ["c"]])
        expected = (
            b"*2\r\n"
            b"*2\r\n$1\r\na\r\n$1\r\nb\r\n"
            b"*1\r\n$1\r\nc\r\n"
        )
        assert result == expected

    def test_encode_tuple(self):
        """Tuples are treated like lists."""
        result = encode(("a",))
        expected = b"*1\r\n$1\r\na\r\n"
        assert result == expected

    def test_encode_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="Cannot encode"):
            encode(3.14)


# ═══════════════════════════════════════════════════════════════════════════════
# RESP DECODER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRESPDecoder:
    """Tests for the decode() function."""

    def _stream(self, data):
        """Create a buffered stream from raw bytes."""
        return io.BytesIO(data)

    def test_decode_simple_string(self):
        assert decode(self._stream(b"+OK\r\n")) == "OK"

    def test_decode_empty_simple_string(self):
        assert decode(self._stream(b"+\r\n")) == ""

    def test_decode_error(self):
        result = decode(self._stream(b"-ERR bad command\r\n"))
        assert isinstance(result, Error)
        assert result.message == "ERR bad command"

    def test_decode_integer(self):
        assert decode(self._stream(b":42\r\n")) == 42

    def test_decode_negative_integer(self):
        assert decode(self._stream(b":-1\r\n")) == -1

    def test_decode_zero(self):
        assert decode(self._stream(b":0\r\n")) == 0

    def test_decode_bulk_string(self):
        assert decode(self._stream(b"$5\r\nhello\r\n")) == "hello"

    def test_decode_empty_bulk_string(self):
        assert decode(self._stream(b"$0\r\n\r\n")) == ""

    def test_decode_null_bulk_string(self):
        assert decode(self._stream(b"$-1\r\n")) is None

    def test_decode_array(self):
        data = b"*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n"
        result = decode(self._stream(data))
        assert result == ["GET", "key"]

    def test_decode_empty_array(self):
        assert decode(self._stream(b"*0\r\n")) == []

    def test_decode_null_array(self):
        assert decode(self._stream(b"*-1\r\n")) is None

    def test_decode_array_with_integers(self):
        data = b"*3\r\n:1\r\n:2\r\n:3\r\n"
        assert decode(self._stream(data)) == [1, 2, 3]

    def test_decode_array_with_null(self):
        data = b"*3\r\n$5\r\nhello\r\n$-1\r\n$5\r\nworld\r\n"
        assert decode(self._stream(data)) == ["hello", None, "world"]

    def test_decode_disconnection_raises(self):
        with pytest.raises(ConnectionError):
            decode(self._stream(b""))

    def test_decode_unknown_prefix_raises(self):
        with pytest.raises(ValueError, match="Unknown RESP prefix"):
            decode(self._stream(b"~unknown\r\n"))


# ═══════════════════════════════════════════════════════════════════════════════
# RESP ROUND-TRIP TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRESPRoundTrip:
    """Encoding then decoding should return the original value."""

    def _roundtrip(self, value):
        encoded = encode(value)
        return decode(io.BytesIO(encoded))

    def test_roundtrip_none(self):
        assert self._roundtrip(None) is None

    def test_roundtrip_integer(self):
        assert self._roundtrip(42) == 42

    def test_roundtrip_string(self):
        assert self._roundtrip("hello world") == "hello world"

    def test_roundtrip_empty_string(self):
        assert self._roundtrip("") == ""

    def test_roundtrip_list_of_strings(self):
        assert self._roundtrip(["a", "b", "c"]) == ["a", "b", "c"]

    def test_roundtrip_list_of_integers(self):
        assert self._roundtrip([1, 2, 3]) == [1, 2, 3]

    def test_roundtrip_mixed_list(self):
        assert self._roundtrip(["hello", 42, None]) == ["hello", 42, None]

    def test_roundtrip_empty_list(self):
        assert self._roundtrip([]) == []

    def test_roundtrip_error(self):
        result = self._roundtrip(Error("ERR oops"))
        assert isinstance(result, Error)
        assert result.message == "ERR oops"


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestStorage:
    """Tests for the Storage class (without expiry)."""

    @pytest.fixture
    def store(self):
        s = Storage()
        yield s
        s.shutdown()

    def test_get_missing_key(self, store):
        assert store.get("nonexistent") is None

    def test_set_and_get(self, store):
        store.set("key", "value")
        assert store.get("key") == "value"

    def test_overwrite_value(self, store):
        store.set("key", "v1")
        store.set("key", "v2")
        assert store.get("key") == "v2"

    def test_set_empty_string(self, store):
        store.set("key", "")
        assert store.get("key") == ""

    def test_set_numeric_string(self, store):
        store.set("num", "42")
        assert store.get("num") == "42"

    def test_delete_existing_key(self, store):
        store.set("key", "val")
        assert store.delete("key") == 1
        assert store.get("key") is None

    def test_delete_missing_key(self, store):
        assert store.delete("nope") == 0

    def test_delete_multiple_keys(self, store):
        store.set("a", "1")
        store.set("b", "2")
        store.set("c", "3")
        assert store.delete("a", "b", "missing") == 2

    def test_exists_present(self, store):
        store.set("key", "val")
        assert store.exists("key") == 1

    def test_exists_missing(self, store):
        assert store.exists("nope") == 0

    def test_exists_multiple(self, store):
        store.set("a", "1")
        store.set("b", "2")
        assert store.exists("a", "b", "c") == 2

    def test_keys_all(self, store):
        store.set("apple", "1")
        store.set("banana", "2")
        store.set("avocado", "3")
        result = sorted(store.keys("*"))
        assert result == ["apple", "avocado", "banana"]

    def test_keys_pattern(self, store):
        store.set("apple", "1")
        store.set("banana", "2")
        store.set("avocado", "3")
        result = sorted(store.keys("a*"))
        assert result == ["apple", "avocado"]

    def test_keys_empty_store(self, store):
        assert store.keys("*") == []

    def test_incr_new_key(self, store):
        assert store.incr("counter") == 1

    def test_incr_existing(self, store):
        store.set("counter", "10")
        assert store.incr("counter") == 11

    def test_decr_new_key(self, store):
        assert store.decr("counter") == -1

    def test_decr_existing(self, store):
        store.set("counter", "10")
        assert store.decr("counter") == 9

    def test_incr_non_integer_raises(self, store):
        store.set("key", "not a number")
        with pytest.raises(ValueError, match="not an integer"):
            store.incr("key")

    def test_flush(self, store):
        store.set("a", "1")
        store.set("b", "2")
        store.flush()
        assert store.size() == 0
        assert store.get("a") is None

    def test_size(self, store):
        assert store.size() == 0
        store.set("a", "1")
        assert store.size() == 1
        store.set("b", "2")
        assert store.size() == 2
        store.delete("a")
        assert store.size() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE EXPIRY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestStorageExpiry:
    """Tests for key expiration in the Storage class."""

    @pytest.fixture
    def store(self):
        s = Storage()
        yield s
        s.shutdown()

    def test_set_with_ttl_before_expiry(self, store):
        store.set("key", "val", ex=10)
        assert store.get("key") == "val"

    def test_set_with_ttl_after_expiry(self, store):
        store.set("key", "val", ex=0.1)
        time.sleep(0.2)
        assert store.get("key") is None

    def test_ttl_no_expiry(self, store):
        store.set("key", "val")
        assert store.ttl("key") == -1

    def test_ttl_with_expiry(self, store):
        store.set("key", "val", ex=10)
        ttl = store.ttl("key")
        assert 8 <= ttl <= 10

    def test_ttl_missing_key(self, store):
        assert store.ttl("nope") == -2

    def test_ttl_expired_key(self, store):
        store.set("key", "val", ex=0.1)
        time.sleep(0.2)
        assert store.ttl("key") == -2

    def test_expire_existing_key(self, store):
        store.set("key", "val")
        assert store.expire("key", 10) is True
        ttl = store.ttl("key")
        assert 8 <= ttl <= 10

    def test_expire_missing_key(self, store):
        assert store.expire("nope", 10) is False

    def test_overwrite_clears_ttl(self, store):
        store.set("key", "val", ex=5)
        store.set("key", "new val")
        assert store.ttl("key") == -1

    def test_exists_expired_key(self, store):
        store.set("key", "val", ex=0.1)
        time.sleep(0.2)
        assert store.exists("key") == 0

    def test_keys_excludes_expired(self, store):
        store.set("alive", "yes")
        store.set("dying", "soon", ex=0.1)
        time.sleep(0.2)
        assert store.keys("*") == ["alive"]

    def test_size_excludes_expired(self, store):
        store.set("a", "1")
        store.set("b", "2", ex=0.1)
        time.sleep(0.2)
        assert store.size() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND PROCESSOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandProcessor:
    """Tests for the CommandProcessor — command dispatch and argument handling."""

    @pytest.fixture
    def proc(self):
        storage = Storage()
        processor = CommandProcessor(storage)
        yield processor
        storage.shutdown()

    # ── connection ──────────────────────────────────────────────────────────

    def test_ping(self, proc):
        assert proc.execute("PING") == "PONG"

    def test_ping_with_message(self, proc):
        assert proc.execute("PING", "hello") == "hello"

    def test_echo(self, proc):
        assert proc.execute("ECHO", "hello") == "hello"

    def test_command(self, proc):
        """COMMAND returns a list (for redis-cli compatibility)."""
        assert isinstance(proc.execute("COMMAND"), list)

    # ── string commands ─────────────────────────────────────────────────────

    def test_get_set(self, proc):
        proc.execute("SET", "key", "value")
        assert proc.execute("GET", "key") == "value"

    def test_get_missing(self, proc):
        assert proc.execute("GET", "nope") is None

    def test_set_returns_ok(self, proc):
        assert proc.execute("SET", "k", "v") == "OK"

    def test_set_with_ex(self, proc):
        proc.execute("SET", "k", "v", "EX", "10")
        result = proc.execute("TTL", "k")
        assert 8 <= result <= 10

    def test_set_with_px(self, proc):
        proc.execute("SET", "k", "v", "PX", "10000")
        result = proc.execute("TTL", "k")
        assert 8 <= result <= 10

    def test_set_ex_invalid(self, proc):
        result = proc.execute("SET", "k", "v", "EX", "notnum")
        assert isinstance(result, Error)

    def test_set_ex_zero(self, proc):
        result = proc.execute("SET", "k", "v", "EX", "0")
        assert isinstance(result, Error)

    def test_incr(self, proc):
        proc.execute("SET", "n", "10")
        assert proc.execute("INCR", "n") == 11

    def test_incr_new_key(self, proc):
        assert proc.execute("INCR", "n") == 1

    def test_incr_non_integer(self, proc):
        proc.execute("SET", "s", "abc")
        result = proc.execute("INCR", "s")
        assert isinstance(result, Error)

    def test_decr(self, proc):
        proc.execute("SET", "n", "10")
        assert proc.execute("DECR", "n") == 9

    def test_decr_new_key(self, proc):
        assert proc.execute("DECR", "n") == -1

    # ── key commands ────────────────────────────────────────────────────────

    def test_del_single(self, proc):
        proc.execute("SET", "key", "val")
        assert proc.execute("DEL", "key") == 1
        assert proc.execute("GET", "key") is None

    def test_del_multiple(self, proc):
        proc.execute("SET", "a", "1")
        proc.execute("SET", "b", "2")
        assert proc.execute("DEL", "a", "b", "c") == 2

    def test_del_no_args(self, proc):
        result = proc.execute("DEL")
        assert isinstance(result, Error)

    def test_exists(self, proc):
        proc.execute("SET", "key", "val")
        assert proc.execute("EXISTS", "key") == 1

    def test_exists_missing(self, proc):
        assert proc.execute("EXISTS", "nope") == 0

    def test_exists_multiple(self, proc):
        proc.execute("SET", "a", "1")
        proc.execute("SET", "b", "2")
        assert proc.execute("EXISTS", "a", "b", "c") == 2

    def test_expire(self, proc):
        proc.execute("SET", "key", "val")
        assert proc.execute("EXPIRE", "key", "10") == 1
        ttl = proc.execute("TTL", "key")
        assert 8 <= ttl <= 10

    def test_expire_missing_key(self, proc):
        assert proc.execute("EXPIRE", "nope", "10") == 0

    def test_ttl_no_expiry(self, proc):
        proc.execute("SET", "key", "val")
        assert proc.execute("TTL", "key") == -1

    def test_ttl_missing(self, proc):
        assert proc.execute("TTL", "nope") == -2

    def test_keys_pattern(self, proc):
        proc.execute("SET", "apple", "1")
        proc.execute("SET", "banana", "2")
        proc.execute("SET", "avocado", "3")
        result = sorted(proc.execute("KEYS", "a*"))
        assert result == ["apple", "avocado"]

    # ── batch commands ──────────────────────────────────────────────────────

    def test_mset_mget(self, proc):
        proc.execute("MSET", "a", "1", "b", "2", "c", "3")
        assert proc.execute("MGET", "a", "b", "c") == ["1", "2", "3"]

    def test_mget_with_missing(self, proc):
        proc.execute("SET", "a", "1")
        assert proc.execute("MGET", "a", "b") == ["1", None]

    def test_mset_odd_args(self, proc):
        result = proc.execute("MSET", "a", "1", "b")
        assert isinstance(result, Error)

    def test_mget_no_args(self, proc):
        result = proc.execute("MGET")
        assert isinstance(result, Error)

    # ── server commands ─────────────────────────────────────────────────────

    def test_flushdb(self, proc):
        proc.execute("SET", "a", "1")
        proc.execute("SET", "b", "2")
        assert proc.execute("FLUSHDB") == "OK"
        assert proc.execute("DBSIZE") == 0

    def test_dbsize(self, proc):
        assert proc.execute("DBSIZE") == 0
        proc.execute("SET", "a", "1")
        assert proc.execute("DBSIZE") == 1

    def test_info(self, proc):
        result = proc.execute("INFO")
        assert "mini_redis_version" in result

    # ── error handling ──────────────────────────────────────────────────────

    def test_unknown_command(self, proc):
        result = proc.execute("NOTACMD")
        assert isinstance(result, Error)
        assert "unknown command" in result.message

    def test_empty_command(self, proc):
        result = proc.execute()
        assert isinstance(result, Error)

    def test_case_insensitive(self, proc):
        """Commands should be case-insensitive."""
        proc.execute("set", "key", "val")
        assert proc.execute("get", "key") == "val"
        assert proc.execute("Get", "key") == "val"


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerIntegration:
    """Start a real server, connect a client, run commands over TCP."""

    @pytest.fixture
    def server_and_client(self):
        """Start server on a random-ish port, yield a connected client."""
        # Use a non-standard port to avoid conflict with real Redis
        port = 16399
        for attempt in range(10):
            try:
                server = RedisServer("127.0.0.1", port + attempt)
                port = port + attempt
                break
            except OSError:
                continue
        else:
            pytest.skip("Could not find a free port")

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        # Give the server a moment to start
        time.sleep(0.1)

        client = RedisClient("127.0.0.1", port)
        client.connect()

        yield server, client

        client.close()
        server.shutdown()

    def test_ping_pong(self, server_and_client):
        _, client = server_and_client
        assert client.execute("PING") == "PONG"

    def test_set_get(self, server_and_client):
        _, client = server_and_client
        assert client.execute("SET", "greeting", "hello") == "OK"
        assert client.execute("GET", "greeting") == "hello"

    def test_incr_decr(self, server_and_client):
        _, client = server_and_client
        assert client.execute("SET", "n", "0") == "OK"
        assert client.execute("INCR", "n") == 1
        assert client.execute("INCR", "n") == 2
        assert client.execute("DECR", "n") == 1

    def test_mset_mget(self, server_and_client):
        _, client = server_and_client
        assert client.execute("MSET", "a", "1", "b", "2") == "OK"
        assert client.execute("MGET", "a", "b") == ["1", "2"]

    def test_del_exists(self, server_and_client):
        _, client = server_and_client
        client.execute("SET", "key", "val")
        assert client.execute("EXISTS", "key") == 1
        assert client.execute("DEL", "key") == 1
        assert client.execute("EXISTS", "key") == 0

    def test_expire_and_ttl(self, server_and_client):
        _, client = server_and_client
        client.execute("SET", "key", "val")
        assert client.execute("EXPIRE", "key", "10") == 1
        ttl = client.execute("TTL", "key")
        assert 8 <= ttl <= 10

    def test_set_with_ex(self, server_and_client):
        _, client = server_and_client
        client.execute("SET", "temp", "val", "EX", "1")
        assert client.execute("GET", "temp") == "val"
        time.sleep(1.2)
        assert client.execute("GET", "temp") is None

    def test_keys(self, server_and_client):
        _, client = server_and_client
        client.execute("MSET", "alpha", "1", "beta", "2", "gamma", "3")
        result = sorted(client.execute("KEYS", "*"))
        assert "alpha" in result
        assert "beta" in result
        assert "gamma" in result

    def test_flushdb_dbsize(self, server_and_client):
        _, client = server_and_client
        client.execute("MSET", "a", "1", "b", "2")
        assert client.execute("DBSIZE") == 2
        assert client.execute("FLUSHDB") == "OK"
        assert client.execute("DBSIZE") == 0

    def test_error_unknown_command(self, server_and_client):
        _, client = server_and_client
        result = client.execute("FAKECMD")
        assert isinstance(result, Error)

    def test_concurrent_clients(self, server_and_client):
        """Two clients can operate independently."""
        server, client1 = server_and_client
        port = server.server_address[1]

        client2 = RedisClient("127.0.0.1", port)
        client2.connect()

        try:
            client1.execute("SET", "from1", "hello")
            client2.execute("SET", "from2", "world")

            assert client1.execute("GET", "from2") == "world"
            assert client2.execute("GET", "from1") == "hello"
        finally:
            client2.close()


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
