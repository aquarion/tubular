# Tubular - YouTube Live Events Webhook Forwarder

Tubular is a Python package that monitors YouTube live streams and forwards events as webhooks to another server (such as the Stream Delta Laravel application). It subscribes to YouTube channel feeds via PubSubHubbub and polls the YouTube Data API v3 for real-time stream status and chat activity.

## Package Structure

Now organized as a modular Python package:

```
tubular/
├── __init__.py          # Package initialization
├── __main__.py          # Entry point (python -m tubular)
├── config.py            # Configuration and environment validation
├── api_client.py        # YouTube API client with quota tracking
├── webhook.py           # Webhook forwarding and PubSubHubbub
├── server.py            # HTTP server for callbacks
└── monitor.py           # Main monitor class
```

## Features

- **Live Stream Monitoring**: Detects when streams start and end
- **Viewer Tracking**: Monitors concurrent viewer count changes
- **Chat Integration**: Captures chat messages, Super Chats, and new memberships
- **PubSubHubbub**: Real-time feed notifications from YouTube
- **Webhook Forwarding**: Sends structured events to your application
- **Redis Heartbeat**: Publishes health status for monitoring
- **State Persistence**: Saves stream state to disk for restarts
- **Retry Logic**: Automatically retries failed webhook deliveries

## Requirements

- Python 3.11+
- YouTube Data API v3 key (from Google Cloud Console)
- Redis server (optional, for heartbeat monitoring)
- Public callback URL (for PubSubHubbub subscriptions)

## Installation

### Standalone

```bash
cd contrib/tubular
pip install -r requirements.txt
```

### Docker Compose

Tubular is included in the Stream Delta docker-compose configuration and starts automatically with `sail up`.

## Configuration

All configuration is done via environment variables. Copy `.env.example` to `.env` and configure:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key | `AIzaSyC...` |
| `YOUTUBE_CHANNEL_ID` | Channel ID to monitor | `UCxxxxxxxxxxxxxx` |
| `WEBHOOK_TARGET_URL` | Endpoint to receive webhooks | `https://example.com/webhooks/youtube` |
| `YOUTUBE_CALLBACK_URL` | Public callback URL for PubSubHubbub | `https://your-server.com:8080/youtube/callback` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | _(empty)_ | Secret for HMAC webhook signing |
| `TUBULAR_CALLBACK_PORT` | `8080` | Port for callback HTTP server |
| `YOUTUBE_POLL_INTERVAL` | `60` | Polling interval in seconds |
| `CALLBACK_BIND_ADDRESS` | _(all interfaces)_ | Bind address for callback server |
| `REDIS_HOST` | `localhost` | Redis host for heartbeat |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | _(empty)_ | Redis password |
| `REDIS_DB` | `0` | Redis database number |
| `TUBULAR_HEARTBEAT_INTERVAL` | `30` | Heartbeat update interval (seconds) |

## Running

### Validate Configuration

```bash
python tubular.py --validate
```

### Start Monitoring

```bash
python tubular.py
```

### Docker Compose

```bash
# Start with all services
sail up -d

# View logs
sail logs -f tubular

# Stop tubular only
sail stop tubular

# Rebuild after changes
sail build tubular
```

## Webhook Events

All webhooks are sent as HTTP POST requests to `WEBHOOK_TARGET_URL` with JSON payloads. If `WEBHOOK_SECRET` is configured, requests include an `X-Hub-Signature` header with HMAC-SHA256 signature.

### Live Stream Events

#### `youtube.live.started`

Triggered when a live stream begins.

**Payload:**
```json
{
  "event_type": "youtube.live.started",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "title": "My Live Stream",
    "description": "Stream description",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "channel_title": "My Channel",
    "started_at": "2026-01-30T12:00:00Z",
    "scheduled_start": "2026-01-30T12:00:00Z",
    "concurrent_viewers": 42
  }
}
```

#### `youtube.live.update`

Triggered when stream metadata changes (via PubSubHubbub feed).

**Payload:**
```json
{
  "event_type": "youtube.live.update",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "title": "Updated Stream Title",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "published": "2026-01-30T12:00:00Z"
  }
}
```

