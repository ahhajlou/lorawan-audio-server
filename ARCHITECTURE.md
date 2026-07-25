# Architecture

This document describes the software architecture of the lorawan-audio-server.

## Overview

The server acts as a smart relay in a LoRaWAN walkie-talkie network. It receives
audio packets from speaking nodes, acknowledges them on behalf of the receiver
(to reduce airtime), and forwards them to the listening node(s).

Every downlink the server produces — the ACK to the sender **and** the data to
the receiver — shares one physical resource: **the gateway's single TX chain.**
A WM1302 (or any SX1302-based gateway) can only have one packet on air at a
time, regardless of which device it's addressed to or which logical "channel"
ChirpStack picked.

```
Node A ──uplink──► Gateway (WM1302) ──MQTT──► ChirpStack ──MQTT──► This Server
Node A ◄──ACK──┐
Node B ◄──data─┤── Gateway ◄── ChirpStack ◄── This Server
               │
               └── both downlinks pass through ONE dispatch queue,
                   serialized against the gateway's TX chain
```

## Hardware Constraints

| Component | Detail |
|---|---|
| End nodes | RAK3112 (ESP32 + SX1262) |
| Gateway | WM1302 with Raspberry Pi 5 |
| Network server | ChirpStack |
| Uplink channels | 8 (multi-channel receiver) |
| Downlink channels | 1 (single radio, one packet on air at a time) |
| Frequency plan | EU868 (duty cycle disabled) |
| LoRaWAN class | **C** (always-on receiver for low latency) |

## Thread Model

Three logical workers. No thread pools.

```
┌─────────────────────────────────┐   ┌───────────────────────────────────┐
│   MQTT THREAD (paho background) │   │   DISPATCHER (one per gateway_id) │
│                                  │   │                                    │
│   on_message callback:          │   │   loop:                            │
│     1. Parse JSON envelope      │   │     item = queue.pop_next()        │
│     2. Deserialize → Packet     │   │     publish(item)                  │
│     3. Forwarder: register,     │   │     wait_for(txack(gateway_id),    │
│        lookup, build ACK,       │   │               timeout=5s)          │
│        build data payload       │   │     (repeat)                       │
│     4. queue.enqueue(ACK item)  │   │                                    │
│     5. queue.enqueue(DATA item) │   │   Consumes: GatewayDispatchQueue   │
│                                  │   │   Produces: MQTT publish calls     │
│   Produces: queue items         │   └───────────────┬────────────────────┘
└───────────────┬──────────────────┘                   │
                │                                       │
                ▼                                       ▼
        ┌───────────────────────────────────────────────────────┐
        │                   SHARED STATE                        │
        │                                                       │
        │  GatewayDispatchQueue (dict: gateway_id → FIFO deque)  │
        │    └─ per-gateway: pending items + dispatcher thread   │
        │                                                       │
        │  DeviceRegistry (Address → DevEUI, DevEUI → gateway_id)│
        │    └─ written by MQTT thread only                     │
        └───────────────────────────────────────────────────────┘
                ▲
                │ txack events
                │
┌───────────────┴───────────────────┐
│   TXACK LISTENER (in MQTT thread) │
│   on txack message:               │
│     resolve gateway_id,           │
│     signal dispatcher             │
└────────────────────────────────────┘
```

### Why Three Workers Instead of Two

- The MQTT thread parses uplinks and produces queue items — it **never
  publishes a downlink directly anymore**. This removes the unsynchronized
  "immediate ACK" bypass.
- The flush-on-timer thread is gone. It's replaced by a **dispatcher per
  gateway** that is event-driven: it only advances after seeing `txack`
  proof that the previous packet cleared the antenna, or a timeout.
- The txack listener is part of the MQTT thread (same `on_message` callback),
  which routes the event to the correct dispatcher via `DispatcherManager`.

## Thread Safety

| Shared Object | MQTT Thread | Dispatcher | Protection |
|---|---|---|---|
| `GatewayDispatchQueue._queues` (dict) | write (create/append) | read (get queue) | `_lock: Lock` |
| Per-gateway `GatewayQueue._pending` (deque) | append | pop | `Lock` + `Condition` |
| `DeviceRegistry._eui_to_gateway` (dict) | write | read (gateway_id lookup) | `Lock` |
| `DispatcherManager._dispatchers` (dict) | write (ensure_dispatcher) | none | `Lock` |
| `MqttTransport.publish()` | calls | calls | paho handles internally |

