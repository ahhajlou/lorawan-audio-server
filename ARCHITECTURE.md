# Architecture

This document describes the software architecture of the lorawan-audio-server.

## Overview

The server acts as a smart relay in a LoRaWAN walkie-talkie network. It receives
audio packets from speaking nodes, acknowledges them on behalf of the receiver
(to reduce airtime), buffers them, and forwards them to the listening node(s).

```
Node A ──uplink──► Gateway (WM1302) ──MQTT──► ChirpStack ──MQTT──► This Server
Node B ◄──downlink── Gateway ◄── ChirpStack ◄── This Server
```

## Hardware Constraints

| Component | Detail |
|---|---|
| End nodes | RAK3112 (ESP32 + SX1262) |
| Gateway | WM1302 with Raspberry Pi 5 |
| Network server | ChirpStack |
| Uplink channels | 8 (multi-channel receiver) |
| Downlink channels | 1 (single radio, serialized) |
| Frequency plan | EU868 (duty cycle disabled) |
| LoRaWAN class | **C** (always-on receiver for low latency) |

Class C means the receiving node's radio is always open (except when transmitting),
so the server can send downlinks at any time without waiting for the receiver to uplink.

## Thread Model

Two threads. No async. No thread pools.

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│   MQTT THREAD (paho)        │    │   FLUSH THREAD              │
│                             │    │                             │
│   on_message callback:      │    │   Every FLUSH_INTERVAL ms:  │
│     1. Parse JSON envelope  │    │     For each receiver with  │
│     2. Deserialize bytes    │    │     pending packets:        │
│        → Packet object      │    │       Pop one packet        │
│     3. Resolve addresses    │    │       Build downlink        │
│     4. ACK sender           │    │       Publish to ChirpStack │
│     5. Enqueue in buffer    │    │                             │
│                             │    │                             │
│   Role: Producer            │    │   Role: Consumer            │
└──────────────┬──────────────┘    └──────────────┬──────────────┘
               │                                  │
               ▼                                  ▼
        ┌─────────────────────────────────────────────┐
        │              SHARED STATE                    │
        │                                             │
        │  BufferManager (dict of StreamBuffers)      │
        │    └─ per-receiver: StreamBuffer            │
        │         └─ _pending: list[Packet]           │
        │                                             │
        │  DeviceRegistry (address ↔ DevEUI map)     │
        └─────────────────────────────────────────────┘
```

### Why Two Threads

- The MQTT thread (paho `loop_start`) handles network I/O and dispatches
  uplink messages to handlers. It produces packets into per-receiver buffers.
- The flush thread consumes from those buffers and publishes downlinks to
  ChirpStack, which handles radio scheduling on the single downlink channel.
- Both threads access shared buffers — protected by `threading.Lock` per buffer
  and one lock for the buffer dictionary.
- No other parallelism is needed. The server does no CPU-heavy work.

## Thread Safety

| Shared Object | MQTT Thread | Flush Thread | Protection |
|---|---|---|---|
| `BufferManager._buffers` (dict) | write (create entries) | read (iterate) | `_lock_manager: Lock` |
| `StreamBuffer._pending` (list) | write (append) | read+write (pop) | `_lock_buffer: Lock` (one per buffer) |
| `DeviceRegistry._map` (dict) | write | never touches | None (single writer) |
| `MqttTransport.publish()` | calls | calls | paho handles internally |

Lock granularity: one lock for the dict, one lock per receiver buffer.
The MQTT thread and flush thread never hold both locks simultaneously
for the same buffer — enqueue and flush are separate `with` blocks.

## Directory Structure

```
lorawan-audio-server/
│
├── main.py                         Entry point, dependency wiring, startup
├── config.py                       Settings dataclass from .env
├── pyproject.toml
├── .env / .env.example
│
├── transport/
│   ├── __init__.py
│   └── mqtt_client.py              MQTT connection, subscribe, publish
│                                    Wraps paho-mqtt. Thin — no business logic.
│
├── protocol/
│   ├── __init__.py
│   ├── models.py                   Packet, Address, MsgType (frozen dataclasses)
│   ├── parser.py                   parse(bytes) → Packet (pure function)
│   ├── serializer.py               build_ack(), build_downlink() (pure functions)
│   └── crc.py                      calculate_crc8(), verify_crc8() (pure functions)
│
├── registry/
│   ├── __init__.py
│   └── device_registry.py          Address ↔ DevEUI mapping
│
├── routing/
│   ├── __init__.py
│   ├── forwarder.py                Routing decisions: ACK, forward, drop
│   └── stream_buffer.py            StreamBuffer, BufferManager (thread-safe)
│
├── handlers/
│   ├── __init__.py
│   ├── uplink.py                   Uplink event handler (orchestrator)
│   └── join.py                     Join event handler
│
└── scheduler.py                    Flush thread: periodic buffer drain + publish
```

## Module Responsibilities

### protocol/ — Pure Functions, Zero Dependencies

The protocol layer knows nothing about MQTT, threads, or buffers. It converts
between raw bytes and typed `Packet` objects. It computes and verifies CRC.

```python
# protocol/models.py
class Address(NamedTuple):
    addh: int
    addl: int

