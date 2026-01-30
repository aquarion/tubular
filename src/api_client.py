"""YouTube API client with quota tracking and rate limiting"""

import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("tubular.api_client")


class YouTubeAPIClient:
    """Client for YouTube Data API v3 with rate limiting"""

    def __init__(
        self, config: "YouTubeConfig", redis_client: Optional["redis.Redis"] = None
    ):
        self.config = config
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.session = requests.Session()
        self.api_calls = deque(maxlen=100)  # Track last 100 API calls for rate limiting
        self.quota_exceeded = False
        self.redis_client = redis_client

        # Quota tracking
        self.quota_used_today = 0
        self.quota_reset_date = datetime.now(timezone.utc).date()
        self.daily_quota_limit = 10000  # YouTube API default daily quota

        # Quota costs per API operation
        self.quota_costs = {"search": 100, "videos": 1, "liveChatMessages": 5}

        # Load quota state from Redis if available
        self._load_quota_from_redis()

    def _load_quota_from_redis(self) -> None:
        """Load quota state from Redis"""
        if not self.redis_client:
            return

        try:
            quota_data = self.redis_client.get("tubular:quota")
            if quota_data:
                data = json.loads(quota_data)
                stored_date = datetime.fromisoformat(data["reset_date"]).date()
                today = datetime.now(timezone.utc).date()

                # Only restore if it's the same day
                if stored_date == today:
                    self.quota_used_today = data.get("used", 0)
                    self.quota_reset_date = stored_date
                    logger.info(
                        f"Restored quota state from Redis: {self.quota_used_today}/{self.daily_quota_limit} used"
                    )
                else:
                    logger.info(f"Quota data from previous day, starting fresh")
        except Exception as e:
            logger.error(f"Error loading quota from Redis: {e}")

    def _save_quota_to_redis(self) -> None:
        """Save quota state to Redis"""
        if not self.redis_client:
            return

        try:
            quota_data = {
                "used": self.quota_used_today,
                "limit": self.daily_quota_limit,
                "remaining": self.daily_quota_limit - self.quota_used_today,
                "reset_date": self.quota_reset_date.isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            # Store with 48 hour expiry (gives us buffer beyond daily reset)
            self.redis_client.setex(
                "tubular:quota", 172800, json.dumps(quota_data)  # 48 hours in seconds
            )
        except Exception as e:
            logger.error(f"Error saving quota to Redis: {e}")

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

    def _record_api_call(self, operation: str = "unknown") -> None:
        """Record an API call for rate limiting and quota tracking"""
        self.api_calls.append(datetime.now(timezone.utc))

        # Check if we need to reset daily quota
        today = datetime.now(timezone.utc).date()
        if today != self.quota_reset_date:
            logger.info(
                f"Daily quota reset. Previous day usage: {self.quota_used_today}/{self.daily_quota_limit}"
            )
            self.quota_used_today = 0
            self.quota_reset_date = today

        # Track quota usage
        cost = self.quota_costs.get(operation, 1)
        self.quota_used_today += cost

        # Save to Redis
        self._save_quota_to_redis()

        # Warn at various thresholds
        usage_percent = (self.quota_used_today / self.daily_quota_limit) * 100
        if (
            usage_percent >= 90
            and (self.quota_used_today - cost) / self.daily_quota_limit * 100 < 90
        ):
            logger.warning(
                f"⚠️  YouTube API quota at {usage_percent:.1f}% ({self.quota_used_today}/{self.daily_quota_limit})"
            )
        elif (
            usage_percent >= 75
            and (self.quota_used_today - cost) / self.daily_quota_limit * 100 < 75
        ):
            logger.warning(
                f"YouTube API quota at {usage_percent:.1f}% ({self.quota_used_today}/{self.daily_quota_limit})"
            )
        elif (
            usage_percent >= 50
            and (self.quota_used_today - cost) / self.daily_quota_limit * 100 < 50
        ):
            logger.info(
                f"YouTube API quota at {usage_percent:.1f}% ({self.quota_used_today}/{self.daily_quota_limit})"
            )

    def get_quota_info(self) -> Dict[str, Any]:
        """Get current quota usage information"""
        usage_percent = (self.quota_used_today / self.daily_quota_limit) * 100
        return {
            "used": self.quota_used_today,
            "limit": self.daily_quota_limit,
            "remaining": self.daily_quota_limit - self.quota_used_today,
            "usage_percent": round(usage_percent, 2),
            "reset_date": self.quota_reset_date.isoformat(),
            "exceeded": self.quota_exceeded,
        }

    def _handle_api_response(
        self, response: requests.Response
    ) -> Optional[Dict[str, Any]]:
        """Handle API response and check for quota errors"""
        try:
            data = response.json()
            if "error" in data:
                error = data["error"]
                error_code = error.get("code")
                error_message = error.get("message", "")

                # Check for quota exceeded errors
                if error_code == 403:
                    # Check error reasons
                    errors = error.get("errors", [])
                    for err in errors:
                        reason = err.get("reason", "")
                        if reason in ["quotaExceeded", "dailyLimitExceeded"]:
                            self.quota_exceeded = True
                            logger.error(f"YouTube API quota exceeded: {error_message}")
                            return None

                # Log other API errors
                logger.error(f"YouTube API error {error_code}: {error_message}")
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

        url = f"{self.base_url}/search"
        params = {
            "part": "snippet",
            "channelId": self.config.channel_id,
            "eventType": "live",
            "type": "video",
            "key": self.config.api_key,
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call("search")

            data = self._handle_api_response(response)
            return data.get("items", []) if data else []
        except requests.RequestException as e:
            logger.error(f"Error fetching live broadcasts: {e}")
            return []

    def get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a video"""
        if self.quota_exceeded:
            return None

        self._check_rate_limit()

        url = f"{self.base_url}/videos"
        params = {
            "part": "snippet,liveStreamingDetails,statistics",
            "id": video_id,
            "key": self.config.api_key,
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call("videos")

            data = self._handle_api_response(response)
            if data:
                items = data.get("items", [])
                return items[0] if items else None
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching video details: {e}")
            return None

    def get_live_chat_messages(
        self, live_chat_id: str, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get live chat messages for a broadcast"""
        if self.quota_exceeded:
            return {}

        self._check_rate_limit()

        url = f"{self.base_url}/liveChat/messages"
        params = {
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "key": self.config.api_key,
        }

        if page_token:
            params["pageToken"] = page_token

        try:
            response = self.session.get(url, params=params, timeout=10)
            self._record_api_call("liveChatMessages")

            data = self._handle_api_response(response)
            return data if data else {}
        except requests.RequestException as e:
            logger.error(f"Error fetching chat messages: {e}")
            return {}