Lock granularity: one lock for the outer dict of gateway queues, one lock (and
one condition variable) per gateway. The dispatcher for gateway G only ever
blocks on G's own condition — dispatchers for other gateways are unaffected.

## Two Downlink Kinds, One Queue

Previously "ACK path" and "data path" were architecturally separate. Now they
are the same kind of object — a `DownlinkItem` — differing only in payload and
target device. Both are produced by the same `Forwarder.on_packet_up()` call
and pushed, in order, to the same per-gateway queue.

```python
# routing/models.py
@dataclass(frozen=True)
class DownlinkItem:
    target_eui: str
    gateway_id: str
    payload: bytes
    kind: Literal["ack", "data"]   # informational only — ordering is FIFO
    f_port: int
```

The ACK is enqueued **ahead of** the data item for the same uplink — the
forwarder pushes ACK then DATA in that order, and since the queue is FIFO,
ACK dispatches first.

## Correlating txack to the In-Flight Item

Because the dispatcher enforces **strictly one downlink in flight per
gateway**, correlation is simple: whichever `txack` event arrives next for that
`gateway_id` belongs to the item currently in flight. A timeout (5s default)
guards against a lost or delayed `txack` wedging the queue forever.

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
│   ├── mqtt_client.py                  MQTT connection, subscribe, publish.
│   │                                    Subscribes to uplink, join, and txack topics.
│   ├── chirpstack_endpoints.py         ChirpStack MQTT topic construction
│   ├── helper.py                       MQTT error handling decorator
│   └── chirpstack_event_types/
│       ├── uplink.py                   Pydantic model for UplinkEvent
│       └── txack.py                    Pydantic model for TxAckEvent
│
├── protocol/
│   ├── __init__.py
│   ├── models.py                       Packet, Address, MsgType (frozen dataclasses)
│   ├── parser.py                       parse(bytes) → Packet (pure function)
│   ├── serializer.py                   build_ack(), build_downlink() (pure functions)
│   ├── crc.py                          calculate_crc8(), verify_crc8() (pure functions)
│   └── c_lora_packet.py               CFFI struct definitions
│
├── registry/
│   ├── __init__.py
│   └── device_registry.py              Address → DevEUI, DevEUI → gateway_id
│
├── routing/
│   ├── __init__.py
│   ├── models.py                       DownlinkItem dataclass
│   ├── forwarder.py                    Builds ACK + data DownlinkItems, in order
│   └── gateway_queue.py               GatewayQueue (FIFO per gateway) + GatewayDispatchQueue
│
├── dispatch/
│   ├── __init__.py
│   └── dispatcher.py                   Dispatcher (one per gateway_id) + DispatcherManager
│
├── handlers/
│   ├── __init__.py
│   ├── uplink.py                       Uplink event handler
│   ├── txack.py                        TxAck event handler
│   └── join.py                         Join event handler
│
├── tests/
│   └── ...
│
└── CHANGELOG.md
```

## Module Responsibilities

### protocol/ — Pure Functions, Zero Dependencies

Unchanged from v1. Converts between raw bytes and typed `Packet` objects.
Computes and verifies CRC. No side effects.

### registry/ — Device State (extended)

```python
class DeviceRegistry:
    def __init__(self, db_url: str = "sqlite:///database.sql"):
        ...

    def register(self, addr: Address, dev_eui: str, gateway_id: str) -> None:
        """Map LoRa address → DevEUI, and DevEUI → gateway_id.
        gateway_id is taken from rxInfo[0].gatewayId."""

    def lookup_eui(self, addr: Address) -> str | None: ...

    def lookup_gateway(self, dev_eui: str) -> str | None:
        """Which gateway_id to target when sending this device a downlink."""
```

### routing/ — Queue and Forwarding Logic

```python
# routing/models.py
@dataclass(frozen=True)
class DownlinkItem:
    target_eui: str
    gateway_id: str
    payload: bytes
    kind: Literal["ack", "data"]
    f_port: int
```

```python
# routing/gateway_queue.py
class GatewayQueue:
    """Thread-safe FIFO for one gateway_id."""

    def enqueue(self, item: DownlinkItem) -> None: ...
    def pop_next(self, timeout=None) -> DownlinkItem | None: ...

class GatewayDispatchQueue:
    """Thread-safe dict of per-gateway GatewayQueues."""
    def get_or_create(self, gateway_id: str) -> GatewayQueue: ...