class MsgType(IntEnum):
    DATA      = 0x1
    ACK       = 0x2
    DATA_SEQ  = 0x3
    ACK_SEQ   = 0x4
    DATA_LAST = 0x5
    ACK_LAST  = 0x6
    JOIN      = 0x7

@dataclass(frozen=True)
class Packet:
    msg_type: MsgType
    sender: Address
    receiver: Address
    seq: int
    payload: bytes
    crc_valid: bool
```

```python
# protocol/parser.py
def parse(raw_bytes: bytes) -> Packet:
    """Deserialize C struct bytes into a Packet.
    Raises ValueError on invalid data."""

# protocol/serializer.py
def build_ack(packet: Packet) -> bytes:
    """Build ACK response bytes for the given packet."""

def build_downlink(packet: Packet) -> bytes:
    """Build data downlink bytes."""

# protocol/crc.py
def calculate_crc8(header_bytes: bytes, payload: bytes) -> int: ...
def verify_crc8(header_bytes: bytes, payload_with_crc: bytes) -> bool: ...
```

### registry/ — Device State

```python
class DeviceRegistry:
    def register(self, addr: Address, dev_eui: str) -> None:
        """Map a LoRa address to a ChirpStack DevEUI."""

    def lookup(self, addr: Address) -> str | None:
        """Return DevEUI for address, or None if unknown."""
```

Only written to by the MQTT thread (on first uplink from a new address).
The flush thread never touches it.

### routing/ — Thread-Safe Buffers and Forwarding Logic

```python
class StreamBuffer:
    """Thread-safe FIFO for one receiver. Protected by _lock_buffer."""

    def __init__(self):
        self._pending: list[Packet] = []
        self._lock: threading.Lock = threading.Lock()

    def enqueue(self, packet: Packet) -> None:
        with self._lock:
            self._pending.append(packet)

    def try_flush(self) -> Packet | None:
        with self._lock:
            if self._pending:
                return self._pending.pop(0)
            return None

    def has_pending(self) -> bool:
        with self._lock:
            return len(self._pending) > 0


class BufferManager:
    """Thread-safe dict of per-receiver StreamBuffers.
    Protected by _lock_manager."""

    def __init__(self):
        self._buffers: dict[str, StreamBuffer] = {}
        self._lock: threading.Lock = threading.Lock()

    def get_or_create(self, receiver_eui: str) -> StreamBuffer:
        with self._lock:
            if receiver_eui not in self._buffers:
                self._buffers[receiver_eui] = StreamBuffer()
            return self._buffers[receiver_eui]

    def get_all_active(self) -> list[tuple[str, StreamBuffer]]:
        with self._lock:
            return [(k, v) for k, v in self._buffers.items() if v.has_pending()]
```

```python
class Forwarder:
    def __init__(self, registry: DeviceRegistry, buffers: BufferManager): ...

    def on_packet_up(self, packet: Packet, sender_eui: str,
                     mqtt_publish) -> None:
        """1. Look up receiver DevEUI via registry
           2. If receiver unknown → drop
           3. ACK sender via mqtt_publish
           4. Enqueue packet in receiver's StreamBuffer"""
```

### handlers/ — Orchestrators

```python
class UplinkHandler:
    def __init__(self, forwarder: Forwarder): ...

    def handle(self, raw_json: bytes) -> None:
        """1. Parse ChirpStack JSON envelope
           2. base64 decode payload
           3. protocol.parse() → Packet
           4. Register sender address if new
           5. Forwarder.on_packet_up()"""
```

### transport/ — MQTT Wrapper

```python
class MqttTransport:
    def __init__(self, settings: Settings): ...

    def set_uplink_handler(self, handler: Callable) -> None:
        """Register the callback for uplink events."""

    def start(self) -> None:
        """Connect and start paho loop_start(). Blocks on loop_forever()."""

    def stop(self) -> None:
        """Disconnect gracefully."""

    def publish_downlink(self, dev_eui: str, payload: bytes) -> None:
        """Publish a downlink to ChirpStack MQTT topic.
        Thread-safe — paho queues internally."""
```

### scheduler.py — Flush Thread

```python
class FlushScheduler:
    def __init__(self, buffers: BufferManager, transport: MqttTransport,
                 flush_interval_ms: int = 100): ...

    def start(self) -> None:
        """Spawn daemon thread running _loop()."""

    def stop(self) -> None:
        """Signal thread to stop, join."""

    def _loop(self) -> None:
        """while not stopped:
            sleep(flush_interval)
            for (receiver_eui, buf) in buffers.get_all_active():
                pkt = buf.try_flush()
                if pkt:
                    downlink = serializer.build_downlink(pkt)
                    transport.publish_downlink(receiver_eui, downlink)
        """
