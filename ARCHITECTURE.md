# Architecture

This document describes the software architecture of the lorawan-audio-server.

## Overview

The server acts as a smart relay in a LoRaWAN walkie-talkie network. It receives
audio packets from speaking nodes, acknowledges them on behalf of the receiver
(to reduce airtime), buffers them, and forwards them to the listening node(s).

The server produces **two separate downlinks** for each received uplink:

1. **ACK to sender** — immediate, sent in the same handler call
2. **Data to receiver** — deferred, sent by the flush thread from a buffer

```
Node A ──uplink──► Gateway (WM1302) ──MQTT──► ChirpStack ──MQTT──► This Server
Node A ◄──ACK──── Gateway ◄── ChirpStack ◄── This Server (immediate)
Node B ◄──data─── Gateway ◄── ChirpStack ◄── This Server (deferred via flush thread)
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
┌─────────────────────────────────────┐    ┌─────────────────────────────┐
│   MQTT THREAD (paho background)     │    │   FLUSH THREAD              │
│                                     │    │                             │
│   on_message callback:              │    │   Every FLUSH_INTERVAL ms:  │
│     1. Parse JSON envelope          │    │     For each receiver with  │
│     2. Deserialize bytes → Packet   │    │     pending packets:        │
│     3. Forwarder: register, lookup, │    │       Pop one packet        │
│        build ACK, enqueue for recv  │    │       Serialize to bytes    │
│     4. Publish ACK immediately      │    │       Publish to ChirpStack │
│                                     │    │                             │
│   Produces: ACK (immediate)         │    │   Produces: data (deferred) │
│   Produces: buffered packets        │    │   Consumes: buffered packets│
└──────────────┬──────────────────────┘    └──────────────┬──────────────┘
               │                                          │
               ▼                                          ▼
        ┌─────────────────────────────────────────────────────┐
        │              SHARED STATE                            │
        │                                                     │
        │  BufferManager (dict of StreamBuffers)              │
        │    └─ per-receiver: StreamBuffer                    │
        │         └─ _pending: list[Packet]                   │
        │                                                     │
        │  DeviceRegistry (Address → DevEUI map)              │
        │    └─ written by MQTT thread only                   │
        └─────────────────────────────────────────────────────┘
```

### Why Two Threads

- The MQTT thread (paho `loop_forever`) handles network I/O and dispatches
  uplink messages to handlers. It produces ACKs immediately and enqueues
  data packets into per-receiver buffers.
- The flush thread consumes from those buffers and publishes data downlinks
  to ChirpStack, which handles radio scheduling on the single downlink channel.
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

## Two Downlink Paths

Each uplink produces two independent downlinks that take different paths:

### ACK Path (immediate)

```
Forwarder returns PublishRequest → Handler publishes immediately
```

The sender (Node A) is waiting for confirmation. The ACK must be fast — no
buffering, no waiting for the flush thread. The handler receives the
`PublishRequest` from the forwarder and calls `transport.publish_downlink()`
in the same call stack.

### Data Path (deferred)

```
Forwarder enqueues packet in receiver's buffer → Flush thread publishes later
```

The receiver (Node B) has its radio always on (Class C). A 100ms delay
from the flush interval is acceptable for audio. The flush thread periodically
drains buffers and publishes to ChirpStack.

```
                    Uplink from A arrives
                           │
                           ▼
                  ┌─── Forwarder ──────────────────────────────┐
                  │                                            │
                  │  1. Register A → dev_eui in registry       │
                  │  2. Lookup B from registry                  │
                  │  3. Build ACK for A                        │
                  │  4. Enqueue packet for B in buffer         │
                  │  5. Return PublishRequest(A, ack_payload)  │
                  │                                            │
                  └──────────┬───────────────┬─────────────────┘
                             │               │
                             ▼               ▼
                     ACK to Node A      Packet for B
                     (immediate)        (in buffer)
                                              │
                                              ▼
                                     Flush thread picks up
                                     (every FLUSH_INTERVAL ms)
                                              │
                                              ▼
                                     Data to Node B
                                     (deferred)
```

## Directory Structure

