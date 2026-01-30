#!/usr/bin/env python3
"""
YouTube Live Events Webhook Forwarder - Main Entry Point

This script subscribes to YouTube live events using the YouTube Data API v3
and forwards them as webhooks to another server (like the stream-delta Laravel app).
"""

import os
import sys
import logging
import argparse

# Determine log directory - prefer Docker mount, fall back to app root storage/logs
if os.path.exists('/var/log/tubular'):
    # Running in Docker with mounted volume
    log_file = '/var/log/tubular/tubular.log'
else:
    # Running standalone - use app root storage/logs
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.abspath(os.path.join(script_dir, '../../../'))
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

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tubular.config import load_env_file, validate_environment, YouTubeConfig
from tubular.webhook import PubSubHubbubSubscriber
from tubular.monitor import YouTubeLiveMonitor


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
  TUBULAR_CALLBACK_PORT     Port for callback server (default: 8080)
  YOUTUBE_POLL_INTERVAL     Polling interval in seconds (default: 60)
  CALLBACK_BIND_ADDRESS     Bind address for callback server (default: all interfaces)

Example:
  export YOUTUBE_API_KEY="your-api-key"
  export YOUTUBE_CHANNEL_ID="UCxxxxxxxxxxxxxx"
  export WEBHOOK_TARGET_URL="https://example.com/webhooks/youtube"
  export YOUTUBE_CALLBACK_URL="https://your-server.com:8080/youtube/callback"
  python -m tubular
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
    env_file = os.path.join(script_dir, '../.env')
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
