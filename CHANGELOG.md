# Changelog

## v2.0 — Single dispatch queue per gateway, gated on txack

The previous version had two independent downlink paths: ACK sent immediately
from the handler, and data sent by a periodic flush thread from per-receiver
buffers. When two conversations were active simultaneously, both paths could
fire downlinks to the same gateway within milliseconds, causing the
concentratord's JIT queue to reject one as `COLLISION_PACKET`.

### What changed

**New dispatch model.** Both ACK and data downlinks now flow through a single
FIFO queue per `gateway_id`. A dispatcher thread per gateway pops items one at
a time, publishes to ChirpStack, and waits for the `txack` event (or a 5s
timeout) before advancing. No more unsynchronized bypass path.

**txack subscription.** The server now subscribes to the
`application/+/device/+/event/txack` MQTT topic. A `TxAckHandler` resolves
the `gatewayId` from the event and signals the corresponding dispatcher to
proceed.

**DeviceRegistry extended.** `register()` now also stores `dev_eui → gateway_id`
(learned from `rxInfo[0].gatewayId` on each uplink). This lets the dispatcher
route downlinks to the correct gateway when multiple gateways exist.

**Forwarder simplified.** Returns a `list[DownlinkItem]` (ACK + data) instead
of a single `PublishRequest`. No longer depends on `BufferManager`. The handler
enqueues both items to the gateway queue.

### Files removed

- `scheduler.py` — replaced by `dispatch/dispatcher.py`
- `routing/stream_buffer.py` — replaced by `routing/gateway_queue.py`
- `routing/model.py` — `PublishRequest` replaced by `DownlinkItem`

### Files added

- `dispatch/__init__.py`, `dispatch/dispatcher.py` — `Dispatcher` (one per
  gateway, event-driven) and `DispatcherManager`
- `routing/gateway_queue.py` — `GatewayQueue` (thread-safe FIFO per gateway)
  and `GatewayDispatchQueue`
- `routing/models.py` — `DownlinkItem` dataclass
- `handlers/txack.py` — parses txack events, notifies dispatcher
- `transport/chirpstack_event_types/txack.py` — `TxAckEvent` pydantic model

### Files modified

- `config.py` — `FLUSH_INTERVAL_MS` replaced by `TXACK_TIMEOUT_S` (default 5.0)
- `registry/device_registry.py` — `register()` takes `gateway_id`, added
  `lookup_eui()` and `lookup_gateway()`
- `routing/forwarder.py` — returns `list[DownlinkItem]`, no buffer dependency
- `handlers/uplink.py` — enqueues items to gateway queue, extracts `gateway_id`
  from `rxInfo`
- `transport/mqtt_client.py` — subscribes to txack topic, dispatches to
  `TxAckHandler`
- `transport/chirpstack_endpoints.py` — added `get_event_txack()`
- `main.py` — wires `DispatcherManager` instead of `FlushScheduler`
- `.env` / `.env.example` — `TXACK_TIMEOUT_S` replaces `FLUSH_INTERVAL_MS`

## v1.0 — Initial implementation

Per-receiver buffer with periodic flush, immediate ACK bypass.