```
lorawan-audio-server/
│
├── main.py                             Entry point, dependency wiring, startup
├── config.py                           Settings dataclass from .env
├── exceptions.py                       Custom exception hierarchy
├── pyproject.toml
├── .env / .env.example
│
├── transport/
│   ├── __init__.py
│   ├── mqtt_client.py                  MQTT connection, subscribe, publish
│   │                                    Wraps paho-mqtt. Thin — no business logic.
│   └── chirpstack_endpoints.py         ChirpStack MQTT topic construction
│   └── chirpstack_event_types/         Pydantic models for ChirpStack JSON
│       └── uplink.py
│
├── protocol/
│   ├── __init__.py
│   ├── models.py                       Packet, Address, MsgType (frozen dataclasses)
│   ├── parser.py                       parse(bytes) → Packet (pure function)
│   ├── serializer.py                   build_ack(), build_downlink() (pure functions)
│   └── crc.py                          calculate_crc8(), verify_crc8() (pure functions)
│
├── registry/
│   ├── __init__.py
│   └── device_registry.py              Address → DevEUI mapping
│
├── routing/
│   ├── __init__.py
│   ├── models.py                       PublishRequest (return type from forwarder)
│   ├── forwarder.py                    Routing decisions: register, lookup, ACK, enqueue
│   └── stream_buffer.py                StreamBuffer, BufferManager (thread-safe)
│
├── handlers/
│   ├── __init__.py
│   ├── uplink.py                       Uplink event handler (orchestrator)
│   └── join.py                         Join event handler
│
└── scheduler.py                        Flush thread: periodic buffer drain + publish
```

## Module Responsibilities

### protocol/ — Pure Functions, Zero Dependencies

The protocol layer knows nothing about MQTT, threads, buffers, or ChirpStack.
It converts between raw bytes and typed `Packet` objects. It computes and verifies CRC.

```python
# protocol/models.py
@dataclass(frozen=True)
class Address:
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
def parse(decoded_payload: bytes) -> Packet:
    """Deserialize C struct bytes into a Packet.
    Raises ProtocolError on invalid data."""

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
    def __init__(self):
        self._map: dict[Address, str] = {}
        self._lock: threading.Lock = threading.Lock()

    def register(self, addr: Address, dev_eui: str) -> None:
        """Map a LoRa address to a ChirpStack DevEUI.
        Thread-safe. Only called by MQTT thread."""

    def lookup(self, addr: Address) -> str | None:
        """Return DevEUI for address, or None if unknown.
        Thread-safe. Only called by MQTT thread."""
```

Only written to by the MQTT thread (on first uplink from a new address).
The flush thread never touches it.

### routing/ — Thread-Safe Buffers and Forwarding Logic

```python
# routing/models.py
@dataclass(frozen=True)
class PublishRequest:
    """What the handler needs to publish. Returned by Forwarder."""
    target_eui: str
    payload: bytes
```

```python
# routing/stream_buffer.py
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
# routing/forwarder.py
class Forwarder:
    """Routing decisions. No transport dependency.
    Returns PublishRequest for the handler to publish."""

    def __init__(self, registry: DeviceRegistry, buffers: BufferManager):
        self.registry = registry
        self.buffers = buffers

    def on_packet_up(
        self, packet: Packet, sender_eui: str, f_port: int, app_id: str
    ) -> PublishRequest | None:
        """
        1. Register sender address → dev_eui in registry
        2. Lookup receiver dev_eui from registry
        3. If receiver unknown → return None (drop)
        4. Build ACK bytes via serializer.build_ack()
        5. Enqueue packet in receiver's StreamBuffer
        6. Return PublishRequest(target=sender_eui, payload=ack_json)
        """
```

Key design: the forwarder **never publishes to MQTT**. It returns a
`PublishRequest` and the handler publishes it. This keeps the routing
layer free of transport dependencies.

### handlers/ — Orchestrators (bridge between transport and routing)

```python
# handlers/uplink.py
class UplinkHandler:
    def __init__(self, forwarder: Forwarder, publish_downlink: Callable):
        self.forwarder = forwarder
        self.publish_downlink = publish_downlink

    def handle(self, raw_json: bytes) -> None:
        """
        1. Parse ChirpStack JSON envelope → UplinkEvent (pydantic)
        2. base64 decode payload → raw bytes
        3. protocol.parse(raw_bytes) → Packet
        4. Extract primitives from UplinkEvent:
             sender_eui = event.device_info.dev_eui
             f_port = event.f_port
             app_id = event.device_info.application_id
        5. Forwarder.on_packet_up(packet, sender_eui, f_port, app_id)
             → returns PublishRequest (ACK) or None
        6. If PublishRequest returned:
             self.publish_downlink(request.target_eui, request.payload)
        """
```

