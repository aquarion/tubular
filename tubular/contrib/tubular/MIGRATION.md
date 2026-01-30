# Tubular - YouTube Live Events Forwarder

Now organized as a proper Python package with modular structure.

## Package Structure

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

## Running

```bash
# As a module (recommended)
python -m tubular

# With validation
python -m tubular --validate

# Subscribe only
python -m tubular --subscribe-only
```

## Import Examples

```python
from tubular.config import YouTubeConfig
from tubular.monitor import YouTubeLiveMonitor
from tubular.api_client import YouTubeAPIClient

# Use the classes as needed
config = YouTubeConfig()
monitor = YouTubeLiveMonitor(config)
```

## Docker

The Dockerfile has been updated to work with the new package structure.

## Migration Notes

The original `tubular.py` has been split into logical modules:
- **config.py**: Environment validation and configuration
- **api_client.py**: YouTube API interactions with rate limiting and quota tracking
- **webhook.py**: Webhook forwarding with retry logic and PubSubHubbub subscription
- **server.py**: HTTP callback handler and example event triggers
- **monitor.py**: Main monitoring loop and stream management

All functionality remains the same - just better organized!
