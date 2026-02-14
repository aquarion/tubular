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
| `TUBULAR_WEBHOOK_URL` | Endpoint to receive webhooks | `https://example.com/webhooks/youtube` |
| `TUBULAR_CALLBACK_URL` | Public callback URL for PubSubHubbub | `https://your-server.com:8080/youtube/callback` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | _(empty)_ | Secret for HMAC webhook signing |
| `TUBULAR_CALLBACK_PORT` | `8080` | Port for callback HTTP server |
| `YOUTUBE_POLL_INTERVAL` | `60` | Polling interval in seconds |
| `YOUTUBE_DISABLE_IDLE_POLLING` | `false` | Disable API polling when no live streams are active |
| `CALLBACK_BIND_ADDRESS` | _(all interfaces)_ | Bind address for callback server |
| `REDIS_HOST` | `localhost` | Redis host for heartbeat |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_USERNAME` | _(empty)_ | Redis username for ACL (Redis 6+) |
| `REDIS_PASSWORD` | _(empty)_ | Redis password |
| `REDIS_DB` | `0` | Redis database number |
| `TUBULAR_HEARTBEAT_INTERVAL` | `30` | Heartbeat update interval (seconds) |
| `TUBULAR_LOG_FILE` | _(stdout)_ | Path to log file (enables file logging) |
| `TUBULAR_LOG_MAX_BYTES` | `10485760` | Max log file size in bytes before rotation |
| `TUBULAR_LOG_BACKUP_COUNT` | `5` | Number of backup log files to keep |
| `TUBULAR_LOG_RETENTION_DAYS` | `7` | Days to keep old log files |

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

## Endpoints

Tubular exposes an HTTP server on `TUBULAR_CALLBACK_PORT` (default: 8080) to handle PubSubHubbub callbacks, testing, and health checks.

### PubSubHubbub Callback

**`GET /youtube/callback`** - PubSubHubbub verification request

Handles subscription/unsubscription verification from the YouTube PubSubHubbub hub. Automatically responds to `hub_challenge` parameters.

**Response:** `200 OK` with hub challenge value

---

**`POST /youtube/callback`** - PubSubHubbub feed notifications

Receives Atom feed updates when YouTube channel videos are published or updated. Automatically parses video details and forwards as webhook events.

**Content-Type:** `application/atom+xml`

**Response:** `200 OK` on success

---

### Health & Testing

**`GET /data/events`** - List available example events

Returns a JSON array of event types available for manual testing.

**Response:**
```json
{
  "available_events": [
    "youtube.live.started",
    "youtube.live.ended",
    "youtube.chat.message",
    "youtube.chat.superchat",
    "youtube.chat.new_sponsor"
  ]
}
```

---

**`POST /example/{event_type}`** - Trigger example event

Manually trigger a test event of the specified type. Useful for testing webhook delivery and integration development.

**Example:** `POST /example/youtube.live.started`

**Response:** `200 OK` with confirmation message

**Available event types:**
- `youtube.live.started`
- `youtube.live.update`
- `youtube.live.viewers_updated`
- `youtube.live.ended`
- `youtube.chat.message`
- `youtube.chat.superchat`
- `youtube.chat.new_sponsor`
- `youtube.chat.supersticker`
- `youtube.chat.user_banned`
- `youtube.chat.message_deleted`
- `youtube.chat.poll`

---

## Webhook Events

All webhooks are sent as HTTP POST requests to `TUBULAR_WEBHOOK_URL` with JSON payloads. If `WEBHOOK_SECRET` is configured, requests include an `X-Hub-Signature` header with HMAC-SHA256 signature.

**Webhook Structure:**
- `event_type` - Type of event (e.g., `youtube.live.started`)
- `event` - Event-specific data (varies by event type)
- `timestamp` - When the webhook was sent (ISO 8601)
- `source` - Always `"youtube"`

### Live Stream Events

**Note:** Live stream events are custom events created by Tubular by monitoring YouTube's live streaming status. They are derived from the YouTube Data API v3 Videos resource (`liveStreamingDetails` field) and PubSubHubbub feed updates, not from a direct API message type.

#### `youtube.live.started`

Triggered when a live stream begins.

**Payload:**
```json
{
  "event_type": "youtube.live.started",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "title": "My Live Stream",
    "description": "Stream description",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "channel_title": "My Channel",
    "started_at": "2026-01-30T12:00:00Z",
    "scheduled_start": "2026-01-30T12:00:00Z",
    "concurrent_viewers": 42
  },
  "timestamp": "2026-01-30T12:00:01Z",
  "source": "youtube"
}
```

#### `youtube.live.update`

Triggered when a PubSubHubbub feed notification is received from YouTube. Includes raw feed data for detailed inspection.

**Payload:**
```json
{
  "event_type": "youtube.live.update",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "title": "My Live Stream",
    "published_at": "2026-01-30T12:00:00Z",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "channel_title": "My Channel",
    "live_streaming_details": {
      "actualStartTime": "2026-01-30T12:00:00Z",
      "scheduledStartTime": "2026-01-30T12:00:00Z",
      "concurrentViewers": 42
    },
    "pubsub_data": {
      "@attributes": {
        "xmlns": "http://www.w3.org/2005/Atom",
        "xmlns:yt": "http://www.youtube.com/xml/schemas/2015"
      },
      "title": "#text",
      "id": "yt:channel:UCxxxxxxxxxxxxxx",
      "link": {
        "@attributes": {
          "href": "http://www.youtube.com/channel/UCxxxxxxxxxxxxxx"
        }
      },
      "entry": {
        "id": "yt:video:dQw4w9WgXcQ",
        "yt:videoId": "dQw4w9WgXcQ",
        "title": "My Live Stream",
        "published": "2026-01-30T12:00:00Z"
      }
    }
  },
  "timestamp": "2026-01-30T12:00:01Z",
  "source": "youtube"
}
```

**Note:** `pubsub_data` contains the Atom feed as a parsed dictionary structure.

#### `youtube.live.viewers_updated`

Triggered when concurrent viewer count changes significantly (>10% or >100 viewers).

**Payload:**
```json
{
  "event_type": "youtube.live.viewers_updated",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "concurrent_viewers": 1337,
    "previous_viewers": 1200,
    "title": "My Live Stream",
    "channel_id": "UCxxxxxxxxxxxxxx"
  },
  "timestamp": "2026-01-30T12:05:00Z",
  "source": "youtube"
}
```



#### `youtube.live.ended`

Triggered when a live stream ends.

**Payload:**
```json
{
  "event_type": "youtube.live.ended",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "title": "My Live Stream",
    "channel_id": "UCxxxxxxxxxxxxxx",
    "ended_at": "2026-01-30T14:00:00Z"
  },
  "timestamp": "2026-01-30T14:00:01Z",
  "source": "youtube"
}
```

### Chat Events

All chat event types are verified against the official [YouTube Data API v3 Live Chat Messages documentation](https://developers.google.com/youtube/v3/live/docs/liveChatMessages#resource).

#### `youtube.chat.message`

Triggered for each chat message during a live stream.

**Payload:**
```json
{
  "event_type": "youtube.chat.message",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "message": "Hello world!",
    "author_name": "Username",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "is_moderator": false,
    "is_sponsor": false,
    "timestamp": "2026-01-30T12:05:00Z"
  },
  "timestamp": "2026-01-30T12:05:01Z",
  "source": "youtube"
}
```

#### `youtube.chat.superchat`

Triggered when someone sends a Super Chat.

**Payload:**
```json
{
  "event_type": "youtube.chat.superchat",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "message": "Great stream!",
    "author_name": "GenerousViewer",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "amount": 5000000,
    "currency": "USD",
    "amount_display": "$5.00",
    "tier": 4,
    "timestamp": "2026-01-30T12:10:00Z"
  },
  "timestamp": "2026-01-30T12:10:01Z",
  "source": "youtube"
}
```

**Note:** `amount` is in micros (1,000,000 = $1.00 USD). `tier` indicates the Super Chat level (1-5, with 5 being the most expensive).

#### `youtube.chat.new_sponsor`

Triggered when someone becomes a channel member.

**Payload:**
```json
{
  "event_type": "youtube.chat.new_sponsor",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "author_name": "NewMember",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "member_level_name": "Level 1 Member",
    "is_upgrade": false,
    "timestamp": "2026-01-30T12:15:00Z"
  },
  "timestamp": "2026-01-30T12:15:01Z",
  "source": "youtube"
}
```

**Note:** `member_level_name` is the tier name defined by the channel. `is_upgrade` indicates whether this user upgraded from a lower membership tier.

**Note:** `amount` is in micros (1,000,000 = $1.00 USD)

#### `youtube.chat.supersticker`

Triggered when someone sends a paid animated sticker.

**Payload:**
```json
{
  "event_type": "youtube.chat.supersticker",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "author_name": "StickerUser",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "sticker_id": "STICKER_ID_12345",
    "sticker_alt_text": "A thumbs up gesture",
    "sticker_language": "en",
    "amount": 5000000,
    "currency": "USD",
    "amount_display": "$5.00",
    "tier": 4,
    "timestamp": "2026-01-30T12:20:00Z"
  },
  "timestamp": "2026-01-30T12:20:01Z",
  "source": "youtube"
}
```

**Note:** `amount` is in micros (1,000,000 = $1.00 USD). `sticker_id` is a unique ID for the sticker image. Image URLs are not available via the API. `tier` indicates the Super Sticker tier (1-4, with 4 being the most expensive).

#### `youtube.chat.user_banned`

Triggered when a user is banned from chat.

**Payload:**
```json
{
  "event_type": "youtube.chat.user_banned",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "banned_user_name": "BannedUser",
    "banned_user_channel_id": "UCyyyyyyyyyyyyyy",
    "ban_type": "temporary",
    "ban_duration_seconds": 3600,
    "timestamp": "2026-01-30T12:25:00Z"
  },
  "timestamp": "2026-01-30T12:25:01Z",
  "source": "youtube"
}
```

**Note:** `ban_type` is either `"permanent"` or `"temporary"`. `ban_duration_seconds` is only present for temporary bans.

#### `youtube.chat.message_deleted`

Triggered when a chat message is deleted by a moderator.

**Payload:**
```json
{
  "event_type": "youtube.chat.message_deleted",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "deleted_message_id": "Ugzxxxxx...",
    "timestamp": "2026-01-30T12:30:00Z"
  },
  "timestamp": "2026-01-30T12:30:01Z",
  "source": "youtube"
}
```

#### `youtube.chat.poll`

Triggered when a poll is created or updated in the live chat.

**Payload:**
```json
{
  "event_type": "youtube.chat.poll",
  "event": {
    "video_id": "dQw4w9WgXcQ",
    "author_name": "PollCreator",
    "author_channel_id": "UCyyyyyyyyyyyyyy",
    "question": "What should I play next?",
    "options": [
      {
        "text": "Game A",
        "tally": "42"
      },
      {
        "text": "Game B",
        "tally": "38"
      },
      {
        "text": "Game C",
        "tally": "25"
      }
    ],
    "status": "active",
    "timestamp": "2026-01-30T12:40:00Z"
  },
  "timestamp": "2026-01-30T12:40:01Z",
  "source": "youtube"
}
```

## Webhook Signature Verification

All webhook requests include the full payload (including `timestamp` and `source`) in the request body. If `WEBHOOK_SECRET` is configured, requests include an `X-Hub-Signature` header with HMAC-SHA256 signature calculated over the entire JSON payload.

```
X-Hub-Signature: sha256=<hmac_hex_digest>
```

**Verification example (Python):**
```python
import hmac
import hashlib
import json

def verify_signature(payload_body, signature_header, secret):
    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body if isinstance(payload_body, bytes) else payload_body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)

# Usage:
# payload_body is the raw request body (bytes or string)
# signature_header is the X-Hub-Signature header value
# secret is your WEBHOOK_SECRET
is_valid = verify_signature(request.body, request.headers.get('X-Hub-Signature'), my_secret)
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

Ensure `TUBULAR_CALLBACK_URL` is:
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