#### `youtube.live.viewers_updated`

Triggered when concurrent viewer count changes significantly.

**Payload:**
```json
{
  "event_type": "youtube.live.viewers_updated",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "concurrent_viewers": 1337,
    "title": "My Live Stream",
    "channel_id": "UCxxxxxxxxxxxxxx"
  }
}
```

#### `youtube.live.ended`

Triggered when a live stream ends.

**Payload:**
```json
{
  "event_type": "youtube.live.ended",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "title": "My Live Stream",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "ended_at": "2026-01-30T14:00:00Z"
  }
}
```

### Chat Events

#### `youtube.chat.message`

Triggered for each chat message during a live stream.

**Payload:**
```json
{
  "event_type": "youtube.chat.message",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "message": "Hello world!",
    "author_name": "Username",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "is_moderator": false,
    "is_sponsor": false,
    "timestamp": "2026-01-30T12:05:00Z"
  }
}
```

#### `youtube.chat.superchat`

Triggered when someone sends a Super Chat.

**Payload:**
```json
{
  "event_type": "youtube.chat.superchat",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "message": "Great stream!",
    "author_name": "GenerousViewer",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "amount": 5000000,
    "currency": "USD",
    "amount_display": "$5.00",
    "timestamp": "2026-01-30T12:10:00Z"
  }
}
```

**Note:** `amount` is in micros (1,000,000 = $1.00 USD)

#### `youtube.chat.new_sponsor`

Triggered when someone becomes a channel member.

**Payload:**
```json
{
  "event_type": "youtube.chat.new_sponsor",
  "event_data": {
    "video_id": "dQw4w9WgXcQ",
    "author_name": "NewMember",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "timestamp": "2026-01-30T12:15:00Z"
  }
}
```

## Webhook Signature Verification

If `WEBHOOK_SECRET` is configured, webhooks include an `X-Hub-Signature` header:

```
X-Hub-Signature: sha256=<hmac_hex_digest>
```

**Verification example (Python):**
```python
import hmac
import hashlib

def verify_signature(payload_body, signature_header, secret):
    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
```

## Redis Heartbeat

When Redis is configured, Tubular publishes status updates to the `tubular:heartbeat` key every `TUBULAR_HEARTBEAT_INTERVAL` seconds.

**Heartbeat data:**
```json
{
  "timestamp": "2026-01-30T12:30:00Z",
  "uptime_seconds": 3600,
  "active_streams": 1,
  "events_forwarded": 42,
  "api_calls": 120,
  "status": "running",
  "channel_id": "UCxxxxxxxxxxxxxx"
}
```

**Check status:**
```bash
redis-cli GET tubular:heartbeat
```

The key expires after 3x the heartbeat interval to automatically clear stale data.

## State Persistence

Tubular saves its state to `tubular_state.pkl` in the working directory. This includes:
- Active stream information
- Chat pagination tokens
- Statistics

State is automatically restored on restart, allowing seamless recovery after crashes or restarts.

## Troubleshooting

### Validation Errors

Run with `--validate` flag to see detailed configuration validation:
```bash
python tubular.py --validate
```

### YouTube API Quota Exceeded

The script monitors quota usage and stops making API calls if quota is exceeded. Default quota is 10,000 units/day. Consider:
- Increasing poll interval
- Requesting quota increase from Google
- Monitoring quota in [Google Cloud Console](https://console.cloud.google.com/apis/dashboard)

### PubSubHubbub Not Working

Ensure `YOUTUBE_CALLBACK_URL` is:
- Publicly accessible from the internet
- Using HTTPS (or HTTP for local testing)
- Not blocked by firewall
- Returning proper responses (handled automatically by script)

### Redis Connection Failed

Redis is optional. If connection fails, tubular will log a warning and continue without heartbeat functionality.

### Webhook Delivery Failures

Failed webhooks are automatically retried with exponential backoff (3 attempts). Check:
- Target URL is accessible
- Server accepts POST requests with JSON
- Firewall allows outbound connections
- Server doesn't require authentication (or implement webhook signature verification)

## License

MIT