```

### main.py — Dependency Wiring

```python
def main() -> None:
    settings = Settings.from_env()

    transport = MqttTransport(settings)
    registry  = DeviceRegistry()
    buffers   = BufferManager()
    forwarder = Forwarder(registry, buffers)
    uplink    = UplinkHandler(forwarder)
    scheduler = FlushScheduler(buffers, transport, settings.flush_interval_ms)

    transport.set_uplink_handler(uplink.handle)

    scheduler.start()
    transport.start()           # blocks (loop_forever)
```

## Packet Flow

### Uplink (Node A sends audio to Node B)

```
1. Node A transmits audio packet
2. Gateway receives on one of 8 channels
3. ChirpStack publishes MQTT message to application topic
4. MqttTransport.on_message fires (paho thread)
5. UplinkHandler.handle():
   a. Parse JSON envelope
   b. base64 decode → raw bytes
   c. protocol.parse(raw_bytes) → Packet object
   d. Registry: register sender address if new
   e. Registry: resolve receiver DevEUI
   f. Forwarder.on_packet_up():
      - Publish ACK to sender (reduces airtime, no wait for Node B)
      - Enqueue packet in Node B's StreamBuffer
```

### Downlink (Server forwards to Node B)

```
1. Flush thread wakes up (every FLUSH_INTERVAL ms)
2. BufferManager.get_all_active() → list of receivers with pending packets
3. For Node B: StreamBuffer.try_flush() → oldest Packet
4. protocol.serializer.build_downlink(pkt) → raw bytes
5. MqttTransport.publish_downlink("NodeB_eui", downlink_bytes)
6. ChirpStack receives MQTT message
7. ChirpStack queues downlink for Node B
8. ChirpStack commands gateway to transmit on next available slot
9. Node B receives audio packet (radio always open — Class C)
```

### Multiple Simultaneous Conversations (A→B and C→D)

```
Uplinks arrive from A and C (different channels, simultaneous)
  → Both are parsed, ACKed, and enqueued for B and D respectively

Flush thread iterates:
  tick 1: B has packets → send one to B
  tick 2: D has packets → send one to D
  tick 3: B has packets → send one to B
  ...

Downlinks are serialized on the single downlink radio.
ChirpStack handles channel selection and scheduling.
```

## Thread Safety Sequence Diagram

```
MQTT Thread                     Locks                      Flush Thread
───────────                     ─────                      ────────────

on_message(A→B pkt1)
  │
  ├─ get_or_create("B")
  │    lock_manager ► ACQUIRE
  │    found in dict
  │    lock_manager ► RELEASE
  │
  ├─ streamB.enqueue(pkt1)
  │    lock_B ► ACQUIRE
  │    _pending.append(pkt1)
  │    lock_B ► RELEASE
  │
  ├─ publish(ACK to A)
  │   (paho internal, thread-safe)
  │                                                   sleep(100ms)...
  │                                                   wake up
  │                                                   │
  │                                                   ├─ get_all_active()
  │                                                   │    lock_manager ► ACQUIRE
  │                                                   │    B has pending
  │                                                   │    lock_manager ► RELEASE
  │                                                   │
  │                                                   ├─ streamB.try_flush()
  │                                                   │    lock_B ► ACQUIRE
  │                                                   │    pop(0) → pkt1
  │                                                   │    lock_B ► RELEASE
  │                                                   │
  │                                                   ├─ publish(downlink to B)
  │                                                   │   (paho internal)
```

## Dependency Rule

```
main.py          →  everything (wiring only)
handlers/*       →  protocol, registry, routing
routing/*        →  protocol, registry
registry/*       →  nothing
protocol/*       →  nothing
transport/*      →  nothing (receives handler callback via set_uplink_handler)
scheduler.py     →  routing, protocol, transport
```

Direction: dependencies point inward toward `protocol` and `registry` at the core.
Outer modules (`handlers`, `transport`, `scheduler`) depend on inner modules,
never the reverse. `protocol/*` is the innermost layer with zero dependencies.

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| Producer-Consumer | MQTT thread → buffers → flush thread | Decouple receive rate from send rate |
| Dependency Injection | main.py wires all components | Testable, no hidden globals |
| Pure Functions | protocol/* (parser, serializer, crc) | Zero side effects, trivially testable |
| Facade | MqttTransport wraps paho-mqtt | Single interface, swap internals freely |
| Strategy | Forwarder decides ACK/forward/drop | Routing logic isolated from protocol |
| Thread-Per-Task (minimal) | 2 threads total | Right parallelism for this workload |

## Tuning Parameters

| Parameter | Config Key | Default | Effect |
|---|---|---|---|
| Flush interval | `FLUSH_INTERVAL_MS` | 100 | How often flush thread checks buffers. Lower = less latency, more CPU. |
| MQTT broker | `MQTT_BROKER_HOST` | localhost | ChirpStack MQTT address |
| MQTT port | `MQTT_BROKER_PORT` | 1883 | ChirpStack MQTT port |