```

```python
# routing/forwarder.py
class Forwarder:
    def __init__(self, registry: DeviceRegistry): ...

    def on_packet_up(
        self, packet: Packet, sender_eui: str, gateway_id: str, f_port: int
    ) -> list[DownlinkItem]:
        """
        1. Register sender address → dev_eui → gateway_id
        2. Lookup receiver dev_eui + gateway_id
        3. If receiver unknown → return [] (drop)
        4. Build ACK bytes via serializer.build_ack()
        5. Build data bytes via serializer.build_downlink()
        6. Return [DownlinkItem(ack), DownlinkItem(data)]
           — order matters: ACK first, so it dispatches first.
        """
```

### dispatch/ — Dispatcher (replaces scheduler.py)

```python
class Dispatcher:
    """One instance per gateway_id. Runs in its own thread."""

    def __init__(self, gateway_id, queue, publish_downlink, txack_timeout=5.0): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def notify_txack(self) -> None: ...

    def _loop(self) -> None:
        """while not stopped:
            item = queue.pop_next(timeout=1.0)
            if item: publish → wait txack/timeout → repeat
        """

class DispatcherManager:
    """Manages one Dispatcher per gateway_id. Thread-safe."""
    def ensure_dispatcher(self, gateway_id: str) -> None: ...
    def notify_txack(self, gateway_id: str) -> None: ...
    def stop_all(self) -> None: ...
```

### handlers/ — Event Handlers

```python
class UplinkHandler:
    def __init__(self, forwarder, dispatch_queue, dispatcher_manager): ...
    def handle(self, raw_json: bytes) -> None:
        """
        1. Parse UplinkEvent
        2. Extract gateway_id from strongest-RSSI rxInfo entry
        3. Forwarder builds [ACK, DATA] items
        4. Enqueue both to the gateway's queue
        5. Ensure dispatcher exists for this gateway
        """

class TxAckHandler:
    def __init__(self, dispatcher_manager): ...
    def handle(self, raw_json: bytes) -> None:
        """
        1. Parse TxAckEvent → extract gatewayId
        2. dispatcher_manager.notify_txack(gateway_id)
        """
```

### transport/ — MQTT Wrapper

```python
class MqttTransport:
    def set_uplink_handler(self, handler: Callable) -> None: ...
    def set_join_handler(self, handler: Callable) -> None: ...
    def set_txack_handler(self, handler: Callable) -> None: ...

    def on_connect(self, ...):
        """Subscribes to uplink, join, and txack wildcard topics."""

    def publish_downlink(self, dev_eui, payload, qos=1) -> None: ...
```

## Dependency Rule

```
main.py              →  everything (wiring only)
handlers/*           →  protocol, routing, dispatch, transport (the bridge layer)
routing/*            →  protocol, registry (NO transport)
dispatch/*           →  routing (GatewayQueue), transport (to publish)
registry/*           →  protocol (Address type only)
protocol/*           →  nothing
transport/*          →  nothing (receives handler callbacks via set_*_handler)
```

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
         handlers (depends on routing + dispatch + transport) ← the bridge
              ▲               ▲
              │               │
         transport        dispatch
```

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| Producer-Consumer | MQTT thread → per-gateway queue → Dispatcher | Decouple receive rate from send rate, per gateway |
| Single-Flight Serialization | Dispatcher + txack wait | Enforces "one packet on air at a time" per gateway |
| Dependency Injection | main.py wires all components | Testable, no hidden globals |
| Pure Functions | protocol/* (parser, serializer, crc) | Zero side effects, trivially testable |
| Facade | MqttTransport wraps paho-mqtt | Single interface, swap internals freely |
| Command (return) | Forwarder returns list[DownlinkItem] | Routing decisions decoupled from transport actions |
| Bridge | handlers/ layer | Only module that touches both routing/dispatch and transport |
| Thread-Per-Gateway | one Dispatcher per gateway_id | Scales to multiple gateways without redesign |

## Tuning Parameters

| Parameter | Config Key | Default | Effect |
|---|---|---|---|
| txack wait timeout | `TXACK_TIMEOUT_S` | 5.0 | Max seconds dispatcher waits for proof of transmission before advancing |
| MQTT broker | `MQTT_BROKER_HOST` | localhost | ChirpStack MQTT address |
| MQTT port | `MQTT_BROKER_PORT` | 1883 | ChirpStack MQTT port |
