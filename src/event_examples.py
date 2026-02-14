"""Example event templates for webhook testing and documentation"""

from datetime import datetime, timezone
from typing import Any, Dict


def get_event_examples() -> Dict[str, Dict[str, Any]]:
    """
    Get template examples for all supported event types.

    Timestamps are generated dynamically to always reflect current time.

    Returns:
        Dictionary mapping event type names to example event data
    """
    now = datetime.now(timezone.utc).isoformat()

    return {
        "youtube.live.started": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "title": "Example Live Stream",
            "description": "Example stream description",
            "channel_id": "EXAMPLE_CHANNEL_ID",
            "channel_title": "Example Channel",
            "started_at": now,
            "scheduled_start": now,
            "concurrent_viewers": 42,
        },
        "youtube.live.update": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "title": "Example Live Stream",
            "published_at": now,
            "channel_id": "EXAMPLE_CHANNEL_ID",
            "channel_title": "Example Channel",
            "live_streaming_details": {
                "actualStartTime": now,
                "scheduledStartTime": now,
                "concurrentViewers": 42,
            },
            "pubsub_data": {
                "@attributes": {
                    "xmlns": "http://www.w3.org/2005/Atom",
                    "xmlns:yt": "http://www.youtube.com/xml/schemas/2015",
                },
                "title": "Example Channel Feed",
                "id": "yt:channel:EXAMPLE_CHANNEL_ID",
                "entry": {
                    "id": "yt:video:EXAMPLE_VIDEO_ID",
                    "yt:videoId": "EXAMPLE_VIDEO_ID",
                    "title": "Example Live Stream",
                    "published": now,
                },
            },
        },
        "youtube.live.viewers_updated": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "concurrent_viewers": 1337,
            "previous_viewers": 1200,
            "title": "Example Live Stream",
            "channel_id": "EXAMPLE_CHANNEL_ID",
        },
        "youtube.live.ended": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "title": "Example Live Stream",
            "channel_id": "EXAMPLE_CHANNEL_ID",
            "ended_at": now,
        },
        "youtube.chat.message": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "message": "This is an example chat message.",
            "author_name": "Example User",
            "author_channel_id": "EXAMPLE_AUTHOR_CHANNEL_ID",
            "is_moderator": False,
            "is_sponsor": False,
            "timestamp": now,
        },
        "youtube.chat.superchat": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "message": "Great stream!",
            "author_name": "Generous Viewer",
            "author_channel_id": "EXAMPLE_AUTHOR_CHANNEL_ID",
            "amount": 5000000,
            "currency": "USD",
            "amount_display": "$5.00",
            "tier": 4,
            "timestamp": now,
        },
        "youtube.chat.new_sponsor": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "author_name": "New Member",
            "author_channel_id": "EXAMPLE_AUTHOR_CHANNEL_ID",
            "member_level_name": "Level 1 Member",
            "is_upgrade": False,
            "timestamp": now,
        },
        "youtube.chat.supersticker": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "author_name": "Sticker Sender",
            "author_channel_id": "EXAMPLE_AUTHOR_CHANNEL_ID",
            "sticker_id": "STICKER_ID_12345",
            "sticker_alt_text": "A thumbs up gesture",
            "sticker_language": "en",
            "amount": 5000000,
            "currency": "USD",
            "amount_display": "$5.00",
            "tier": 4,
            "timestamp": now,
        },
        "youtube.chat.user_banned": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "banned_user_name": "Banned User",
            "banned_user_channel_id": "EXAMPLE_BANNED_CHANNEL_ID",
            "ban_type": "temporary",
            "ban_duration_seconds": 3600,
            "timestamp": now,
        },
        "youtube.chat.message_deleted": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "deleted_message_id": "EXAMPLE_MESSAGE_ID",
            "timestamp": now,
        },
        "youtube.chat.poll": {
            "video_id": "EXAMPLE_VIDEO_ID",
            "author_name": "Poll Creator",
            "author_channel_id": "EXAMPLE_AUTHOR_CHANNEL_ID",
            "question": "What should I play next?",
            "options": [
                {"text": "Game A", "tally": "42"},
                {"text": "Game B", "tally": "38"},
                {"text": "Game C", "tally": "25"},
            ],
            "status": "active",
            "timestamp": now,
        },
    }
