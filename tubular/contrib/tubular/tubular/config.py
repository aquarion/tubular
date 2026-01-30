"""Configuration management for tubular"""

import os
import logging
from typing import List, Tuple

logger = logging.getLogger('tubular.config')


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
        'WEBHOOK_TARGET_URL': 'Target URL to forward webhooks to (e.g., https://example.com/webhooks/youtube)',
        'YOUTUBE_CALLBACK_URL': 'Public callback URL for PubSubHubbub (must be internet-accessible)'
    }

    # Optional variables with descriptions and defaults
    optional_vars = {
        'WEBHOOK_SECRET': 'Secret key for signing webhooks (recommended for security)',
        'YOUTUBE_POLL_INTERVAL': 'Seconds between poll checks (default: 60, minimum: 10)',
        'TUBULAR_CALLBACK_PORT': 'Port for callback HTTP server (default: 8080)',
        'CALLBACK_BIND_ADDRESS': 'Address to bind callback server to (default: empty = all interfaces)',
        'REDIS_HOST': 'Redis host for heartbeat monitoring (default: localhost)',
        'REDIS_PORT': 'Redis port (default: 6379)',
        'REDIS_PASSWORD': 'Redis password if required (optional)',
        'REDIS_DB': 'Redis database number (default: 0)',
        'TUBULAR_HEARTBEAT_INTERVAL': 'Seconds between heartbeat updates (default: 30)'
    }

    missing_required = []
    has_all_required = True

    if show_details:
        print("\n=== Environment Variable Validation ===\n")
        print("REQUIRED Variables:")

    for var, description in required_vars.items():
        value = os.getenv(var)
        status = "✓" if value else "✗"

        if show_details:
            status_str = f"{status} {var}"
            if value:
                # Mask sensitive values
                if 'SECRET' in var or 'KEY' in var or 'PASSWORD' in var:
                    display_value = f"{'*' * min(len(value), 20)}"
                else:
                    display_value = value[:50] + ('...' if len(value) > 50 else '')
                status_str += f" = {display_value}"
            else:
                status_str += " (MISSING)"

            print(f"  {status_str}")
            print(f"    → {description}")

        if not value:
            missing_required.append(var)
            has_all_required = False

    if show_details:
        print("\nOPTIONAL Variables:")

        for var, description in optional_vars.items():
            value = os.getenv(var)
            status = "✓" if value else "○"

            status_str = f"{status} {var}"
            if value:
                # Mask sensitive values
                if 'SECRET' in var or 'KEY' in var or 'PASSWORD' in var:
                    display_value = f"{'*' * min(len(value), 20)}"
                else:
                    display_value = value[:50] + ('...' if len(value) > 50 else '')
                status_str += f" = {display_value}"
            else:
                status_str += " (using default)"

            print(f"  {status_str}")
            print(f"    → {description}")

        print()
        if has_all_required:
            print("✓ All required environment variables are set!")
        else:
            print(f"✗ Missing {len(missing_required)} required variable(s)")

    return has_all_required, missing_required


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
