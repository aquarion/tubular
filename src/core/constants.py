"""Application constants and configuration defaults"""

# YouTube API Configuration
YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_DAILY_QUOTA_LIMIT = 10000

# API Operation Costs (quota units)
YOUTUBE_API_QUOTA_COSTS = {
    "search": 100,
    "videos": 1,
    "liveChatMessages": 5,
}

# Redis Configuration
REDIS_DEFAULT_HOST = "localhost"
REDIS_DEFAULT_PORT = 6379
REDIS_DEFAULT_DB = 0

# Redis Key Names
REDIS_KEY_QUOTA = "tubular:quota"
REDIS_KEY_HEARTBEAT = "tubular:heartbeat"

# Redis Key Expiry Time (seconds)
REDIS_QUOTA_EXPIRY = 172800  # 48 hours

# Polling Configuration
YOUTUBE_DEFAULT_POLL_INTERVAL = 60  # seconds
YOUTUBE_MIN_POLL_INTERVAL = 10  # seconds
BROADCAST_CHECK_INTERVAL = (
    300  # 5 minutes - skip if within this time and have active streams
)

# Viewer Count Thresholds (for triggering viewers_updated event)
VIEWER_COUNT_CHANGE_THRESHOLD_PERCENT = 0.1  # 10%
VIEWER_COUNT_CHANGE_THRESHOLD_ABSOLUTE = 100  # viewers

# Webhook Configuration
WEBHOOK_REQUEST_TIMEOUT = (3.0, 5.0)  # (connect, read) timeout in seconds
WEBHOOK_RETRY_MAX_ATTEMPTS = 3
WEBHOOK_RETRY_BACKOFF = 2  # exponential backoff base (1s, 2s, 4s)

# HTTP Server Configuration
DEFAULT_CALLBACK_PORT = 8080
DEFAULT_PAGINATED_RESULTS = 50

# API Request Configuration
API_REQUEST_TIMEOUT = 10  # seconds
RATE_LIMIT_CHECK_PERIOD = 60  # 1 minute
RATE_LIMIT_MAX_CALLS_PER_MINUTE = 50

# Chat/Message Configuration
HEARTBEAT_INTERVAL_DEFAULT = 30  # seconds

# Message Type Constants (from YouTube API)
MESSAGE_TYPE_TEXT = "textMessageEvent"
MESSAGE_TYPE_SUPERCHAT = "superChatEvent"
MESSAGE_TYPE_SUPERSTICKER = "superStickerEvent"
MESSAGE_TYPE_NEW_SPONSOR = "newSponsorEvent"
MESSAGE_TYPE_USER_BANNED = "userBannedEvent"
MESSAGE_TYPE_MESSAGE_DELETED = "messageDeletedEvent"
MESSAGE_TYPE_POLL = "pollEvent"

# Event Type Constants (Tubular internal)
EVENT_TYPE_LIVE_STARTED = "youtube.live.started"
EVENT_TYPE_LIVE_UPDATE = "youtube.live.update"
EVENT_TYPE_LIVE_VIEWERS_UPDATED = "youtube.live.viewers_updated"
EVENT_TYPE_LIVE_ENDED = "youtube.live.ended"
EVENT_TYPE_CHAT_MESSAGE = "youtube.chat.message"
EVENT_TYPE_CHAT_SUPERCHAT = "youtube.chat.superchat"
EVENT_TYPE_CHAT_SUPERSTICKER = "youtube.chat.supersticker"
EVENT_TYPE_CHAT_NEW_SPONSOR = "youtube.chat.new_sponsor"
EVENT_TYPE_CHAT_USER_BANNED = "youtube.chat.user_banned"
EVENT_TYPE_CHAT_MESSAGE_DELETED = "youtube.chat.message_deleted"
EVENT_TYPE_CHAT_POLL = "youtube.chat.poll"

# Supported Event Types (for listing/validation)
SUPPORTED_EVENT_TYPES = [
    EVENT_TYPE_LIVE_STARTED,
    EVENT_TYPE_LIVE_UPDATE,
    EVENT_TYPE_LIVE_VIEWERS_UPDATED,
    EVENT_TYPE_LIVE_ENDED,
    EVENT_TYPE_CHAT_MESSAGE,
    EVENT_TYPE_CHAT_SUPERCHAT,
    EVENT_TYPE_CHAT_NEW_SPONSOR,
    EVENT_TYPE_CHAT_SUPERSTICKER,
    EVENT_TYPE_CHAT_USER_BANNED,
    EVENT_TYPE_CHAT_MESSAGE_DELETED,
    EVENT_TYPE_CHAT_POLL,
]

# Feature Flags / Configuration
LOG_RETENTION_DAYS = 7

# Webhook Header Configuration
WEBHOOK_USER_AGENT = "Tubular-YouTube-Webhook-Forwarder/1.0"
WEBHOOK_CONTENT_TYPE = "application/json"

# PubSubHubbub Configuration
PUBSUB_HUB_URL = "https://pubsubhubbub.appspot.com"
PUBSUB_SUBSCRIPTION_LEASE_SECONDS = 864000  # 10 days
