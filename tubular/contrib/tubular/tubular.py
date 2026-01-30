#!/usr/bin/env python3
"""
YouTube Live Events Webhook Forwarder

This script subscribes to YouTube live events using the YouTube Data API v3
and forwards them as webhooks to another server (like the stream-delta Laravel app).

Features:
- Subscribe to YouTube channel live events via PubSubHubbub
- Poll YouTube Data API for live stream status
- Forward events as webhooks to a configured endpoint
- Support for various YouTube live events (stream start, end, chat, super chats, etc.)
"""

import os
import sys
import json
import logging
import hashlib
import hmac
import time
import pickle
import requests
import redis
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading
import argparse
from collections import deque

# Determine log directory - use app root storage/logs if available, otherwise current directory
script_dir = os.path.dirname(os.path.abspath(__file__))
app_root = os.path.abspath(os.path.join(script_dir, '../../'))
log_dir = os.path.join(app_root, 'storage/logs')

# Create log directory if it doesn't exist
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'tubular.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('tubular')


def load_env_file(env_path: str) -> None:
    """Load environment variables from .env file if it exists"""
    if not os.path.exists(env_path):
        return

    logger.info(f"Loading environment variables from {env_path}")

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                # Only set if not already in environment
                if key and value and key not in os.environ:
                    os.environ[key] = value


def validate_environment(show_details: bool = True) -> Tuple[bool, List[str]]:
    """
    Validate required and optional environment variables

    Args:
        show_details: If True, print detailed validation results

    Returns:
        Tuple of (is_valid, missing_vars)
    """
    # Required variables with descriptions
    required_vars = {
        'YOUTUBE_API_KEY': 'YouTube Data API v3 key from https://console.cloud.google.com/apis/credentials',
        'YOUTUBE_CHANNEL_ID': 'YouTube channel ID to monitor (format: UCxxxxxxxxxxxxxx)',
    }

    # Optional variables with defaults and descriptions
    optional_vars = {
        'WEBHOOK_TARGET_URL': {
            'default': 'http://localhost/webhooks/youtube',
            'description': 'URL to forward webhook events to'
        },
        'WEBHOOK_SECRET': {
            'default': '',
            'description': 'Secret for HMAC signing of webhook payloads (optional)'
        },
        'YOUTUBE_CALLBACK_URL': {
            'default': 'http://localhost:8080/youtube/callback',
            'description': 'Public callback URL for PubSubHubbub (must be internet accessible)'
        },
        'TUBULAR_CALLBACK_PORT': {
            'default': '8080',
            'description': 'Port for the callback HTTP server'
        },
        'YOUTUBE_POLL_INTERVAL': {
            'default': '60',
            'description': 'Polling interval in seconds (30-120 recommended)'
        },
        'CALLBACK_BIND_ADDRESS': {
            'default': '',
            'description': 'Address to bind callback server (empty=all, 127.0.0.1=localhost only)'
        },
        'REDIS_HOST': {
            'default': 'localhost',
            'description': 'Redis host for heartbeat updates'
        },
        'REDIS_PORT': {
            'default': '6379',
            'description': 'Redis port'
        },
        'REDIS_PASSWORD': {
            'default': '',
            'description': 'Redis password (optional)'
        },
        'REDIS_DB': {
            'default': '0',
            'description': 'Redis database number'
        },
        'TUBULAR_HEARTBEAT_INTERVAL': {
            'default': '30',
            'description': 'Heartbeat interval in seconds (how often to update Redis)'
        },
    }

    missing_vars = []

    if show_details:
        print("\n" + "=" * 70)
        print("Tubular YouTube Webhook Forwarder - Environment Validation")
        print("=" * 70 + "\n")

        print("Required Variables:")
        print("-" * 70)

    # Check required variables
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)

        if not value:
            missing_vars.append(var_name)
            if show_details:
                print(f"✗ {var_name:<25} NOT SET")
                print(f"  → {description}")
        elif show_details:
            # Mask sensitive values - don't show actual values
            if 'KEY' in var_name or 'SECRET' in var_name:
                display_value = "***" + value[-4:] if len(value) > 4 else "***"
            else:
                display_value = value
            print(f"✓ {var_name:<25} {display_value}")

    if show_details:
        print("\nOptional Variables:")
        print("-" * 70)

        # Show optional variables
        for var_name, config in optional_vars.items():
            value = os.getenv(var_name)
            default = config['default']

            if not value:
                if default:
                    print(f"○ {var_name:<25} using default: {default}")
                else:
                    print(f"○ {var_name:<25} not set (optional)")
            else:
                # Mask sensitive values
                if 'SECRET' in var_name:
                    display_value = "***" + value[-4:] if len(value) > 4 else "***"
                else:
                    display_value = value
                print(f"✓ {var_name:<25} {display_value}")

        print("\n" + "=" * 70)

    # Print result
    if missing_vars:
        if show_details:
            print("❌ VALIDATION FAILED - Missing required variables!\n")
            print("Missing variables:")
            for var in missing_vars:
                print(f"  • {var}")
            print("\nTo fix this:")
            print("  1. Create a .env file in the same directory as this script:")

            script_dir = os.path.dirname(os.path.abspath(__file__))
            env_example = os.path.join(script_dir, '.env.example')
            env_file = os.path.join(script_dir, '.env')

            if os.path.exists(env_example):
                print(f"     cp {env_example} {env_file}")
            else:
                print(f"     touch {env_file}")

            print(f"\n  2. Edit {env_file} and set the required variables:")
            for var in missing_vars:
                print(f"     {var}=your-value-here")

            print("\n  3. Run this script again")
            print()

        return False, missing_vars
    else:
        if show_details:
            print("✅ VALIDATION PASSED - All required variables are set!")
            print()
        return True, []


