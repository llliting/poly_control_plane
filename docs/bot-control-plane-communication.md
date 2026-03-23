# Bot ↔ Control Plane Communication Design

Status: accepted design direction

## Design Principles

1. **The bot is sovereign.** The trading hot path must never block, wait, or degrade because of the control plane. Every control-plane interaction is async, lossy-ok, and on a separate tokio task.
2. **Latency is the top priority.** No design choice should add microseconds to the tick-to-order path.
3. **Start simple, swap later.** Use trait-based abstractions so transport can change (HTTP → NATS → gRPC) without touching business logic.
4. **Same-EC2 now, multi-EC2 later.** Everything communicates over localhost today but must work over the network with only config changes.

## Why Not a Full Event Bus

A dedicated message bus (NATS, Redis pub/sub, Kafka) was considered and rejected for now:

| Concern | Event Bus (NATS/Redis) | HTTP + Traits |
|---|---|---|
| Latency impact on bot | Must maintain connection, handle reconnects | Zero — bot is the server |
| Operational complexity | Another service to deploy/monitor/restart | None — just HTTP |
| Cross-EC2 support | Yes | Yes (change host:port) |
| Fan-out (N subscribers) | Yes | No (but we don't need it — 1:1 communication) |
| Guaranteed delivery | Configurable | No (but commands are idempotent) |
| Swap to bus later | N/A | Change trait impl, zero business logic changes |

The communication pattern is simple: telemetry flows one way (bot → CP), commands flow the other (CP → bot). Neither requires pub/sub fan-out semantics. If that changes (e.g. multiple consumers for telemetry), the trait abstraction makes adding a bus straightforward.

## Current State

| Direction | Mechanism | Works cross-EC2? |
|---|---|---|
| Bot → CP (telemetry) | HTTP batch POST via tokio background task + unbounded channel | Yes |
| CP → Bot (commands) | Subprocess shell execution via `action_executor` | No |

The telemetry path (ingest) is already well-designed — non-blocking, batched, fire-and-forget. The command path is the problem: subprocess execution won't work across EC2 instances and only supports coarse start/stop.

## Target Architecture

```text
┌─────────────────────────────────────────────────────────┐
│  RUST BOT PROCESS                                       │
│                                                         │
│  ┌──────────────────────────────────────────┐           │
│  │  TRADING HOT PATH  (untouched)           │           │
│  │  WS → mpsc(20K) → Features → Model → Trader         │
│  └──────────────────────────────────────────┘           │
│       │ fire-and-forget                  ▲              │
│       ▼                                  │ read on idle │
│  ┌────────────┐                   ┌──────────────┐      │
│  │ Telemetry  │                   │ Command      │      │
│  │ Sink       │                   │ Receiver     │      │
│  │ (outbound) │                   │ (inbound)    │      │
│  └─────┬──────┘                   └──────┬───────┘      │
│        │                                 │              │
│  ══════╪═════════════════════════════════╪══════════    │
│        │     Transport Trait Layer        │              │
│  ══════╪═════════════════════════════════╪══════════    │
│        │                                 │              │
│  ┌─────▼──────┐                   ┌──────▼───────┐      │
│  │ HttpSink   │                   │ Axum CmdAPI  │      │
│  │ (existing) │                   │ (new, :8081) │      │
│  └─────┬──────┘                   └──────▲───────┘      │
└────────┼─────────────────────────────────┼──────────────┘
         │                                 │
         ▼                                 │
┌────────────────────────────────────────────────────────┐
│  CONTROL PLANE (FastAPI)                               │
│                                                        │
│  POST /ingest/batch  ◄── telemetry (existing)          │
│  HTTP POST to bot:8081/cmd/*  ──► commands (new)       │
│                                                        │
│  action_executor evolves:                              │
│    subprocess → HTTP POST bot_host:8081/cmd/...        │
└────────────────────────────────────────────────────────┘
```

## Two Core Abstractions

### 1. TelemetrySink (outbound: bot → control plane)

Already implemented as the ingest worker. Formalized as a trait:

```rust
/// Fire-and-forget outbound telemetry. Implementations must never block
/// the caller. Returns unit, not Result — the bot does not care if the
/// control plane is down.
#[async_trait]
pub trait TelemetrySink: Send + Sync + 'static {
    async fn emit(&self, event: TelemetryEvent);
}
```

Implementations:
- `HttpBatchSink` — current ingest worker (tokio task + unbounded channel + periodic HTTP flush)
- `NoopSink` — for running bots without a control plane
- `MockSink` — for tests (collects events in a `Vec`)

No changes needed to the existing ingest path. This trait just formalizes the interface.

### 2. CommandSource (inbound: control plane → bot)

New. The bot exposes a lightweight HTTP command server on a separate port.

```rust
/// Inbound command receiver. The bot spawns a task that calls
/// next_command() in a loop and processes commands without
/// blocking the trading hot path.
#[async_trait]
pub trait CommandSource: Send + Sync + 'static {
    async fn next_command(&self) -> Command;
}
```

Implementations:
- `AxumCommandSource` — HTTP server on `:8081`, bridges HTTP requests to a `tokio::mpsc` channel
- `NatsCommandSource` — future, if we ever need pub/sub
- `MockCommandSource` — for tests

## Command Types

Start with a small, extensible enum:

```rust
pub enum Command {
    /// Hot-reload an env var without process restart
    UpdateEnv { key: String, value: String },

    /// Cancel all open orders immediately (emergency kill switch)
    CancelAllOrders,

    /// Pause trading (sets trading_enabled = false in memory)
    PauseTrading,

    /// Resume trading
    ResumeTrading,

    /// Request immediate telemetry flush to control plane
    FlushTelemetry,

    /// Graceful shutdown
    Shutdown,
}
```

New command types are added by extending this enum. The HTTP command server deserializes them from JSON.

## How Commands Stay Off the Hot Path

```text
                   ┌─────────────────────────┐
 HTTP POST :8081 → │  Axum Command Server    │
                   │  (own tokio task)        │
                   └──────────┬──────────────┘
                              │ mpsc::channel(64)
                              ▼
                   ┌─────────────────────────┐
                   │  Command Processor      │
                   │  (own tokio task)        │
                   │                         │
                   │  match cmd {            │
                   │    UpdateEnv → config   │
                   │      .write()           │
                   │    PauseTrading →       │
                   │      config.write()     │
                   │    CancelAllOrders →    │
                   │      trader.cancel()    │
                   │  }                      │
                   └─────────────────────────┘
                              │
                    Arc<RwLock<AppConfig>>
                              │
                              ▼
                   ┌─────────────────────────┐
                   │  Trading Hot Path       │
                   │  (own tokio task)        │
                   │                         │
                   │  Only ever takes        │
                   │  config.read() locks    │
                   │  — never blocks         │
                   └─────────────────────────┘
```

Key guarantees:
- The trading loop **never awaits** anything command-related
- It reads config via `Arc<RwLock<AppConfig>>` with read locks only
- Commands are rare (~1/min at most) vs ticks (~100/sec), so lock contention is negligible
- If the command server crashes, trading continues unaffected

## Bot Command HTTP API

Served on a separate port (default `:8081`) from the health server (`:8080`).

### POST /cmd/update-env

```json
{ "key": "MODEL_THRESHOLD", "value": "0.90" }
```

Response: `200 OK` with `{ "applied": true }`

Allows the control plane UI to tweak parameters without restarting the bot.

### POST /cmd/pause-trading

No body. Sets `trading_enabled = false` in the live config.

Response: `200 OK` with `{ "trading_enabled": false }`

### POST /cmd/resume-trading

No body. Sets `trading_enabled = true` in the live config.

Response: `200 OK` with `{ "trading_enabled": true }`

### POST /cmd/cancel-all-orders

No body. Cancels all open orders on Polymarket.

Response: `200 OK` with `{ "cancelled": <count> }`

### POST /cmd/flush-telemetry

No body. Forces an immediate telemetry batch flush.

Response: `200 OK`

### POST /cmd/shutdown

No body. Graceful shutdown: cancel orders, flush telemetry, exit.

Response: `200 OK` (connection may close before response completes)

### Authentication

All command endpoints require the `X-Cmd-Key` header matching the `BOT_CMD_API_KEY` env var. Same pattern as the existing ingest API key.

## Control Plane Changes

### action_executor.py evolution

Current: polls `action_requests` table, runs subprocess shell commands.

Target: polls `action_requests` table, sends HTTP POST to `bot_host:bot_cmd_port/cmd/<action>`.

```python
# Before (subprocess)
subprocess.run(["bash", "-c", command_map[service_key]["stop"]])

# After (HTTP to bot command server)
async with httpx.AsyncClient() as client:
    resp = await client.post(
        f"http://{bot_host}:{bot_cmd_port}/cmd/pause-trading",
        headers={"X-Cmd-Key": bot_cmd_api_key},
        timeout=5.0,
    )
```

### runners / service_instances table additions

Add columns to track bot command endpoint:

```sql
ALTER TABLE runners ADD COLUMN cmd_host text;
ALTER TABLE runners ADD COLUMN cmd_port integer;
```

Or store per-service if bots run on different ports:

```sql
ALTER TABLE service_instances ADD COLUMN cmd_port integer;
```

### New UI endpoints for commands

```text
POST /api/v1/services/{service_key}/commands/pause-trading
POST /api/v1/services/{service_key}/commands/resume-trading
POST /api/v1/services/{service_key}/commands/cancel-all-orders
POST /api/v1/services/{service_key}/commands/update-env
  body: { "key": "MODEL_THRESHOLD", "value": "0.90" }
```

These create an `action_request` row for audit, then forward the HTTP call to the bot.

## Rust Bot Changes

New or modified files:

| File | Change |
|---|---|
| `src/command.rs` | New. `Command` enum, `CommandSource` trait, `AxumCommandSource` implementation |
| `src/config.rs` | Wrap `AppConfig` in `Arc<RwLock<>>` for hot-reload support |
| `src/main.rs` | Spawn command server task + command processor task |

Existing health server on `:8080` stays unchanged. Command server runs on `:8081`.

## Configuration

### Same EC2 (current)

```env
# Bot
BOT_CMD_BIND=127.0.0.1:8081
BOT_CMD_API_KEY=shared-secret-cmd

# Control plane
# runners table: cmd_host=127.0.0.1, cmd_port=8081
```

### Separate EC2 (future)

```env
# Bot (on EC2-B)
BOT_CMD_BIND=0.0.0.0:8081
BOT_CMD_API_KEY=shared-secret-cmd

# Control plane (on EC2-A)
# runners table: cmd_host=10.0.1.5, cmd_port=8081
# Security: VPC security group restricts :8081 to control plane IP only
```

No code changes — only config and network rules.

## Migration Path

### Phase 1: Bot command server (now)

- Add `src/command.rs` to Rust bot with `AxumCommandSource`
- Wrap `AppConfig` in `Arc<RwLock<>>`
- Spawn command server on `:8081` alongside existing health server on `:8080`
- Update `action_executor.py` to call HTTP instead of subprocess
- Keep existing ingest (telemetry) path unchanged

### Phase 2: Multi-EC2 (when needed)

- Store `cmd_host` and `cmd_port` per runner/service in the database
- Action executor looks up the right host before sending commands
- Bind bot command server on `0.0.0.0` instead of `127.0.0.1`
- Add VPC security group rules

### Phase 3: Event bus (if ever needed)

- Implement `NatsTelemetrySink` and `NatsCommandSource` behind the same traits
- Swap implementations via config flag
- Zero changes to trading logic, command processing, or control plane API layer

## Relationship to Existing Docs

- **control-plane-design.md**: This doc supersedes the "Action Execution" section. The multi-account/multi-strategy architecture and Polymarket polling designs remain unchanged.
- **live-trading-control-plane-spec.md**: The Runner Agent API (Section 5) is compatible with this design. The runner agent becomes the intermediary that knows bot command endpoints and forwards commands. The external API (Section 4) and database schema (Section 6) are unaffected.
