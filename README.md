# lorawan-audio-server

Application server for LoRaWAN-based walkie-talkie audio transmission.
Receives audio packets from speaking nodes via ChirpStack MQTT, acknowledges
them on behalf of the receiver, buffers, and forwards to the listening node(s).

## Hardware

| Component | Device |
|---|---|
| End nodes | RAK3112 (ESP32 + SX1262) |
| Gateway | WM1302 on Raspberry Pi 5 |
| Network server | ChirpStack |

## Network Topology

```
┌──────────┐     ┌──────────┐     ┌────────────┐     ┌────────────┐
│  Node A  │────►│  Gateway │────►│ ChirpStack │────►│   This     │
│ (sender) │     │  WM1302  │     │  (MQTT)    │     │   Server   │
└──────────┘     └──────────┘     └────────────┘     └────────────┘
                                        ▲                     │
┌──────────┐     ┌──────────┐          │                     │
│  Node B  │◄────│  Gateway │◄─────────┘                     │
│(receiver)│     │  WM1302  │◄────────────────────────────────┘
└──────────┘     └──────────┘
```

- Single gateway, multiple nodes
- Uplink: 8 channels (multi-channel receiver)
- Downlink: 1 channel (single radio, serialized by ChirpStack)
- LoRaWAN Class C (always-on receiver for low latency)
- Frequency plan: EU868 (duty cycle disabled)

## How It Works

1. **Node A** transmits audio packets (sound split into multiple sequential packets)
2. **Gateway** receives and forwards to **ChirpStack** via MQTT
3. **This server** receives the MQTT message, parses the LoRa packet, and:
   - Sends an ACK back to Node A immediately (on behalf of Node B, to reduce airtime)
   - Buffers the packet for Node B
4. **Flush thread** periodically drains the buffer and publishes downlinks to ChirpStack
5. **ChirpStack** schedules and transmits the downlink to Node B via the gateway
6. **Node B** receives the audio packet (radio always open in Class C)

## Project Structure

```
lorawan-audio-server/
├── main.py                 Entry point, wiring, startup
├── config.py               Settings from .env
│
├── transport/              MQTT layer (wraps paho-mqtt)
│   └── mqtt_client.py
│
├── protocol/               Packet format — pure functions, zero deps
│   ├── models.py           Packet, Address, MsgType
│   ├── parser.py           bytes → Packet
│   ├── serializer.py       Packet → bytes, build_ack, build_downlink
│   └── crc.py              CRC8 calculation and verification
│
├── registry/               Device state
│   └── device_registry.py  Address ↔ DevEUI mapping
│
├── routing/                Forwarding logic
│   ├── forwarder.py        Routing decisions (ACK, forward, drop)
│   └── stream_buffer.py    Thread-safe per-receiver packet buffers
│
├── handlers/               Event handlers
│   ├── uplink.py           Uplink message handler
│   └── join.py             Join event handler
│
└── scheduler.py            Flush thread (periodic buffer drain)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

## Requirements

- Python 3.13+
- ChirpStack running and accessible via MQTT
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd lorawan-audio-server

# Install dependencies
uv sync

# Copy and edit environment config
cp .env.example .env
```

Edit `.env`:

```env
MQTT_BROKER_HOST=192.168.1.100
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
```

## Running

```bash
uv run python main.py
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MQTT_BROKER_HOST` | `localhost` | ChirpStack MQTT broker address |
| `MQTT_BROKER_PORT` | `1883` | ChirpStack MQTT broker port |
| `MQTT_USERNAME` | (empty) | MQTT auth username |
| `MQTT_PASSWORD` | (empty) | MQTT auth password |
| `FLUSH_INTERVAL_MS` | `100` | Flush thread interval in milliseconds |
| `CHIRPSTACK_APP_ID` | — | ChirpStack application UUID |

## Architecture

- **2 threads**: MQTT I/O thread (paho) + flush thread
- **No async**: unnecessary for this workload
- **Thread safety**: `threading.Lock` per buffer + one lock for the buffer dict
- **Pure protocol layer**: parser, serializer, CRC are stateless functions
- **Dependency injection**: `main.py` wires all components, no hidden globals

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full thread model, sequence diagrams,
dependency rules, and design patterns.