class YouTubeConfig:
    """Configuration for YouTube API and webhook forwarding"""

    def __init__(self, validate: bool = True):
        """
        Initialize configuration from environment variables

        Args:
            validate: If True, validate environment before loading config
        """
        if validate:
            is_valid, missing = validate_environment(show_details=False)
            if not is_valid:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing)}. "
                    "Run with --validate flag to see details."
                )

        self.api_key = os.getenv('YOUTUBE_API_KEY')
        self.channel_id = os.getenv('YOUTUBE_CHANNEL_ID')
        self.webhook_url = os.getenv('WEBHOOK_TARGET_URL', 'http://localhost/webhooks/youtube')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', '')
        self.callback_url = os.getenv('YOUTUBE_CALLBACK_URL', 'http://localhost:8080/youtube/callback')
        self.hub_url = 'https://pubsubhubbub.appspot.com/subscribe'
        self.topic_url_template = 'https://www.youtube.com/xml/feeds/videos.xml?channel_id={}'

        # Validate and set poll interval
        poll_interval = int(os.getenv('YOUTUBE_POLL_INTERVAL', '60'))
        if poll_interval < 10:
            logger.warning(f"Poll interval {poll_interval}s is too low, setting to 10s minimum")
            poll_interval = 10
        self.poll_interval = poll_interval

        # Validate and set server port
        server_port = int(os.getenv('TUBULAR_CALLBACK_PORT', '8080'))
        if not (1 <= server_port <= 65535):
            raise ValueError(f"Invalid port number: {server_port}. Must be between 1-65535")
        self.server_port = server_port

        # Bind address for callback server
        self.bind_address = os.getenv('CALLBACK_BIND_ADDRESS', '')

        # Redis configuration for heartbeat
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_password = os.getenv('REDIS_PASSWORD', '') or None
        self.redis_db = int(os.getenv('REDIS_DB', '0'))
        self.heartbeat_interval = int(os.getenv('TUBULAR_HEARTBEAT_INTERVAL', '30'))

        # Final safety checks
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY environment variable is required")
        if not self.channel_id:
            raise ValueError("YOUTUBE_CHANNEL_ID environment variable is required")


