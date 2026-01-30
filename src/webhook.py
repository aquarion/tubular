"""Webhook forwarding and PubSubHubbub subscription handling"""

import hashlib
import hmac
import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import requests

logger = logging.getLogger("tubular.webhook")


class WebhookForwarder:
    """Forwards YouTube events as webhooks to the target server with retry logic"""

    def __init__(self, config: "YouTubeConfig"):
        self.config = config
        self.session = requests.Session()
        self.failed_events = deque(maxlen=100)  # Store failed events for retry

    def forward_event(
        self, event_type: str, event_data: Dict[str, Any], retry_count: int = 0
    ) -> bool:
        """Forward an event to the webhook endpoint with retry logic"""
        payload = {
            "event_type": event_type,
            "event": event_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "youtube",
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Tubular-YouTube-Webhook-Forwarder/1.0",
        }

        # Add HMAC signature if secret is configured
        if self.config.webhook_secret:
            signature = self._generate_signature(json.dumps(payload))
            headers["X-Hub-Signature"] = f"sha256={signature}"

        try:
            logger.info(f"Forwarding {event_type} event to {self.config.webhook_url}")
            response = self.session.post(
                self.config.webhook_url, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            logger.info(f"Successfully forwarded {event_type} event")
            return True
        except requests.RequestException as e:
            logger.error(f"Error forwarding webhook (attempt {retry_count + 1}): {e}")

            # Retry with exponential backoff (max 3 retries)
            if retry_count < 3:
                wait_time = 2**retry_count  # 1s, 2s, 4s
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self.forward_event(event_type, event_data, retry_count + 1)
            else:
                # Store failed event for potential later retry
                self.failed_events.append(
                    (event_type, event_data, datetime.now(timezone.utc))
                )
                logger.error(
                    f"Failed to forward event after {retry_count + 1} attempts"
                )
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
            self.config.webhook_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class PubSubHubbubSubscriber:
    """Handles PubSubHubbub subscriptions for YouTube feeds"""

    def __init__(self, config: "YouTubeConfig"):
        self.config = config
        self.session = requests.Session()

    def subscribe(self) -> bool:
        """Subscribe to YouTube channel feed updates"""
        topic_url = self.config.topic_url_template.format(self.config.channel_id)

        data = {
            "hub.callback": self.config.callback_url,
            "hub.mode": "subscribe",
            "hub.topic": topic_url,
            "hub.verify": "async",
            "hub.lease_seconds": 864000,  # 10 days
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
            "hub.callback": self.config.callback_url,
            "hub.mode": "unsubscribe",
            "hub.topic": topic_url,
            "hub.verify": "async",
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
