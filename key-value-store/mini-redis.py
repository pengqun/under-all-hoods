"""
A Miniature Redis Server — in Python
======================================

How does Redis store and retrieve data so fast? This module implements a
mini Redis server from scratch, covering the RESP wire protocol, an
in-memory storage engine with key expiration, and a threaded TCP server
that is compatible with the real ``redis-cli``.

Architecture
------------

::

    redis-cli / RedisClient
           │
           ▼
    ┌─────────────────┐
    │   TCP SERVER     │  Accept connections, one thread per client.
    │ (socketserver)   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  RESP PROTOCOL   │  Bytes on the wire  ↔  Python objects.
    │    HANDLER       │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │    COMMAND        │  Dispatch parsed commands to handler methods.
    │   PROCESSOR      │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │    STORAGE       │  dict + per-key TTL expiry (lazy + passive).
    │    ENGINE        │
    └─────────────────┘

Reference
---------
- `Building a simple Redis server with Python
  <http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/>`_
  by Charles Leifer
"""

import fnmatch
import io
import socket
import socketserver
import threading
import time


# ═══════════════════════════════════════════════════════════════════════════════
# RESP PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════════

class Error:
    """Represents a Redis error value on the wire."""

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"Error({self.message!r})"

    def __eq__(self, other):
        return isinstance(other, Error) and self.message == other.message


def encode(value):
    """Encode a Python value into RESP bytes.

    Mapping:
        None        →  $-1\\r\\n                   (Null bulk string)
        bool(True)  →  :1\\r\\n                    (Integer)
        int         →  :42\\r\\n                   (Integer)
        str         →  $5\\r\\nhello\\r\\n           (Bulk string)
        Error       →  -ERR message\\r\\n           (Error)
        list/tuple  →  *N\\r\\n …elements…          (Array)
    """
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, bool):
        return f":{int(value)}\r\n".encode()
    if isinstance(value, int):
        return f":{value}\r\n".encode()
    if isinstance(value, Error):
        return f"-{value.message}\r\n".encode()
    if isinstance(value, str):
        encoded = value.encode()
        return f"${len(encoded)}\r\n".encode() + encoded + b"\r\n"
    if isinstance(value, bytes):
        return f"${len(value)}\r\n".encode() + value + b"\r\n"
    if isinstance(value, (list, tuple)):
        parts = [f"*{len(value)}\r\n".encode()]
        for item in value:
            parts.append(encode(item))
        return b"".join(parts)
    raise TypeError(f"Cannot encode type {type(value).__name__}")


