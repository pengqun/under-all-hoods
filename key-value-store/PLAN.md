# Key-Value Store (Redis): Implementation Plan

## Overview

Implement a miniature Redis server in Python that speaks the real RESP (REdis Serialization Protocol), so it can be tested with any standard Redis client. The implementation covers TCP networking, protocol design, in-memory data structures, and key expiration — all in a single, readable Python file.

**Reference**: [Building a simple Redis server with Python](http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/) by Charles Leifer

## Architecture

The implementation consists of four layered components, each building on the one below:

```
 Redis Client (redis-cli, or our built-in client)
       │
       ▼
┌─────────────────┐
│   TCP SERVER    │  Accept connections, manage client sockets.
│  (socketserver) │  One thread per client via ThreadingMixIn.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ RESP PROTOCOL   │  Serialize and deserialize the Redis wire protocol.
│    HANDLER      │  Turns bytes ↔ Python objects (str, int, list, Error).
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    COMMAND       │  Dispatch parsed commands to handler methods.
│   PROCESSOR     │  Each Redis command = one Python method.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    STORAGE      │  In-memory dict with optional per-key TTL expiry.
│    ENGINE       │  Lazy expiration on access + passive cleanup.
└─────────────────┘
```

## Component Details

### 1. RESP Protocol Handler

The RESP protocol prefixes each data type with a special character:

| Prefix | Type | Example (wire format) | Python value |
|--------|------|-----------------------|-------------|
| `+` | Simple String | `+OK\r\n` | `"OK"` |
| `-` | Error | `-ERR unknown\r\n` | `Error("ERR unknown")` |
| `:` | Integer | `:42\r\n` | `42` |
| `$` | Bulk String | `$5\r\nhello\r\n` | `"hello"` |
| `*` | Array | `*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n` | `["GET", "key"]` |

Null values are represented as `$-1\r\n`.

**Implementation**: Two functions:
- `encode(value) -> bytes` — Python object → RESP bytes
- `decode(stream) -> object` — Read from socket stream → Python object

### 2. Storage Engine

A Python `dict` as the primary store, plus a parallel `dict` for expiry timestamps.

```python
_data = {}          # key → value
_expires = {}       # key → expiry_time (float, from time.time())
```

**Expiration strategy**:
- **Lazy**: On every read (`GET`, `EXISTS`, etc.), check if the key has expired. If yes, delete it and return as if it doesn't exist.
- **Passive**: A background thread periodically samples keys from `_expires` and removes expired ones. This prevents memory leaks from keys that are set-and-forgotten.

### 3. Command Processor

Each Redis command maps to a method. The server dispatches by command name.

**Commands to implement** (16 total):

| Category | Command | Description |
|----------|---------|-------------|
| Connection | `PING [msg]` | Return PONG or echo msg |
| Connection | `ECHO msg` | Echo the message back |
| String | `GET key` | Get value by key |
| String | `SET key value [EX s]` | Set key with optional TTL in seconds |
| String | `INCR key` | Increment integer value by 1 |
| String | `DECR key` | Decrement integer value by 1 |
| Key | `DEL key [key ...]` | Delete one or more keys |
| Key | `EXISTS key [key ...]` | Check if keys exist |
| Key | `EXPIRE key seconds` | Set TTL on existing key |
| Key | `TTL key` | Get remaining TTL (-1 = no expiry, -2 = missing) |
| Key | `KEYS pattern` | Find keys matching glob pattern |
| Batch | `MGET key [key ...]` | Get multiple values |
| Batch | `MSET key value [key value ...]` | Set multiple key-value pairs |
| Server | `FLUSHDB` | Clear all keys |
| Server | `DBSIZE` | Return number of keys |
| Server | `INFO` | Return server information |

### 4. TCP Server

Use Python's `socketserver.TCPServer` with `ThreadingMixIn` for concurrent client handling. This avoids external dependencies (no gevent/asyncio needed for the educational version) while still supporting multiple clients.

**Connection flow**:
```
Client connects via TCP
  → Server accepts, creates handler thread
    → Read loop: decode RESP → dispatch command → encode response → send
  → Client disconnects, thread exits
```

**Configuration**: Default host `127.0.0.1`, port `6379` (or configurable via CLI args).

## File Structure