The handler is the **only module that knows about both** the ChirpStack
JSON model (`UplinkEvent`) and the transport (`publish_downlink`). It
extracts primitive values from the ChirpStack model and passes only those
to the forwarder. This preserves the dependency rule.

### transport/ — MQTT Wrapper

```python
# transport/mqtt_client.py
class MqttTransport:
    def __init__(self, settings: Settings): ...

    def set_uplink_handler(self, handler: Callable) -> None:
        """Register the callback for uplink events."""

    def set_join_handler(self, handler: Callable) -> None:
        """Register the callback for join events."""

    def start(self) -> None:
        """Connect to broker. Raises MQTTConnectionError on failure."""

    def stop(self) -> None:
        """Disconnect gracefully."""

    def loop_forever(self) -> None:
        """Block and process MQTT events. Handles auto-reconnect."""

    def publish_downlink(self, dev_eui: str, payload: bytes, qos: int = 1) -> None:
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
            wait(flush_interval)
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
    settings = load_env_variables()

    transport = MqttTransport(settings)
    registry  = DeviceRegistry()
    buffers   = BufferManager()
    forwarder = Forwarder(registry, buffers)
    uplink    = UplinkHandler(forwarder, transport.publish_downlink)
    join      = JoinHandler(forwarder)
    scheduler = FlushScheduler(buffers, transport, settings.flush_interval_ms)

    transport.set_uplink_handler(uplink.handle)
    transport.set_join_handler(join.handle)

    scheduler.start()
    transport.start()           # raises MQTTConnectionError on failure
    transport.loop_forever()    # blocks
```

## Packet Flow — Detailed Module Sequence

Every function call for a single incoming uplink (Node A sends audio to Node B):

