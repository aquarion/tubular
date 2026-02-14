#!/usr/bin/env python3
"""
YouTube Live Events Webhook Forwarder - Main Entry Point

This script subscribes to YouTube live events using the YouTube Data API v3
and forwards them as webhooks to another server (like the stream-delta Laravel app).
"""

import argparse
import glob
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

# Configure logging with rotation
handlers = [logging.StreamHandler(sys.stdout)]

if os.environ.get("TUBULAR_LOG_FILE"):
    log_file = os.environ["TUBULAR_LOG_FILE"]
    # 10MB max file size, keep 5 backup files
    max_bytes = int(os.environ.get("TUBULAR_LOG_MAX_BYTES", 10 * 1024 * 1024))
    backup_count = int(os.environ.get("TUBULAR_LOG_BACKUP_COUNT", 5))

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    handlers.append(file_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=handlers,
)
logger = logging.getLogger("tubular")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tubular.config import YouTubeConfig, load_env_file, validate_environment
from tubular.monitor import YouTubeLiveMonitor
from tubular.webhook import PubSubHubbubSubscriber


def cleanup_old_logs(log_dir: str, max_age_days: int = 7) -> None:
    """
    Delete log files older than the specified number of days

    Args:
        log_dir: Directory containing log files
        max_age_days: Maximum age of log files in days (default: 7)
    """
    if not os.path.exists(log_dir):
        return

    now = time.time()
    max_age_seconds = max_age_days * 86400  # days to seconds

    # Find all log files (*.log and *.log.*)
    log_patterns = [os.path.join(log_dir, "*.log"), os.path.join(log_dir, "*.log.*")]

    deleted_count = 0
    for pattern in log_patterns:
        for log_file in glob.glob(pattern):
            try:
                file_age = now - os.path.getmtime(log_file)
                if file_age > max_age_seconds:
                    os.remove(log_file)
                    logger.info(
                        f"Deleted old log file: {log_file} (age: {file_age / 86400:.1f} days)"
                    )
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete log file {log_file}: {e}")

    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old log file(s)")


def main() -> None:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="YouTube Live Events Webhook Forwarder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  YOUTUBE_API_KEY           YouTube Data API v3 key (required)
  YOUTUBE_CHANNEL_ID        YouTube channel ID to monitor (required)
  TUBULAR_WEBHOOK_URL        URL to forward events to (default: http://localhost/webhooks/youtube)
  WEBHOOK_SECRET            Secret for HMAC signing (optional)
  TUBULAR_CALLBACK_URL      Public callback URL for PubSubHubbub (required for feed subscriptions)
  TUBULAR_CALLBACK_PORT     Port for callback server (default: 8080)
  YOUTUBE_POLL_INTERVAL     Polling interval in seconds (default: 60)
  CALLBACK_BIND_ADDRESS     Bind address for callback server (default: all interfaces)
  REDIS_HOST                Redis host for heartbeat monitoring (default: localhost)
  REDIS_PORT                Redis port (default: 6379)
  REDIS_USERNAME            Redis username for ACL (optional, requires Redis 6+)
  REDIS_PASSWORD            Redis password if required (optional)
  REDIS_DB                  Redis database number (default: 0)
  TUBULAR_HEARTBEAT_INTERVAL Heartbeat update interval in seconds (default: 30)
  TUBULAR_LOG_FILE          Path to log file (optional, logs to stdout if not set)
  TUBULAR_LOG_MAX_BYTES     Max log file size in bytes before rotation (default: 10485760 = 10MB)
  TUBULAR_LOG_BACKUP_COUNT  Number of backup log files to keep (default: 5)
  TUBULAR_LOG_RETENTION_DAYS Number of days to keep old log files (default: 7)

Example:
  export YOUTUBE_API_KEY="your-api-key"
  export YOUTUBE_CHANNEL_ID="UCxxxxxxxxxxxxxx"
  export TUBULAR_WEBHOOK_URL="https://example.com/webhooks/youtube"
  export TUBULAR_CALLBACK_URL="https://your-server.com:8080/youtube/callback"
  python -m tubular
        """,
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate environment variables and exit",
    )
    parser.add_argument(
        "--subscribe-only",
        action="store_true",
        help="Only subscribe to PubSubHubbub and exit",
    )
    parser.add_argument(
        "--unsubscribe",
        action="store_true",
        help="Unsubscribe from PubSubHubbub and exit",
    )

    args = parser.parse_args()

    # Try to load .env file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.join(script_dir, "../.env")
    load_env_file(env_file)

    # Clean up old log files
    log_retention_days = int(os.environ.get("TUBULAR_LOG_RETENTION_DAYS", "7"))
    if os.environ.get("TUBULAR_LOG_FILE"):
        log_dir = os.path.dirname(os.environ["TUBULAR_LOG_FILE"])
        cleanup_old_logs(log_dir, log_retention_days)

    # Handle --validate flag
    if args.validate:
        is_valid, missing = validate_environment(show_details=True)
        sys.exit(0 if is_valid else 1)

    try:
        # Validate environment (will show brief error if validation fails)
        is_valid, missing = validate_environment(show_details=False)
        if not is_valid:
            logger.error(
                f"Environment validation failed. Missing: {', '.join(missing)}"
            )
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


if __name__ == "__main__":
    main()