```
key-value-store/
├── PLAN.md                  ← This file
├── README.md                ← Concept explanation (like other modules)
├── mini-redis.py            ← Complete implementation (~400-500 lines)
└── test_redis.py            ← Test suite (~500-600 lines)
```

### mini-redis.py Structure

```python
"""
A Miniature Redis Server — in Python
======================================
...top-level docstring with ASCII architecture diagram...
"""

# ═══════════════════════════════════════════════════════
# RESP PROTOCOL
# ═══════════════════════════════════════════════════════
class Error: ...              # Sentinel for Redis errors
def encode(value): ...        # Python → RESP bytes
def decode(stream): ...       # RESP stream → Python

# ═══════════════════════════════════════════════════════
# STORAGE ENGINE
# ═══════════════════════════════════════════════════════
class Storage:
    _data: dict
    _expires: dict
    def get(key): ...
    def set(key, value, ex=None): ...
    def delete(*keys): ...
    def exists(*keys): ...
    def expire(key, seconds): ...
    def ttl(key): ...
    def keys(pattern): ...
    def flush(): ...
    def size(): ...
    # internal: _is_expired(), _cleanup()

# ═══════════════════════════════════════════════════════
# COMMAND PROCESSOR
# ═══════════════════════════════════════════════════════
class CommandProcessor:
    def __init__(storage): ...
    def execute(command, *args): ...
    # One method per command: handle_get, handle_set, ...

# ═══════════════════════════════════════════════════════
# TCP SERVER
# ═══════════════════════════════════════════════════════
class RedisHandler(socketserver.StreamRequestHandler): ...
class RedisServer(socketserver.ThreadingTCPServer): ...

# ═══════════════════════════════════════════════════════
# CLIENT (for demo/testing)
# ═══════════════════════════════════════════════════════
class RedisClient:
    def connect(host, port): ...
    def execute(*args): ...

# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    # Start server, run demo commands, print results
```

## Test Plan

### test_redis.py Structure

Tests organized by component, following the same pattern as the compiler and interpreter test suites:

```
TestRESPEncoder          — encode() for each data type
TestRESPDecoder          — decode() for each data type, edge cases
TestStorage              — Storage class: get/set/delete/expire/TTL/keys
TestStorageExpiry        — Expiration: lazy deletion, TTL countdown
TestCommandProcessor     — Each command: normal + error cases
TestServerIntegration    — Start real server, connect client, run commands
```

**Estimated**: ~80-100 test cases.

### Key Test Scenarios

1. **RESP round-trip**: encode → decode == identity for all types
2. **GET/SET basics**: set a key, get it back, overwrite, get new value
3. **Expiry**: set key with EX, verify it disappears after TTL
4. **INCR/DECR**: increment non-existent key (starts from 0), error on non-integer value
5. **DEL/EXISTS**: delete multiple keys, check existence returns correct count
6. **KEYS pattern**: wildcard matching with `*` and `?`
7. **MGET/MSET**: batch operations, MGET with missing keys returns nil
8. **Concurrent clients**: two clients set/get without interference
9. **Error handling**: wrong number of arguments, wrong types, unknown commands
10. **Edge cases**: empty strings, very long values, binary-safe keys

## Design Decisions

1. **Pure Python stdlib** — No external dependencies. Uses `socketserver`, `threading`, `fnmatch`, `time`. Consistent with the project's "no frameworks, no bloat" philosophy.

2. **Real RESP protocol** — Compatible with `redis-cli` and any Redis client library. This makes the educational value much higher: you can test with real tools.

3. **Threading over async** — `ThreadingMixIn` is simpler to understand than asyncio/gevent. For an educational project, clarity beats performance.

4. **Lazy + passive expiry** — Demonstrates both strategies that real Redis uses, without over-engineering.

5. **Single file** — Entire implementation in one file, matching the project convention. Sections clearly delimited with comment banners.

## Compatibility with Real Redis

After implementation, the following should work:

```bash
# Terminal 1: start our server
python mini-redis.py

# Terminal 2: use the real redis-cli
redis-cli -p 6379
> PING
PONG
> SET greeting "hello world"
OK
> GET greeting
"hello world"
> SET counter 0
OK
> INCR counter
(integer) 1
> INCR counter
(integer) 2
> DEL greeting counter
(integer) 2
> KEYS *
(empty array)
```