```
ChirpStack MQTT Broker
        │
        │  MQTT publish to topic:
        │  "application/{app_id}/device/{sender_eui}/event/up"
        │
        ▼
═══════════════════════════════════════════════════════════════════
  THREAD 1: MQTT (paho background)
═══════════════════════════════════════════════════════════════════
        │
        │  paho internal: parse MQTT packet, match topic
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  transport/mqtt_client.py                                    │
│                                                              │
│  MqttTransport.on_message(client, userdata, msg)             │
│    │                                                         │
│    │  event_type = msg.topic.rsplit('/', 1)[1]               │
│    │  if event_type == "up":                                 │
│    │    self.uplink_handler(msg.payload)                     │
│    │  elif event_type == "join":                             │
│    │    self.join_handler(msg.payload)                       │
│    │                                                         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  handlers/uplink.py                                          │
│                                                              │
│  UplinkHandler.handle(raw_json: bytes)                       │
│    │                                                         │
│    │  1. UplinkEvent.model_validate_json(raw_json)           │
│    │     → ChirpStack JSON envelope parsed                   │
│    │                                                         │
│    │  2. base64.b64decode(event.data) → decoded_payload      │
│    │                                                         │
│    │  3. parser.parse(decoded_payload) → Packet              │
│    │                                                         │
│    │  4. Extract primitives from UplinkEvent:                │
│    │       sender_eui = event.device_info.dev_eui            │
│    │       f_port     = event.f_port                         │
│    │       app_id     = event.device_info.application_id     │
│    │                                                         │
│    ▼                                                         │
│  self.forwarder.on_packet_up(packet, sender_eui,             │
│                              f_port, app_id)                 │
│    │                                                         │
│    │  ← returns PublishRequest(target_eui, payload) or None  │
│    │                                                         │
│    │  5. if result:                                          │
│    │       self.publish_downlink(result.target_eui,          │
│    │                             result.payload)             │
│    │                                                         │
│    ▼                                                         │
│  ┌─────────────────────────────────────────┐                 │
│  │  MqttTransport.publish_downlink()       │                 │
│  │    → MQTT publish ACK to Node A         │                 │
│  └─────────────────────────────────────────┘                 │
│                                                              │
│  ✓ ACK sent to Node A immediately                            │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │  (Meanwhile, inside the forwarder
                           │   call above, this also happened:)
                           │
┌──────────────────────────┼───────────────────────────────────┐
│  routing/forwarder.py    │                                   │
│                          │                                   │
│  Forwarder.on_packet_up(packet, sender_eui, f_port, app_id) │
│    │                                                         │
│    │  1. self.registry.register(packet.sender, sender_eui)  │
│    │                                                         │
│    │  2. receiver_eui = self.registry.lookup(packet.receiver)│
│    │     if not receiver_eui: return None                    │
│    │                                                         │
│    │  3. ack_bytes = serializer.build_ack(packet)            │
│    │     ack_b64 = base64.b64encode(ack_bytes).decode()     │
│    │     ack_payload = json.dumps({                          │
│    │         "devEui": sender_eui,                            │
│    │         "confirmed": False,                              │
│    │         "fPort": f_port,                                 │
│    │         "data": ack_b64                                  │
│    │     })                                                  │
│    │                                                         │
│    │  4. buf = self.buffers.get_or_create(receiver_eui)      │
│    │     ┌─────────────────────────────────────────┐         │
│    │     │  BufferManager.get_or_create(eui)       │         │
│    │     │    lock_manager ► ACQUIRE               │         │
│    │     │    if eui not in _buffers:              │         │
│    │     │        _buffers[eui] = StreamBuffer()   │         │
│    │     │    lock_manager ► RELEASE               │         │
│    │     └─────────────────────────────────────────┘         │
│    │                                                         │
│    │  5. buf.enqueue(packet)                                 │
│    │     ┌─────────────────────────────────────────┐         │
│    │     │  StreamBuffer.enqueue(packet)           │         │
│    │     │    lock_buffer ► ACQUIRE                │         │
│    │     │    _pending.append(packet)              │         │
│    │     │    lock_buffer ► RELEASE                │         │
│    │     └─────────────────────────────────────────┘         │
│    │                                                         │
│    │  6. return PublishRequest(target_eui=sender_eui,        │
│    │                           payload=ack_payload)          │
│    │                                                         │
│  ✓ Packet enqueued for Node B                                │
│  ✓ PublishRequest returned for ACK                           │
└──────────────────────────────────────────────────────────────┘
                           │
                           │  (back to paho thread — continues
                           │   listening for next message)
                           │
                           │  (Packet for Node B sits in buffer)
                           │
═══════════════════════════════════════════════════════════════════
  THREAD 2: FLUSH (periodic, runs independently)
═══════════════════════════════════════════════════════════════════
        │
        │  (runs every FLUSH_INTERVAL ms)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  scheduler.py                                                │
│                                                              │
│  FlushScheduler._loop()                                      │
│    │                                                         │
│    │  while not self._stop_event.is_set():                   │
│    │      self._stop_event.wait(self.flush_interval / 1000)  │
│    │                                                         │
│    │      active = self.buffers.get_all_active()             │
│    │       │                                                 │
│    │       ▼                                                 │
│    │  ┌─────────────────────────────────────────┐            │
│    │  │  BufferManager.get_all_active()         │            │
│    │  │    lock_manager ► ACQUIRE               │            │
│    │  │    return [(k,v) for k,v in _buffers    │            │
│    │  │            if v.has_pending()]           │            │
│    │  │    lock_manager ► RELEASE               │            │
│    │  └─────────────────────────────────────────┘            │
│    │                                                         │
│    │      for receiver_eui, buf in active:                   │
│    │                                                         │
│    │        pkt = buf.try_flush()                            │
│    │       │                                                 │
│    │       ▼                                                 │
│    │  ┌─────────────────────────────────────────┐            │
│    │  │  StreamBuffer.try_flush()               │            │
│    │  │    lock_buffer ► ACQUIRE                │            │
│    │  │    if _pending:                         │            │
│    │  │        return _pending.pop(0)           │            │
│    │  │    lock_buffer ► RELEASE                │            │
│    │  └─────────────────────────────────────────┘            │
│    │       │                                                 │
│    │       ▼  (if pkt is not None)                           │
│    │                                                         │
│    │  downlink_bytes = serializer.build_downlink(pkt)        │
│    │                                                         │
│    │  self.transport.publish_downlink(receiver_eui,          │
│    │                                  downlink_bytes)         │
│    │       │                                                 │
│    │       ▼                                                 │
│    │  ┌─────────────────────────────────────────┐            │
│    │  │  MqttTransport.publish_downlink()       │            │
│    │  │    → MQTT publish data to Node B        │            │
│    │  └─────────────────────────────────────────┘            │
│    │                                                         │
│    │  ✓ Data sent to Node B (deferred, via flush thread)    │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
   ChirpStack MQTT Broker
        │
        ▼
   ChirpStack → Gateway → Node B (radio, always on — Class C)
```