def decode(stream):
    """Decode one RESP value from a buffered stream (file-like object).

    Returns the decoded Python value, or raises ``ConnectionError``
    when the client disconnects.
    """
    line = stream.readline()
    if not line:
        raise ConnectionError("Client disconnected")

    # Strip the trailing \r\n
    line = line.rstrip(b"\r\n")
    if not line:
        raise ConnectionError("Client disconnected")

    prefix = chr(line[0])
    payload = line[1:]

    if prefix == "+":
        # Simple string
        return payload.decode()

    if prefix == "-":
        # Error
        return Error(payload.decode())

    if prefix == ":":
        # Integer
        return int(payload)

    if prefix == "$":
        # Bulk string
        length = int(payload)
        if length == -1:
            return None
        data = stream.read(length + 2)  # +2 for trailing \r\n
        if not data:
            raise ConnectionError("Client disconnected")
        return data[:length].decode()

    if prefix == "*":
        # Array
        count = int(payload)
        if count == -1:
            return None
        return [decode(stream) for _ in range(count)]

    raise ValueError(f"Unknown RESP prefix: {prefix!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class Storage:
    """In-memory key-value store with per-key TTL expiration.

    Expiration uses two strategies, just like real Redis:

    - **Lazy**: every read checks whether the key has expired.
    - **Passive**: a background thread periodically samples keys and
      removes the expired ones.
    """

    def __init__(self):
        self._data = {}      # key → value
        self._expires = {}   # key → expiry timestamp (time.time())
        self._lock = threading.Lock()

        # Start the passive-expiry background thread
        self._running = True
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleaner.start()

    def shutdown(self):
        self._running = False

    # ── core operations ─────────────────────────────────────────────────────

    def get(self, key):
        with self._lock:
            if self._is_expired(key):
                self._delete_key(key)
                return None
            return self._data.get(key)

    def set(self, key, value, ex=None):
        with self._lock:
            self._data[key] = value
            if ex is not None:
                self._expires[key] = time.time() + ex
            else:
                self._expires.pop(key, None)

    def delete(self, *keys):
        count = 0
        with self._lock:
            for key in keys:
                if key in self._data:
                    self._delete_key(key)
                    count += 1
        return count

    def exists(self, *keys):
        count = 0
        with self._lock:
            for key in keys:
                if self._is_expired(key):
                    self._delete_key(key)
                elif key in self._data:
                    count += 1
        return count

    def expire(self, key, seconds):
        with self._lock:
            if self._is_expired(key):
                self._delete_key(key)
                return False
            if key not in self._data:
                return False
            self._expires[key] = time.time() + seconds
            return True

    def ttl(self, key):
        with self._lock:
            if self._is_expired(key):
                self._delete_key(key)
                return -2
            if key not in self._data:
                return -2
            if key not in self._expires:
                return -1
            remaining = self._expires[key] - time.time()
            return max(0, int(remaining))

    def keys(self, pattern="*"):
        with self._lock:
            # Clean up expired keys lazily during scan
            result = []
            for key in list(self._data):
                if self._is_expired(key):
                    self._delete_key(key)
                elif fnmatch.fnmatch(key, pattern):
                    result.append(key)
            return result

    def incr(self, key):
        return self._incr_by(key, 1)

    def decr(self, key):
        return self._incr_by(key, -1)

    def flush(self):
        with self._lock:
            self._data.clear()
            self._expires.clear()

    def size(self):
        with self._lock:
            # Count only non-expired keys
            count = 0
            for key in list(self._data):
                if self._is_expired(key):
                    self._delete_key(key)
                else:
                    count += 1
            return count

    # ── internal helpers ────────────────────────────────────────────────────

    def _incr_by(self, key, delta):
        with self._lock:
            if self._is_expired(key):
                self._delete_key(key)
            val = self._data.get(key, "0")
            try:
                num = int(val)
            except (ValueError, TypeError):
                raise ValueError("value is not an integer or out of range")
            num += delta
            self._data[key] = str(num)
            return num

    def _is_expired(self, key):
        """Check if a key has expired. Must be called under _lock."""
        if key in self._expires:
            return time.time() > self._expires[key]
        return False

    def _delete_key(self, key):
        """Remove a key and its expiry. Must be called under _lock."""
        self._data.pop(key, None)
        self._expires.pop(key, None)

    def _cleanup_loop(self):
        """Background thread: sample expired keys every 100ms."""
        while self._running:
            time.sleep(0.1)
            with self._lock:
                expired = [
                    k for k in list(self._expires)
                    if time.time() > self._expires[k]
                ]
                for key in expired:
                    self._delete_key(key)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

class CommandProcessor:
    """Dispatch Redis commands to handler methods.

    Each ``handle_<cmd>`` method receives the argument list (strings)
    and returns a Python value that will be RESP-encoded back to the
    client.
    """

    def __init__(self, storage):
        self._storage = storage

    def execute(self, *args):
        if not args:
            return Error("ERR no command given")

        cmd = args[0].upper()
        cmd_args = args[1:]

        handler = getattr(self, f"handle_{cmd.lower()}", None)
        if handler is None:
            return Error(f"ERR unknown command '{cmd}'")

        try:
            return handler(*cmd_args)
        except TypeError:
            return Error(f"ERR wrong number of arguments for '{cmd}' command")

    # ── connection ──────────────────────────────────────────────────────────

    def handle_ping(self, *args):
        if len(args) > 1:
            return Error("ERR wrong number of arguments for 'PING' command")
        if args:
            return args[0]
        return "PONG"

    def handle_echo(self, message):
        return message

    def handle_command(self, *args):
        # Minimal implementation — redis-cli sends COMMAND DOCS on connect
        return []

    # ── string operations ───────────────────────────────────────────────────

    def handle_get(self, key):
        return self._storage.get(key)

    def handle_set(self, key, value, *options):
        ex = None
        i = 0
        while i < len(options):
            opt = options[i].upper()
            if opt == "EX" and i + 1 < len(options):
                try:
                    ex = int(options[i + 1])
                except ValueError:
                    return Error("ERR value is not an integer or out of range")
                if ex <= 0:
                    return Error("ERR invalid expire time in 'set' command")
                i += 2
            elif opt == "PX" and i + 1 < len(options):
                try:
                    px = int(options[i + 1])
                except ValueError:
                    return Error("ERR value is not an integer or out of range")
                if px <= 0:
                    return Error("ERR invalid expire time in 'set' command")
                ex = px / 1000.0
                i += 2
            else:
                return Error(f"ERR syntax error")
                i += 1
        self._storage.set(key, value, ex=ex)
        return "OK"

    def handle_incr(self, key):
        try:
            return self._storage.incr(key)
        except ValueError as e:
            return Error(f"ERR {e}")

    def handle_decr(self, key):
        try:
            return self._storage.decr(key)
        except ValueError as e:
            return Error(f"ERR {e}")

    # ── key operations ──────────────────────────────────────────────────────

    def handle_del(self, *keys):
        if not keys:
            return Error("ERR wrong number of arguments for 'DEL' command")
        return self._storage.delete(*keys)

    def handle_exists(self, *keys):
        if not keys:
            return Error("ERR wrong number of arguments for 'EXISTS' command")
        return self._storage.exists(*keys)

    def handle_expire(self, key, seconds):
        try:
            seconds = int(seconds)
        except ValueError:
            return Error("ERR value is not an integer or out of range")
        if seconds <= 0:
            # Redis deletes the key when expire <= 0
            self._storage.delete(key)
            return 1
        return int(self._storage.expire(key, seconds))

    def handle_ttl(self, key):
        return self._storage.ttl(key)

    def handle_keys(self, pattern):
        return self._storage.keys(pattern)

    # ── batch operations ────────────────────────────────────────────────────

    def handle_mget(self, *keys):
        if not keys:
            return Error("ERR wrong number of arguments for 'MGET' command")
        return [self._storage.get(k) for k in keys]

    def handle_mset(self, *args):
        if not args or len(args) % 2 != 0:
            return Error("ERR wrong number of arguments for 'MSET' command")
        for i in range(0, len(args), 2):
            self._storage.set(args[i], args[i + 1])
        return "OK"

    # ── server operations ───────────────────────────────────────────────────

    def handle_flushdb(self, *args):
        self._storage.flush()
        return "OK"

    def handle_dbsize(self):
        return self._storage.size()

    def handle_info(self, *args):
        return (
            "# Server\r\n"
            "mini_redis_version:1.0.0\r\n"
            "python_version:3.x\r\n"
            f"# Keyspace\r\n"
            f"db0:keys={self._storage.size()}\r\n"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TCP SERVER
# ═══════════════════════════════════════════════════════════════════════════════

class RedisHandler(socketserver.StreamRequestHandler):
    """Handle one client connection: read commands, send responses."""

    def handle(self):
        stream = self.rfile
        while True:
            try:
                data = decode(stream)
            except (ConnectionError, ValueError):
                break

            if isinstance(data, list) and data:
                result = self.server.processor.execute(*data)
            elif isinstance(data, str):
                # Inline command (e.g. "PING\r\n")
                parts = data.split()
                if parts:
                    result = self.server.processor.execute(*parts)
                else:
                    continue
            else:
                result = Error("ERR invalid command format")

            try:
                self.wfile.write(encode(result))
                self.wfile.flush()
            except BrokenPipeError:
                break


class RedisServer(socketserver.ThreadingTCPServer):
    """A threaded TCP server that speaks the RESP protocol."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host="127.0.0.1", port=6379):
        self.storage = Storage()
        self.processor = CommandProcessor(self.storage)
        super().__init__((host, port), RedisHandler)

    def shutdown(self):
        self.storage.shutdown()
        super().shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT (for demo / testing)
# ═══════════════════════════════════════════════════════════════════════════════

class RedisClient:
    """A minimal Redis client that speaks RESP."""

    def __init__(self, host="127.0.0.1", port=6379):
        self._host = host
        self._port = port
        self._sock = None
        self._stream = None

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))
        self._stream = self._sock.makefile("rb")

    def close(self):
        if self._stream:
            self._stream.close()
        if self._sock:
            self._sock.close()

    def execute(self, *args):
        """Send a command and return the decoded response."""
        cmd = encode(list(args))
        self._sock.sendall(cmd)
        return decode(self._stream)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — demo
# ═══════════════════════════════════════════════════════════════════════════════

def _demo():
    """Start the server, run a few commands, print the results."""
    import sys

    port = 16379  # Non-privileged port for demo

    server = RedisServer("127.0.0.1", port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("Mini-Redis Server — Python Edition")
    print("=" * 40)
    print(f"\n  Server listening on 127.0.0.1:{port}\n")

    with RedisClient("127.0.0.1", port) as client:
        demos = [
            (("PING",),                          "Ping the server"),
            (("SET", "greeting", "hello world"),  "SET greeting"),
            (("GET", "greeting"),                 "GET greeting"),
            (("SET", "counter", "0"),             "SET counter = 0"),
            (("INCR", "counter"),                 "INCR counter"),
            (("INCR", "counter"),                 "INCR counter again"),
            (("INCR", "counter"),                 "INCR counter once more"),
            (("GET", "counter"),                  "GET counter"),
            (("MSET", "a", "1", "b", "2", "c", "3"), "MSET a=1 b=2 c=3"),
            (("MGET", "a", "b", "c"),             "MGET a b c"),
            (("KEYS", "*"),                        "KEYS *"),
            (("DBSIZE",),                          "DBSIZE"),
            (("DEL", "a", "b", "c"),               "DEL a b c"),
            (("DBSIZE",),                          "DBSIZE after DEL"),
            (("SET", "temp", "gone soon", "EX", "1"), "SET temp with 1s TTL"),
            (("TTL", "temp"),                      "TTL temp"),
            (("GET", "temp"),                      "GET temp (before expiry)"),
        ]

        for args, label in demos:
            result = client.execute(*args)
            cmd_str = " ".join(args)
            print(f"  {label}:")
            print(f"    > {cmd_str}")
            print(f"    {result!r}\n")

        # Wait for expiry
        print("  (waiting 1.5s for temp to expire...)\n")
        time.sleep(1.5)

        result = client.execute("GET", "temp")
        print("  GET temp (after expiry):")
        print(f"    > GET temp")
        print(f"    {result!r}\n")

        client.execute("FLUSHDB")
        print("  FLUSHDB — all keys cleared.")

    server.shutdown()
    print("\n  Server stopped.")


if __name__ == "__main__":
    _demo()
