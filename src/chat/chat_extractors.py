"""Extractors for different YouTube Live Chat message types"""

from typing import Any, Dict

from ..core import constants


def extract_text_message(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from textMessageEvent"""
    return {
        "video_id": video_id,
        "message": snippet["textMessageDetails"]["messageText"],
        "author_name": author["displayName"],
        "author_channel_id": author["channelId"],
        "is_moderator": author.get("isChatModerator", False),
        "is_sponsor": author.get("isChatSponsor", False),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_superchat(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from superChatEvent"""
    super_chat_details = snippet.get("superChatDetails", {})
    return {
        "video_id": video_id,
        "message": super_chat_details.get("userComment", ""),
        "author_name": author["displayName"],
        "author_channel_id": author["channelId"],
        "amount": super_chat_details.get("amountMicros"),
        "currency": super_chat_details.get("currency"),
        "amount_display": super_chat_details.get("amountDisplayString"),
        "tier": super_chat_details.get("tier"),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_new_sponsor(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from newSponsorEvent"""
    new_sponsor_details = snippet.get("newSponsorDetails", {})
    return {
        "video_id": video_id,
        "author_name": author["displayName"],
        "author_channel_id": author["channelId"],
        "member_level_name": new_sponsor_details.get("memberLevelName"),
        "is_upgrade": new_sponsor_details.get("isUpgrade", False),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_supersticker(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from superStickerEvent"""
    sticker_details = snippet.get("superStickerDetails", {})
    sticker_metadata = sticker_details.get("superStickerMetadata", {})
    return {
        "video_id": video_id,
        "author_name": author["displayName"],
        "author_channel_id": author["channelId"],
        "sticker_id": sticker_metadata.get("stickerId"),
        "sticker_alt_text": sticker_metadata.get("altText"),
        "sticker_language": sticker_metadata.get("language"),
        "amount": sticker_details.get("amountMicros"),
        "currency": sticker_details.get("currency"),
        "amount_display": sticker_details.get("amountDisplayString"),
        "tier": sticker_details.get("tier"),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_user_banned(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from userBannedEvent"""
    banned_details = snippet.get("userBannedDetails", {})
    banned_user_details = banned_details.get("bannedUserDetails", {})
    return {
        "video_id": video_id,
        "banned_user_name": banned_user_details.get("displayName"),
        "banned_user_channel_id": banned_user_details.get("channelId"),
        "ban_type": banned_details.get("banType"),
        "ban_duration_seconds": banned_details.get("banDurationSeconds"),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_message_deleted(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from messageDeletedEvent"""
    return {
        "video_id": video_id,
        "deleted_message_id": snippet["messageDeletedDetails"].get("deletedMessageId"),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


def extract_poll(
    video_id: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract data from pollEvent"""
    poll_details = snippet.get("pollDetails", {})
    poll_metadata = poll_details.get("metadata", {})

    # Convert options format from API structure
    options = []
    api_options = poll_metadata.get("options", [])
    if isinstance(api_options, list):
        for option in api_options:
            options.append(
                {
                    "text": option.get("optionText"),
                    "tally": option.get("tally"),
                }
            )
    elif isinstance(api_options, dict):
        # Single option case
        options.append(
            {
                "text": api_options.get("optionText"),
                "tally": api_options.get("tally"),
            }
        )

    return {
        "video_id": video_id,
        "author_name": author["displayName"],
        "author_channel_id": author["channelId"],
        "question": poll_metadata.get("questionText"),
        "options": options,
        "status": poll_metadata.get("status"),
        "timestamp": snippet["publishedAt"],
        "api_data": {"snippet": snippet, "authorDetails": author},
    }


# Mapping of message types to extractor functions
EXTRACTORS = {
    constants.MESSAGE_TYPE_TEXT: extract_text_message,
    constants.MESSAGE_TYPE_SUPERCHAT: extract_superchat,
    constants.MESSAGE_TYPE_NEW_SPONSOR: extract_new_sponsor,
    constants.MESSAGE_TYPE_SUPERSTICKER: extract_supersticker,
    constants.MESSAGE_TYPE_USER_BANNED: extract_user_banned,
    constants.MESSAGE_TYPE_MESSAGE_DELETED: extract_message_deleted,
    constants.MESSAGE_TYPE_POLL: extract_poll,
}


def extract_chat_message(
    video_id: str, message_type: str, snippet: Dict[str, Any], author: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract chat message data based on message type.

    Args:
        video_id: YouTube video ID
        message_type: Type of message (e.g., "textMessageEvent")
        snippet: Message snippet from API
        author: Author details from API

    Returns:
        Dictionary with extracted event data, or empty dict if type not recognized
    """
    extractor = EXTRACTORS.get(message_type)
    if extractor:
        return extractor(video_id, snippet, author)
    return {}