### Multiple Simultaneous Conversations (A→B and C→D)

```
Uplinks arrive from A and C (different channels, simultaneous)
  → Both are parsed, ACKed immediately, and enqueued for B and D

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
  ├─ forwarder.on_packet_up()
  │   ├─ registry.register(A)
  │   │    lock_registry ► ACQUIRE
  │   │    _map[A] = dev_eui
  │   │    lock_registry ► RELEASE
  │   │
  │   ├─ registry.lookup(B)
  │   │    lock_registry ► ACQUIRE
  │   │    return dev_eui
  │   │    lock_registry ► RELEASE
  │   │
  │   ├─ buffers.get_or_create("B")
  │   │    lock_manager ► ACQUIRE
  │   │    found in dict
  │   │    lock_manager ► RELEASE
  │   │
  │   ├─ buf.enqueue(pkt1)
  │   │    lock_B ► ACQUIRE
  │   │    _pending.append(pkt1)
  │   │    lock_B ► RELEASE
  │   │
  │   └─ return PublishRequest(A, ack_payload)
  │
  ├─ publish_downlink(A, ack_payload)
  │   (paho internal, thread-safe)
  │
  │  ✓ ACK sent to Node A
  │                                                   sleep(100ms)...
  │                                                   wake up
  │                                                   │
  │                                                   ├─ get_all_active()
  │                                                   │    lock_manager ► ACQUIRE
  │                                                   │    B has pending
  │                                                   │    lock_manager ► RELEASE
  │                                                   │
  │                                                   ├─ buf.try_flush()
  │                                                   │    lock_B ► ACQUIRE
  │                                                   │    pop(0) → pkt1
  │                                                   │    lock_B ► RELEASE
  │                                                   │
  │                                                   ├─ publish_downlink(B, data)
  │                                                   │   (paho internal)
  │                                                   │
  │                                                   │  ✓ Data sent to Node B
```

## Dependency Rule

```
main.py              →  everything (wiring only)
handlers/*           →  protocol, routing, transport (the bridge layer)
routing/*            →  protocol, registry (NO transport)
registry/*           →  protocol (Address type only)
protocol/*           →  nothing
transport/*          →  nothing (receives handler callbacks via set_*_handler)
scheduler.py         →  routing, protocol, transport
```

Direction: dependencies point inward toward `protocol` at the core.
The `handlers` layer is the **only** layer that touches both routing and
transport — it bridges the two worlds. `routing/*` never imports from
`transport/*`. `protocol/*` has zero dependencies.

```
         protocol (core, zero deps)
              ▲
              │
         registry (depends on protocol for Address)
              ▲
              │
         routing (depends on protocol + registry)
              ▲
              │
         handlers (depends on routing + transport) ← the bridge
              ▲               ▲
              │               │
         transport       scheduler
```

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| Producer-Consumer | MQTT thread → buffers → flush thread | Decouple receive rate from send rate |
| Dependency Injection | main.py wires all components | Testable, no hidden globals |
| Pure Functions | protocol/* (parser, serializer, crc) | Zero side effects, trivially testable |
| Facade | MqttTransport wraps paho-mqtt | Single interface, swap internals freely |
| Command (return) | Forwarder returns PublishRequest | Routing decisions decoupled from transport actions |
| Bridge | handlers/ layer | Only module that touches both routing and transport |
| Thread-Per-Task (minimal) | 2 threads total | Right parallelism for this workload |

## Tuning Parameters

| Parameter | Config Key | Default | Effect |
|---|---|---|---|
| Flush interval | `FLUSH_INTERVAL_MS` | 100 | How often flush thread checks buffers. Lower = less latency, more CPU. |
| MQTT broker | `MQTT_BROKER_HOST` | localhost | ChirpStack MQTT address |
| MQTT port | `MQTT_BROKER_PORT` | 1883 | ChirpStack MQTT port |
