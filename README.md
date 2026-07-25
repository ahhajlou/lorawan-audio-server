# lorawan-audio-server

Application server for LoRaWAN-based walkie-talkie audio transmission.
Receives audio packets from speaking nodes via ChirpStack MQTT, acknowledges
them on behalf of the receiver, and forwards to the listening node(s).

All downlinks — both ACKs and data — are serialized through a single
per-gateway dispatch queue, gated on ChirpStack `txack` events, to prevent
collisions on the gateway's single TX chain.

## Hardware

| Component | Device |
|---|---|
| End nodes | RAK3112 (ESP32 + SX1262) |
| Gateway | WM1302 on Raspberry Pi 5 |
| Network server | ChirpStack |

## Network Topology

```
Node A ──uplink──► Gateway (WM1302) ──MQTT──► ChirpStack ──MQTT──► This Server
Node A ◄──ACK────┐
Node B ◄──data───┤── Gateway ◄── ChirpStack ◄── This Server
                 │
                 └── both downlinks pass through ONE dispatch queue,
                     serialized against the gateway's TX chain
```

- Single gateway, multiple nodes
- Uplink: 8 channels (multi-channel receiver)
- Downlink: 1 channel (single radio, one packet on air at a time)
- LoRaWAN Class C (always-on receiver for low latency)
- Frequency plan: EU868 (duty cycle disabled)

## How It Works

1. **Node A** transmits audio packets
2. **Gateway** receives and forwards to **ChirpStack** via MQTT
3. **This server** parses the uplink, then enqueues two items into a
   per-gateway FIFO queue: ACK (for Node A) then data (for Node B)
4. **Dispatcher** (one per gateway) pops items one at a time, publishes
   each to ChirpStack, and waits for the `txack` confirmation before
   sending the next
5. **ChirpStack** transmits the downlink to the target node via the gateway

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MQTT_BROKER_HOST` | `localhost` | ChirpStack MQTT broker address |
| `MQTT_BROKER_PORT` | `1883` | ChirpStack MQTT broker port |
| `MQTT_USERNAME` | (empty) | MQTT auth username |
| `MQTT_PASSWORD` | (empty) | MQTT auth password |
| `TXACK_TIMEOUT_S` | `5.0` | Max seconds to wait for txack before advancing |
| `CHIRPSTACK_APP_ID` | — | ChirpStack application UUID |

## Requirements

- Python 3.13+
- ChirpStack running and accessible via MQTT
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
git clone <repo-url>
cd lorawan-audio-server
uv sync
cp .env.example .env
```

Edit `.env` with your MQTT broker address, ChirpStack app ID, and log level.

## Running

```bash
uv run python main.py
```

## Tests

```bash
uv run ruff check
uv run pytest
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.
