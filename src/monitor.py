"""Main monitor class for YouTube live streams"""

import glob
import json
import logging
import os
import pickle
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer
from typing import Any, Dict, Optional

import redis

from .api_client import YouTubeAPIClient
from .config import YouTubeConfig
from .server import CallbackHandler, ExampleEventsTrigger
from .webhook import PubSubHubbubSubscriber, WebhookForwarder

logger = logging.getLogger("tubular.monitor")


class YouTubeLiveMonitor:
    """Monitors YouTube live streams and forwards events"""

    def __init__(self, config: YouTubeConfig):
        self.config = config

        # Initialize Redis client first (needed for both API client and heartbeat)
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password,
                db=config.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            self.redis_client.ping()
            logger.info(
                f"Connected to Redis at {config.redis_host}:{config.redis_port}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to connect to Redis: {e}. Quota persistence and heartbeat will be disabled."
            )
            self.redis_client = None

        # Initialize API client with Redis for quota persistence
        self.api_client = YouTubeAPIClient(config, self.redis_client)
        self.forwarder = WebhookForwarder(config)
        self.subscriber = PubSubHubbubSubscriber(config)
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.chat_page_tokens: Dict[str, str] = {}
        self.running = False
        self.server: Optional[HTTPServer] = None
        self.state_file = "tubular_state.pkl"
        self.stats = {
            "events_forwarded": 0,
            "api_calls": 0,
            "start_time": datetime.now(timezone.utc),
        }
        self.last_heartbeat = datetime.now(timezone.utc)
        self.last_broadcast_check = datetime.now(timezone.utc)
        self.last_log_cleanup = datetime.now(timezone.utc)

        # Load saved state
        self._load_state()

    def _save_state(self) -> None:
        """Save active streams state to file"""
        try:
            state = {
                "active_streams": self.active_streams,
                "chat_page_tokens": self.chat_page_tokens,
                "stats": self.stats,
            }
            with open(self.state_file, "wb") as f:
                pickle.dump(state, f)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def _load_state(self) -> None:
        """Load active streams state from file"""
        if not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, "rb") as f:
                state = pickle.load(f)
            self.active_streams = state.get("active_streams", {})
            self.chat_page_tokens = state.get("chat_page_tokens", {})
            saved_stats = state.get("stats", {})
            if saved_stats:
                self.stats.update(saved_stats)
            logger.info(f"Loaded state: {len(self.active_streams)} active streams")
        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def _cleanup_old_logs(self) -> None:
        """Clean up log files older than retention period"""
        log_file = os.environ.get("TUBULAR_LOG_FILE")
        if not log_file:
            return

        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            return

        max_age_days = int(os.environ.get("TUBULAR_LOG_RETENTION_DAYS", "7"))
        now = time.time()
        max_age_seconds = max_age_days * 86400

        log_patterns = [
            os.path.join(log_dir, "*.log"),
            os.path.join(log_dir, "*.log.*"),
        ]

        deleted_count = 0
        for pattern in log_patterns:
            for log_file_path in glob.glob(pattern):
                try:
                    file_age = now - os.path.getmtime(log_file_path)
                    if file_age > max_age_seconds:
                        os.remove(log_file_path)
                        logger.info(
                            f"Deleted old log file: {log_file_path} (age: {file_age / 86400:.1f} days)"
                        )
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete log file {log_file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old log file(s)")

    def _update_heartbeat(self) -> None:
        """Update heartbeat in Redis"""
        if not self.redis_client:
            return

        try:
            now = datetime.now(timezone.utc)
            uptime = now - self.stats["start_time"]

            heartbeat_data = {
                "timestamp": now.isoformat(),
                "uptime_seconds": int(uptime.total_seconds()),
                "active_streams": len(self.active_streams),
                "events_forwarded": self.stats["events_forwarded"],
                "api_calls": self.stats["api_calls"],
                "status": "running",
                "channel_id": self.config.channel_id,
                "quota": self.api_client.get_quota_info(),
            }

            # Store in Redis with key 'tubular:heartbeat'
            # Set expiry to 3x heartbeat interval so stale data is cleared
            expiry = self.config.heartbeat_interval * 3
            self.redis_client.setex(
                "tubular:heartbeat", expiry, json.dumps(heartbeat_data)
            )

            self.last_heartbeat = now
            logger.debug(
                f"Heartbeat updated: {len(self.active_streams)} active streams"
            )

        except Exception as e:
            logger.error(f"Error updating heartbeat: {e}")

    def start(self) -> None:
        """Start monitoring YouTube live streams"""
        logger.info("Starting YouTube live monitor")
        self.running = True
        self.stats["start_time"] = datetime.now(timezone.utc)

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
        uptime = datetime.now(timezone.utc) - self.stats["start_time"]
        logger.info(
            f"Stats - Uptime: {uptime}, Events: {self.stats['events_forwarded']}, API calls: {self.stats['api_calls']}"
        )

    def _run_callback_server(self) -> None:
        """Run the HTTP server for PubSubHubbub callbacks"""
        CallbackHandler.forwarder = self.forwarder
        CallbackHandler.api_client = self.api_client
        CallbackHandler.example_events_trigger = ExampleEventsTrigger(self.forwarder)

        self.server = HTTPServer(
            (self.config.bind_address, self.config.server_port), CallbackHandler
        )
        self.server.timeout = 1.0  # Check running flag every second

        bind_info = self.config.bind_address or "all interfaces"
        logger.info(
            f"Callback server listening on {bind_info}:{self.config.server_port}"
        )

        while self.running:
            self.server.handle_request()

        self.server.server_close()
        logger.info("Callback server stopped")

    def _polling_loop(self) -> None:
        """Poll YouTube API for live stream status"""
        retry_counter = 0

        while self.running:
            try:
                if self.config.disable_idle_polling and not self.active_streams:
                    logger.debug(
                        "Idle polling disabled; skipping API checks while no streams are active"
                    )
                else:
                    self._check_live_streams()

                # Update heartbeat if interval has passed
                now = datetime.now(timezone.utc)
                if (
                    now - self.last_heartbeat
                ).total_seconds() >= self.config.heartbeat_interval:
                    self._update_heartbeat()

                # Clean up old logs once per day
                if (now - self.last_log_cleanup).total_seconds() >= 86400:  # 24 hours
                    self._cleanup_old_logs()
                    self.last_log_cleanup = now

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
        now = datetime.now(timezone.utc)

        # Smart polling: If we have active streams, rely on PubSubHubbub for updates
        # and skip expensive API calls. Only check for NEW broadcasts if:
        # 1. No active streams (check frequently to catch stream starts quickly)
        # 2. Active streams but 5+ minutes since last check (catch additional streams)
        time_since_last_check = (now - self.last_broadcast_check).total_seconds()

        if self.active_streams and time_since_last_check < 300:  # 5 minutes
            logger.debug(
                f"Skipping broadcast check - monitoring {len(self.active_streams)} active stream(s)"
            )
            # Still update viewer counts for active streams (cheaper API call)
            for video_id in list(self.active_streams.keys()):
                details = self.api_client.get_video_details(video_id)
                self.stats["api_calls"] += 1

                if details and "liveStreamingDetails" in details:
                    old_details = self.active_streams[video_id]
                    old_viewers = old_details["liveStreamingDetails"].get(
                        "concurrentViewers", 0
                    )
                    new_viewers = details["liveStreamingDetails"].get(
                        "concurrentViewers", 0
                    )

                    # Update stored details
                    self.active_streams[video_id] = details

                    # Only send event if viewer count changed significantly (>10%)
                    if old_viewers > 0:
                        change_percent = abs(new_viewers - old_viewers) / old_viewers
                        if change_percent > 0.1:
                            event_data = {
                                "video_id": video_id,
                                "concurrent_viewers": new_viewers,
                                "title": details["snippet"]["title"],
                                "channel_id": details["snippet"]["channelId"],
                            }
                            if self.forwarder.forward_event(
                                "youtube.live.viewers_updated", event_data
                            ):
                                self.stats["events_forwarded"] += 1
                else:
                    # Stream ended - details no longer available
                    logger.info(
                        f"Stream {video_id} appears to have ended (no live details)"
                    )
            return

        # Perform full broadcast check
        logger.debug("Checking for live broadcasts")
        self.last_broadcast_check = now

        broadcasts = self.api_client.get_live_broadcasts()
        self.stats["api_calls"] += 1
        current_stream_ids = set()

        for broadcast in broadcasts:
            video_id = broadcast["id"]["videoId"]
            current_stream_ids.add(video_id)

            # Get detailed info
            details = self.api_client.get_video_details(video_id)
            self.stats["api_calls"] += 1

            if not details:
                continue

            # Check if this is a new stream
            if video_id not in self.active_streams:
                logger.info(f"New live stream detected: {video_id}")
                self.active_streams[video_id] = details

                event_data = {
                    "video_id": video_id,
                    "title": details["snippet"]["title"],
                    "description": details["snippet"]["description"],
                    "channel_id": details["snippet"]["channelId"],
                    "channel_title": details["snippet"]["channelTitle"],
                    "started_at": details["liveStreamingDetails"].get(
                        "actualStartTime"
                    ),
                    "scheduled_start": details["liveStreamingDetails"].get(
                        "scheduledStartTime"
                    ),
                    "concurrent_viewers": details["liveStreamingDetails"].get(
                        "concurrentViewers", 0
                    ),
                }

                if self.forwarder.forward_event("youtube.live.started", event_data):
                    self.stats["events_forwarded"] += 1

                # Start monitoring chat if available
                if "activeLiveChatId" in details["liveStreamingDetails"]:
                    self._monitor_chat(
                        video_id, details["liveStreamingDetails"]["activeLiveChatId"]
                    )

            else:
                # Check for updates (viewer count changes, etc.)
                old_details = self.active_streams[video_id]
                old_viewers = old_details.get("liveStreamingDetails", {}).get(
                    "concurrentViewers", 0
                )
                new_viewers = details.get("liveStreamingDetails", {}).get(
                    "concurrentViewers", 0
                )

                # Only log significant viewer changes (>10% or >100 viewers)
                if old_viewers and new_viewers:
                    viewer_diff = abs(new_viewers - old_viewers)
                    pct_change = viewer_diff / old_viewers if old_viewers > 0 else 0

                    if viewer_diff > 100 or pct_change > 0.1:
                        logger.info(
                            f"Viewer count changed for {video_id}: {old_viewers} -> {new_viewers}"
                        )

                        event_data = {
                            "video_id": video_id,
                            "concurrent_viewers": new_viewers,
                            "previous_viewers": old_viewers,
                        }

                        if self.forwarder.forward_event(
                            "youtube.live.viewers_updated", event_data
                        ):
                            self.stats["events_forwarded"] += 1

                self.active_streams[video_id] = details

                # Monitor chat for active streams
                if "activeLiveChatId" in details["liveStreamingDetails"]:
                    self._monitor_chat(
                        video_id, details["liveStreamingDetails"]["activeLiveChatId"]
                    )

        # Check for ended streams
        ended_streams = set(self.active_streams.keys()) - current_stream_ids
        for video_id in ended_streams:
            logger.info(f"Live stream ended: {video_id}")
            details = self.active_streams[video_id]

            event_data = {
                "video_id": video_id,
                "title": details["snippet"]["title"],
                "channel_id": details["snippet"]["channelId"],
                "ended_at": datetime.now(timezone.utc).isoformat(),
            }

            if self.forwarder.forward_event("youtube.live.ended", event_data):
                self.stats["events_forwarded"] += 1

            del self.active_streams[video_id]

            if video_id in self.chat_page_tokens:
                del self.chat_page_tokens[video_id]

    def _monitor_chat(self, video_id: str, live_chat_id: str) -> None:
        """Monitor live chat for a stream"""
        logger.debug(f"Monitoring chat for video {video_id}")

        page_token = self.chat_page_tokens.get(video_id)
        chat_data = self.api_client.get_live_chat_messages(live_chat_id, page_token)
        self.stats["api_calls"] += 1

        if not chat_data:
            return

        # Store next page token
        self.chat_page_tokens[video_id] = chat_data.get("nextPageToken", "")

        # Process new messages
        for item in chat_data.get("items", []):
            snippet = item["snippet"]
            author = item["authorDetails"]

            message_type = snippet["type"]

            # Handle different message types
            if message_type == "textMessageEvent":
                event_data = {
                    "video_id": video_id,
                    "message": snippet["textMessageDetails"]["messageText"],
                    "author_name": author["displayName"],
                    "author_channel_id": author["channelId"],
                    "is_moderator": author.get("isChatModerator", False),
                    "is_sponsor": author.get("isChatSponsor", False),
                    "timestamp": snippet["publishedAt"],
                }
                if self.forwarder.forward_event("youtube.chat.message", event_data):
                    self.stats["events_forwarded"] += 1

            elif message_type == "superChatEvent":
                event_data = {
                    "video_id": video_id,
                    "message": snippet["superChatDetails"].get("userComment", ""),
                    "author_name": author["displayName"],
                    "author_channel_id": author["channelId"],
                    "amount": snippet["superChatDetails"]["amountMicros"],
                    "currency": snippet["superChatDetails"]["currency"],
                    "amount_display": snippet["superChatDetails"][
                        "amountDisplayString"
                    ],
                    "timestamp": snippet["publishedAt"],
                }
                if self.forwarder.forward_event("youtube.chat.superchat", event_data):
                    self.stats["events_forwarded"] += 1

            elif message_type == "newSponsorEvent":
                event_data = {
                    "video_id": video_id,
                    "author_name": author["displayName"],
                    "author_channel_id": author["channelId"],
                    "timestamp": snippet["publishedAt"],
                }
                if self.forwarder.forward_event("youtube.chat.new_sponsor", event_data):
                    self.stats["events_forwarded"] += 1
