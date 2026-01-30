"""HTTP server for PubSubHubbub callbacks and event triggering"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger('tubular.server')


class ExampleEventsTrigger:
    """Example class to trigger specific YouTube events manually"""

    def __init__(self, forwarder: 'WebhookForwarder'):
        self.forwarder = forwarder

    def trigger_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Trigger a specific event manually"""
        logger.info(f"Manually triggering event: {event_type}")
        self.forwarder.forward_event(event_type, event_data)

    def list_events(self) -> List[str]:
        """List available example events"""
        return [
            'youtube.live.start',
            'youtube.live.end',
            'youtube.chat.message',
            'youtube.superchat.received',
            'youtube.member.joined'
        ]

    def get_event_data_template(self, event_type: str) -> Dict[str, Any]:
        """Get a template for the specified event type"""
        templates = {
            'youtube.live.start': {
                'video_id': 'EXAMPLE_VIDEO_ID',
                'title': 'Example Live Stream',
                'published_at': datetime.now(timezone.utc).isoformat(),
                'channel_id': 'EXAMPLE_CHANNEL_ID',
                'channel_title': 'Example Channel'
            },
            'youtube.live.end': {
                'video_id': 'EXAMPLE_VIDEO_ID',
                'title': 'Example Live Stream',
                'ended_at': datetime.now(timezone.utc).isoformat(),
                'channel_id': 'EXAMPLE_CHANNEL_ID',
                'channel_title': 'Example Channel'
            },
            'youtube.chat.message': {
                'video_id': 'EXAMPLE_VIDEO_ID',
                'message_id': 'EXAMPLE_MESSAGE_ID',
                'author_name': 'Example User',
                'message_text': 'This is an example chat message.',
                'published_at': datetime.now(timezone.utc).isoformat()
            },
            'youtube.superchat.received': {
                'video_id': 'EXAMPLE_VIDEO_ID',
                'superchat_id': 'EXAMPLE_SUPERCHAT_ID',
                'author_name': 'Example User',
                'amount_display_string': '$5.00',
                'message_text': 'This is an example super chat message.',
                'published_at': datetime.now(timezone.utc).isoformat()
            },
            'youtube.member.joined': {
                'channel_id': 'EXAMPLE_CHANNEL_ID',
                'member_name': 'Example Member',
                'joined_at': datetime.now(timezone.utc).isoformat()
            }
        }
        return templates.get(event_type, {})


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for PubSubHubbub callbacks"""

    forwarder: Optional['WebhookForwarder'] = None
    api_client: Optional['YouTubeAPIClient'] = None
    example_events_trigger: Optional[ExampleEventsTrigger] = None

    def do_GET(self) -> None:
        """Handle verification requests from PubSubHubbub hub"""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if self.path == '/data/events':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                events = self.example_events_trigger.list_events() if self.example_events_trigger else []
                response = {'available_events': events}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

            if 'hub.challenge' in params:
                challenge = params['hub.challenge'][0]
                mode = params.get('hub.mode', [''])[0]

                logger.info(f"Received {mode} verification request - responding with challenge")

                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(challenge.encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found: " + self.path.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error in do_GET: {e}", exc_info=True)
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Internal Server Error")
            except Exception:
                pass  # Can't send response if headers already sent

    def do_POST(self) -> None:
        """Handle feed notifications from PubSubHubbub"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        if self.path.startswith('/example/'):
            event_name = self.path.split('/example/')[1]
            if self.example_events_trigger:
                event_data = self.example_events_trigger.get_event_data_template(event_name)
                if not event_data:
                    logger.error(f"Unknown example event: {event_name}")
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Unknown example event " + event_name.encode('utf-8'))
                    return
                self.example_events_trigger.trigger_event(event_name, event_data)
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Example event {event_name} triggered".encode('utf-8'))
            else:
                logger.error("ExampleEventsTrigger not configured")
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"ExampleEventsTrigger not configured")
            return

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