class YouTubeAPIClient:
    """Client for YouTube Data API v3 with rate limiting"""

    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.base_url = 'https://www.googleapis.com/youtube/v3'
        self.session = requests.Session()
        self.api_calls = deque(maxlen=100)  # Track last 100 API calls for rate limiting
        self.quota_exceeded = False

    def _check_rate_limit(self) -> None:
        """Simple rate limiting check"""
        now = datetime.now(timezone.utc)
        # Remove calls older than 1 minute
        while self.api_calls and (now - self.api_calls[0]) > timedelta(minutes=1):
            self.api_calls.popleft()

        # If more than 50 calls in last minute, wait
        if len(self.api_calls) >= 50:
            wait_time = 60 - (now - self.api_calls[0]).total_seconds()
            if wait_time > 0:
                logger.warning(f"Rate limit approaching, waiting {wait_time:.1f}s")
                time.sleep(wait_time)

    def _record_api_call(self) -> None:
        """Record an API call for rate limiting"""
        self.api_calls.append(datetime.now(timezone.utc))

    def _handle_api_response(self, response: requests.Response) -> Optional[Dict[str, Any]]:
        """Handle API response and check for quota errors"""
        try:
            data = response.json()
            if 'error' in data:
                error = data['error']
                if error.get('code') == 403 and 'quota' in str(error).lower():
                    self.quota_exceeded = True
                    logger.error("YouTube API quota exceeded!")
                return None
            return data
        except Exception as e:
            logger.error(f"Error parsing API response: {e}")
            return None

    def get_live_broadcasts(self) -> List[Dict[str, Any]]:
        """Get current live broadcasts for the channel"""
        if self.quota_exceeded:
            return []

        self._check_rate_limit()

        url = f'{self.base_url}/search'
        params = {
            'part': 'snippet',
            'channelId': self.config.channel_id,
            'eventType': 'live',
            'type': 'video',
            'key': self.config.api_key
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call()
            response.raise_for_status()

            data = self._handle_api_response(response)
            return data.get('items', []) if data else []
        except requests.RequestException as e:
            logger.error(f"Error fetching live broadcasts: {e}")
            return []

    def get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a video"""
        if self.quota_exceeded:
            return None

        self._check_rate_limit()

        url = f'{self.base_url}/videos'
        params = {
            'part': 'snippet,liveStreamingDetails,statistics',
            'id': video_id,
            'key': self.config.api_key
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call()
            response.raise_for_status()

            data = self._handle_api_response(response)
            if data:
                items = data.get('items', [])
                return items[0] if items else None
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching video details: {e}")
            return None

    def get_live_chat_messages(self, live_chat_id: str, page_token: Optional[str] = None) -> Dict[str, Any]:
        """Get live chat messages for a broadcast"""
        if self.quota_exceeded:
            return {}

        self._check_rate_limit()

        url = f'{self.base_url}/liveChat/messages'
        params = {
            'liveChatId': live_chat_id,
            'part': 'snippet,authorDetails',
            'key': self.config.api_key
        }

        if page_token:
            params['pageToken'] = page_token

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call()
            response.raise_for_status()

            data = self._handle_api_response(response)
            return data if data else {}
        except requests.RequestException as e:
            logger.error(f"Error fetching chat messages: {e}")
            return {}


class WebhookForwarder:
    """Forwards YouTube events as webhooks to the target server with retry logic"""

    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.session = requests.Session()
        self.failed_events = deque(maxlen=100)  # Store failed events for retry

    def forward_event(self, event_type: str, event_data: Dict[str, Any], retry_count: int = 0) -> bool:
        """Forward an event to the webhook endpoint with retry logic"""
        payload = {
            'event_type': event_type,
            'event': event_data,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'youtube'
        }

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Tubular-YouTube-Webhook-Forwarder/1.0'
        }

        # Add HMAC signature if secret is configured
        if self.config.webhook_secret:
            signature = self._generate_signature(json.dumps(payload))
            headers['X-Hub-Signature'] = f'sha256={signature}'

        try:
            logger.info(f"Forwarding {event_type} event to {self.config.webhook_url}")
            response = self.session.post(
                self.config.webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Successfully forwarded {event_type} event")
            return True
        except requests.RequestException as e:
            logger.error(f"Error forwarding webhook (attempt {retry_count + 1}): {e}")

            # Retry with exponential backoff (max 3 retries)
            if retry_count < 3:
                wait_time = 2 ** retry_count  # 1s, 2s, 4s
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self.forward_event(event_type, event_data, retry_count + 1)
            else:
                # Store failed event for potential later retry
                self.failed_events.append((event_type, event_data, datetime.now(timezone.utc)))
                logger.error(f"Failed to forward event after {retry_count + 1} attempts")
                return False

    def retry_failed_events(self) -> None:
        """Attempt to retry previously failed events"""
        if not self.failed_events:
            return

        logger.info(f"Retrying {len(self.failed_events)} failed events")
        failed_copy = list(self.failed_events)
        self.failed_events.clear()

        for event_type, event_data, timestamp in failed_copy:
            # Don't retry events older than 1 hour
            if (datetime.now(timezone.utc) - timestamp) > timedelta(hours=1):
                continue

            if not self.forward_event(event_type, event_data):
                self.failed_events.append((event_type, event_data, timestamp))

    def _generate_signature(self, payload: str) -> str:
        """Generate HMAC signature for webhook payload"""
        return hmac.new(
            self.config.webhook_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


class PubSubHubbubSubscriber:
    """Handles PubSubHubbub subscriptions for YouTube feeds"""

    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.session = requests.Session()

    def subscribe(self) -> bool:
        """Subscribe to YouTube channel feed updates"""
        topic_url = self.config.topic_url_template.format(self.config.channel_id)

        data = {
            'hub.callback': self.config.callback_url,
            'hub.mode': 'subscribe',
            'hub.topic': topic_url,
            'hub.verify': 'async',
            'hub.lease_seconds': 864000  # 10 days
        }

        try:
            logger.info(f"Subscribing to YouTube channel {self.config.channel_id}")
            response = self.session.post(self.config.hub_url, data=data, timeout=10)
            response.raise_for_status()
            logger.info("Subscription request sent successfully")
            return True
        except requests.RequestException as e:
            logger.error(f"Error subscribing to feed: {e}")
            return False

    def unsubscribe(self) -> bool:
        """Unsubscribe from YouTube channel feed updates"""
        topic_url = self.config.topic_url_template.format(self.config.channel_id)

        data = {
            'hub.callback': self.config.callback_url,
            'hub.mode': 'unsubscribe',
            'hub.topic': topic_url,
            'hub.verify': 'async'
        }

        try:
            logger.info(f"Unsubscribing from YouTube channel {self.config.channel_id}")
            response = self.session.post(self.config.hub_url, data=data, timeout=10)
            response.raise_for_status()
            logger.info("Unsubscribe request sent successfully")
            return True
        except requests.RequestException as e:
            logger.error(f"Error unsubscribing from feed: {e}")
            return False


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for PubSubHubbub callbacks"""

    forwarder: Optional[WebhookForwarder] = None
    api_client: Optional[YouTubeAPIClient] = None

    def do_GET(self) -> None:
        """Handle verification requests from PubSubHubbub hub"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'hub.challenge' in params:
            challenge = params['hub.challenge'][0]
            mode = params.get('hub.mode', [''])[0]

            logger.info(f"Received {mode} verification request - responding with challenge")

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(challenge.encode('utf-8'))
        else:
            self.send_response(200)
            self.end_headers()

    def do_POST(self) -> None:
        """Handle feed notifications from PubSubHubbub"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            # Parse Atom feed
            root = ET.fromstring(body)
            namespace = {'atom': 'http://www.w3.org/2005/Atom',
                        'yt': 'http://www.youtube.com/xml/schemas/2015'}

            entry = root.find('atom:entry', namespace)
            if entry is not None:
                video_id_elem = entry.find('yt:videoId', namespace)
                title_elem = entry.find('atom:title', namespace)
                published_elem = entry.find('atom:published', namespace)

                if video_id_elem is None or video_id_elem.text is None:
                    logger.warning("Video ID not found in feed")
                    self.send_response(200)
                    self.end_headers()
                    return

                video_id = video_id_elem.text
                title = title_elem.text if title_elem is not None else "Unknown"
                published = published_elem.text if published_elem is not None else ""

                logger.info(f"Received notification for video: {video_id} - {title}")

                # Get detailed video info to check if it's a live stream
                if self.api_client:
                    video_details = self.api_client.get_video_details(video_id)

                    if video_details and 'liveStreamingDetails' in video_details:
                        event_data = {
                            'video_id': video_id,
                            'title': title,
                            'published_at': published,
                            'channel_id': video_details['snippet']['channelId'],
                            'channel_title': video_details['snippet']['channelTitle'],
                            'live_streaming_details': video_details['liveStreamingDetails']
                        }

                        # Forward as live stream event
                        if self.forwarder:
                            self.forwarder.forward_event('youtube.live.update', event_data)

            self.send_response(200)
            self.end_headers()

        except ET.ParseError as e:
            logger.error(f"Error parsing feed XML: {e}")
            self.send_response(400)
            self.end_headers()
        except Exception as e:
            logger.error(f"Error processing notification: {e}")
            self.send_response(500)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger"""
        logger.debug(f"{self.address_string()} - {format % args}")


class YouTubeLiveMonitor:
    """Monitors YouTube live streams and forwards events"""

    def __init__(self, config: YouTubeConfig):
        self.config = config
        self.api_client = YouTubeAPIClient(config)
        self.forwarder = WebhookForwarder(config)
        self.subscriber = PubSubHubbubSubscriber(config)
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.chat_page_tokens: Dict[str, str] = {}
        self.running = False
        self.server: Optional[HTTPServer] = None
        self.state_file = 'tubular_state.pkl'
        self.stats = {
            'events_forwarded': 0,
            'api_calls': 0,
            'start_time': datetime.now(timezone.utc)
        }
        self.last_heartbeat = datetime.now(timezone.utc)

        # Initialize Redis client for heartbeat
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password,
                db=config.redis_db,
                decode_responses=True,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {config.redis_host}:{config.redis_port}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Heartbeat will be disabled.")
            self.redis_client = None

        # Load saved state
        self._load_state()

    def _save_state(self) -> None:
        """Save active streams state to file"""
        try:
            state = {
                'active_streams': self.active_streams,
                'chat_page_tokens': self.chat_page_tokens,
                'stats': self.stats
            }
            with open(self.state_file, 'wb') as f:
                pickle.dump(state, f)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def _load_state(self) -> None:
        """Load active streams state from file"""
        if not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, 'rb') as f:
                state = pickle.load(f)
            self.active_streams = state.get('active_streams', {})
            self.chat_page_tokens = state.get('chat_page_tokens', {})
            saved_stats = state.get('stats', {})
            if saved_stats:
                self.stats.update(saved_stats)
            logger.info(f"Loaded state: {len(self.active_streams)} active streams")
        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def _update_heartbeat(self) -> None:
        """Update heartbeat in Redis"""
        if not self.redis_client:
            return

        try:
            now = datetime.now(timezone.utc)
            uptime = now - self.stats['start_time']

            heartbeat_data = {
                'timestamp': now.isoformat(),
                'uptime_seconds': int(uptime.total_seconds()),
                'active_streams': len(self.active_streams),
                'events_forwarded': self.stats['events_forwarded'],
                'api_calls': self.stats['api_calls'],
                'status': 'running',
                'channel_id': self.config.channel_id
            }

            # Store in Redis with key 'tubular:heartbeat'
            # Set expiry to 3x heartbeat interval so stale data is cleared
            expiry = self.config.heartbeat_interval * 3
            self.redis_client.setex(
                'tubular:heartbeat',
                expiry,
                json.dumps(heartbeat_data)
            )

            self.last_heartbeat = now
            logger.debug(f"Heartbeat updated: {len(self.active_streams)} active streams")

        except Exception as e:
            logger.error(f"Error updating heartbeat: {e}")

    def start(self) -> None:
        """Start monitoring YouTube live streams"""
        logger.info("Starting YouTube live monitor")
        self.running = True
        self.stats['start_time'] = datetime.now(timezone.utc)

        # Send initial heartbeat
        self._update_heartbeat()

        # Subscribe to PubSubHubbub feed
        self.subscriber.subscribe()

        # Start callback server
        server_thread = threading.Thread(target=self._run_callback_server, daemon=True)
        server_thread.start()

        # Start polling loop
        self._polling_loop()

    def stop(self) -> None:
        """Stop monitoring"""
        logger.info("Stopping YouTube live monitor")
        self.running = False

        # Save state before stopping
        self._save_state()

        # Close server
        if self.server:
            self.server.server_close()

        self.subscriber.unsubscribe()

        # Print stats
        uptime = datetime.now(timezone.utc) - self.stats['start_time']
        logger.info(f"Stats - Uptime: {uptime}, Events: {self.stats['events_forwarded']}, API calls: {self.stats['api_calls']}")

    def _run_callback_server(self) -> None:
        """Run the HTTP server for PubSubHubbub callbacks"""
        CallbackHandler.forwarder = self.forwarder
        CallbackHandler.api_client = self.api_client

        self.server = HTTPServer((self.config.bind_address, self.config.server_port), CallbackHandler)
        self.server.timeout = 1.0  # Check running flag every second

        bind_info = self.config.bind_address or "all interfaces"
        logger.info(f"Callback server listening on {bind_info}:{self.config.server_port}")

        while self.running:
            self.server.handle_request()

        self.server.server_close()
        logger.info("Callback server stopped")

    def _polling_loop(self) -> None:
        """Poll YouTube API for live stream status"""
        retry_counter = 0

        while self.running:
            try:
                self._check_live_streams()

                # Update heartbeat if interval has passed
                now = datetime.now(timezone.utc)
                if (now - self.last_heartbeat).total_seconds() >= self.config.heartbeat_interval:
                    self._update_heartbeat()

                # Periodically retry failed webhooks
                if retry_counter % 10 == 0:  # Every 10 poll cycles
                    self.forwarder.retry_failed_events()

                # Save state periodically
                if retry_counter % 5 == 0:  # Every 5 poll cycles
                    self._save_state()

                retry_counter += 1
                time.sleep(self.config.poll_interval)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                time.sleep(self.config.poll_interval)

    def _check_live_streams(self) -> None:
        """Check for live streams and monitor their status"""
        logger.debug("Checking for live streams")

        broadcasts = self.api_client.get_live_broadcasts()
        self.stats['api_calls'] += 1
        current_stream_ids = set()

        for broadcast in broadcasts:
            video_id = broadcast['id']['videoId']
            current_stream_ids.add(video_id)

            # Get detailed info
            details = self.api_client.get_video_details(video_id)
            self.stats['api_calls'] += 1

            if not details:
                continue

            # Check if this is a new stream
            if video_id not in self.active_streams:
                logger.info(f"New live stream detected: {video_id}")
                self.active_streams[video_id] = details

                event_data = {
                    'video_id': video_id,
                    'title': details['snippet']['title'],
                    'description': details['snippet']['description'],
                    'channel_id': details['snippet']['channelId'],
                    'channel_title': details['snippet']['channelTitle'],
                    'started_at': details['liveStreamingDetails'].get('actualStartTime'),
                    'scheduled_start': details['liveStreamingDetails'].get('scheduledStartTime'),
                    'concurrent_viewers': details['liveStreamingDetails'].get('concurrentViewers', 0)
                }

                if self.forwarder.forward_event('youtube.live.started', event_data):
                    self.stats['events_forwarded'] += 1

                # Start monitoring chat if available
                if 'activeLiveChatId' in details['liveStreamingDetails']:
                    self._monitor_chat(video_id, details['liveStreamingDetails']['activeLiveChatId'])

            else:
                # Check for updates (viewer count changes, etc.)
                old_details = self.active_streams[video_id]
                old_viewers = old_details.get('liveStreamingDetails', {}).get('concurrentViewers', 0)
                new_viewers = details.get('liveStreamingDetails', {}).get('concurrentViewers', 0)

                # Only log significant viewer changes (>10% or >100 viewers)
                if old_viewers and new_viewers:
                    viewer_diff = abs(new_viewers - old_viewers)
                    pct_change = viewer_diff / old_viewers if old_viewers > 0 else 0

                    if viewer_diff > 100 or pct_change > 0.1:
                        logger.info(f"Viewer count changed for {video_id}: {old_viewers} -> {new_viewers}")

                        event_data = {
                            'video_id': video_id,
                            'concurrent_viewers': new_viewers,
                            'previous_viewers': old_viewers
                        }

                        if self.forwarder.forward_event('youtube.live.viewers_updated', event_data):
                            self.stats['events_forwarded'] += 1

                self.active_streams[video_id] = details

                # Monitor chat for active streams
                if 'activeLiveChatId' in details['liveStreamingDetails']:
                    self._monitor_chat(video_id, details['liveStreamingDetails']['activeLiveChatId'])

        # Check for ended streams
        ended_streams = set(self.active_streams.keys()) - current_stream_ids
        for video_id in ended_streams:
            logger.info(f"Live stream ended: {video_id}")
            details = self.active_streams[video_id]

            event_data = {
                'video_id': video_id,
                'title': details['snippet']['title'],
                'channel_id': details['snippet']['channelId'],
                'ended_at': datetime.now(timezone.utc).isoformat()
            }

            if self.forwarder.forward_event('youtube.live.ended', event_data):
                self.stats['events_forwarded'] += 1

            del self.active_streams[video_id]

            if video_id in self.chat_page_tokens:
                del self.chat_page_tokens[video_id]

    def _monitor_chat(self, video_id: str, live_chat_id: str) -> None:
        """Monitor live chat for a stream"""
        logger.debug(f"Monitoring chat for video {video_id}")

        page_token = self.chat_page_tokens.get(video_id)
        chat_data = self.api_client.get_live_chat_messages(live_chat_id, page_token)
        self.stats['api_calls'] += 1

        if not chat_data:
            return

        # Store next page token
        self.chat_page_tokens[video_id] = chat_data.get('nextPageToken', '')

        # Process new messages
        for item in chat_data.get('items', []):
            snippet = item['snippet']
            author = item['authorDetails']

            message_type = snippet['type']

            # Handle different message types
            if message_type == 'textMessageEvent':
                event_data = {
                    'video_id': video_id,
                    'message': snippet['textMessageDetails']['messageText'],
                    'author_name': author['displayName'],
                    'author_channel_id': author['channelId'],
                    'is_moderator': author.get('isChatModerator', False),
                    'is_sponsor': author.get('isChatSponsor', False),
                    'timestamp': snippet['publishedAt']
                }
                if self.forwarder.forward_event('youtube.chat.message', event_data):
                    self.stats['events_forwarded'] += 1

            elif message_type == 'superChatEvent':
                event_data = {
                    'video_id': video_id,
                    'message': snippet['superChatDetails'].get('userComment', ''),
                    'author_name': author['displayName'],
                    'author_channel_id': author['channelId'],
                    'amount': snippet['superChatDetails']['amountMicros'],
                    'currency': snippet['superChatDetails']['currency'],
                    'amount_display': snippet['superChatDetails']['amountDisplayString'],
                    'timestamp': snippet['publishedAt']
                }
                if self.forwarder.forward_event('youtube.chat.superchat', event_data):
                    self.stats['events_forwarded'] += 1

            elif message_type == 'newSponsorEvent':
                event_data = {
                    'video_id': video_id,
                    'author_name': author['displayName'],
                    'author_channel_id': author['channelId'],
                    'timestamp': snippet['publishedAt']
                }
                if self.forwarder.forward_event('youtube.chat.new_sponsor', event_data):
                    self.stats['events_forwarded'] += 1


def main() -> None:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='YouTube Live Events Webhook Forwarder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  YOUTUBE_API_KEY           YouTube Data API v3 key (required)
  YOUTUBE_CHANNEL_ID        YouTube channel ID to monitor (required)
  WEBHOOK_TARGET_URL        URL to forward events to (default: http://localhost/webhooks/youtube)
  WEBHOOK_SECRET            Secret for HMAC signing (optional)
  YOUTUBE_CALLBACK_URL      Public callback URL for PubSubHubbub (required for feed subscriptions)
  TUBULAR_CALLBACK_PORT      Port for callback server (default: 8080)
  YOUTUBE_POLL_INTERVAL     Polling interval in seconds (default: 60)
  CALLBACK_BIND_ADDRESS     Bind address for callback server (default: all interfaces)

Example:
  export YOUTUBE_API_KEY="your-api-key"
  export YOUTUBE_CHANNEL_ID="UCxxxxxxxxxxxxxx"
  export WEBHOOK_TARGET_URL="https://example.com/webhooks/youtube"
  export YOUTUBE_CALLBACK_URL="https://your-server.com:8080/youtube/callback"
  python tubular.py
        """
    )

    parser.add_argument('--validate', action='store_true',
                       help='Validate environment variables and exit')
    parser.add_argument('--subscribe-only', action='store_true',
                       help='Only subscribe to PubSubHubbub and exit')
    parser.add_argument('--unsubscribe', action='store_true',
                       help='Unsubscribe from PubSubHubbub and exit')

    args = parser.parse_args()

    # Try to load .env file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.join(script_dir, '.env')
    load_env_file(env_file)

    # Handle --validate flag
    if args.validate:
        is_valid, missing = validate_environment(show_details=True)
        sys.exit(0 if is_valid else 1)

    try:
        # Validate environment (will show brief error if validation fails)
        is_valid, missing = validate_environment(show_details=False)
        if not is_valid:
            logger.error(f"Environment validation failed. Missing: {', '.join(missing)}")
            logger.error("Run with --validate flag for detailed information")
            sys.exit(1)

        config = YouTubeConfig(validate=False)  # Already validated above

        if args.subscribe_only:
            subscriber = PubSubHubbubSubscriber(config)
            subscriber.subscribe()
            logger.info("Subscription request sent")
            return

        if args.unsubscribe:
            subscriber = PubSubHubbubSubscriber(config)
            subscriber.unsubscribe()
            logger.info("Unsubscribe request sent")
            return

        # Start monitoring
        monitor = YouTubeLiveMonitor(config)

        try:
            monitor.start()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            monitor.stop()

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
