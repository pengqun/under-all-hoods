# Key-Value Store (Redis): Under the Hood

How does Redis store and retrieve data so fast? This module implements a mini Redis server in Python, covering the RESP wire protocol, an in-memory storage engine with key expiration, and a threaded TCP server — all in a single file.

## What it Does

This server speaks the real Redis protocol (RESP), so you can test it with `redis-cli` or any Redis client library:

```
CLIENT                              SERVER
──────                              ──────
PING                           →    PONG
SET greeting "hello world"     →    OK
GET greeting                   →    "hello world"
SET counter 0                  →    OK
INCR counter                   →    (integer) 1
INCR counter                   →    (integer) 2
SET temp "bye" EX 5            →    OK     (expires in 5 seconds)
KEYS *                         →    1) "greeting"  2) "counter"  3) "temp"
```

## The Four Layers

Every request flows through four layers, top to bottom:

```
Bytes on the wire  →  RESP decode  →  Command dispatch  →  Storage  →  RESP encode  →  Bytes back
      Layer 1            Layer 2          Layer 3           Layer 4         Layer 2
```

### Layer 1: TCP Server

The server uses Python's `socketserver.ThreadingTCPServer` — one thread per client connection. When a client connects, a handler thread enters a read loop: decode a command, execute it, encode the result, send it back.

```
Client connects
  → Server spawns handler thread
    → Loop: decode → execute → encode → send
  → Client disconnects, thread exits
```

No async frameworks, no event loops — just threads and sockets. Simple enough to read, concurrent enough to be useful.

### Layer 2: RESP Protocol

Redis uses a simple text-based protocol called **RESP** (REdis Serialization Protocol). Each data type has a one-character prefix:

| Prefix | Type | Example (on the wire) | Python value |
|--------|------|-----------------------|-------------|
| `+` | Simple String | `+OK\r\n` | `"OK"` |
| `-` | Error | `-ERR unknown\r\n` | `Error(...)` |
| `:` | Integer | `:42\r\n` | `42` |
| `$` | Bulk String | `$5\r\nhello\r\n` | `"hello"` |
| `*` | Array | `*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n` | `["GET", "key"]` |

Null values are `$-1\r\n`. Every message ends with `\r\n`. That's the entire protocol.

A client sends commands as RESP arrays of bulk strings. The server responds with the appropriate type. Two functions handle everything:

- `encode(value)` — Python object → RESP bytes
- `decode(stream)` — RESP bytes from socket → Python object

### Layer 3: Command Processor

The command processor maps command names to handler methods. When it receives `["SET", "key", "value", "EX", "10"]`, it calls `handle_set("key", "value", "EX", "10")`.

Sixteen commands are implemented:

| Category | Commands |
|----------|----------|
| Connection | `PING`, `ECHO` |
| String | `GET`, `SET` (with EX/PX), `INCR`, `DECR` |
| Key | `DEL`, `EXISTS`, `EXPIRE`, `TTL`, `KEYS` |
| Batch | `MGET`, `MSET` |
| Server | `FLUSHDB`, `DBSIZE`, `INFO` |

### Layer 4: Storage Engine

At its core, Redis is a Python dictionary with superpowers. Our storage is literally:

```python
_data    = {}   # key → value
_expires = {}   # key → expiry timestamp
```

The interesting part is **key expiration**. When you `SET key value EX 5`, the key should vanish after 5 seconds. Real Redis uses two strategies, and so do we:

- **Lazy expiration**: every time a key is accessed (`GET`, `EXISTS`, etc.), check if it's expired. If yes, delete it and pretend it was never there.
- **Passive expiration**: a background thread wakes up every 100ms, samples keys with TTLs, and removes expired ones. This prevents memory leaks from keys nobody ever reads again.

## Running It

```bash
cd key-value-store
python mini-redis.py
```

Output:

```
Mini-Redis Server — Python Edition
========================================

  Server listening on 127.0.0.1:16379

  Ping the server:
    > PING
    'PONG'

  SET greeting:
    > SET greeting hello world
    'OK'

  GET greeting:
    > GET greeting
    'hello world'

  SET counter = 0:
    > SET counter 0
    'OK'

  INCR counter:
    > INCR counter
    1

  INCR counter again:
    > INCR counter
    2

  INCR counter once more:
    > INCR counter
    3

  GET counter:
    > GET counter
    '3'

  ...

  SET temp with 1s TTL:
    > SET temp gone soon EX 1
    'OK'

  (waiting 1.5s for temp to expire...)

  GET temp (after expiry):
    > GET temp
    None

  FLUSHDB — all keys cleared.

  Server stopped.
```

You can also test with the real `redis-cli`:

```bash
# Terminal 1
python mini-redis.py   # starts on port 16379

# Terminal 2
redis-cli -p 16379
127.0.0.1:16379> PING
PONG
127.0.0.1:16379> SET hello world
OK
127.0.0.1:16379> GET hello
"world"
```

## Running Tests

```bash
cd key-value-store
python -m pytest test_redis.py -v
```

The test suite covers each layer in isolation plus end-to-end integration tests — 90+ test cases covering RESP encoding/decoding, storage operations, key expiration, command processing, error handling, and concurrent client access.

## Implementation: `mini-redis.py`

### References

- [Building a simple Redis server with Python](http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/) by Charles Leifer — the tutorial this implementation draws from
- [Redis Protocol specification (RESP)](https://redis.io/docs/reference/protocol-spec/) — the official RESP documentation
- [Redis Commands](https://redis.io/commands/) — the full Redis command reference
