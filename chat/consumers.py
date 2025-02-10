import json
from collections import defaultdict

from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async, async_to_sync
from django.contrib.auth.models import User
import logging
from .models import PrivateMessage, UserStatus

logger = logging.getLogger(__name__)

class PrivateChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        logger.info(f"Attempting WebSocket connection: {self.channel_name}")
        try:
            self.sender_username = self.scope['url_route']['kwargs']['sender_username']
            self.recipient_username = self.scope['url_route']['kwargs']['recipient_username']
            self.room_name = f"chat_{min(self.sender_username, self.recipient_username)}_{max(self.sender_username, self.recipient_username)}"
            self.room_group_name = f"chat_{self.room_name}"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket connected to room: {self.room_group_name}")
            logger.info(f"Connected to channel : {self.channel_name}")
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected: {self.channel_name}")
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message', None)
            file_url = text_data_json.get('file_url')

            if not message and not file_url:
                await self.send(text_data=json.dumps({'error': 'No message provided'}))
                return

            if message is None:
                await self.send(text_data=json.dumps({'error': 'No message provided'}))
                return

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'file_url': file_url,
                    'sender': self.sender_username,
                    'recipient': self.recipient_username,
                }
            )

            await self.save_message(self.sender_username, self.recipient_username, message, file_url)
            logger.info(f"Message received: {message}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @sync_to_async
    def save_message(self, sender_username, recipient_username, content, file_url):
        sender_user = User.objects.get(username=sender_username)
        recipient_user = User.objects.get(username=recipient_username)
        message = PrivateMessage.objects.create(
            sender=sender_user,
            recipient=recipient_user,
            content=content,
            file=file_url
        )
        return message

    async def user_online(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'username': event['username'],
            'status': 'online',
        }))

    async def user_offline(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'username': event['username'],
            'status': 'offline',
        }))


    async def send_notification(self, recipient_username, message):
        recipient = await sync_to_async(User.objects.get)(username=recipient_username)
        if recipient.is_authenticated:
            await self.channel_layer.group_send(
                f"notifications_{recipient_username}",
                {
                    'type': 'notification_message',
                    'message': message,
                    'sender': self.sender_username
                }
            )

class NotificationConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.group_name = f"notifications_{self.user.username}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            await self.send_unread_messages_per_sender()

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        sender_username = content.get("sender_username")

        if content.get("type") == "mark_read" and sender_username:
            await self.mark_messages_as_read(sender_username)
            await self.send_unread_messages_per_sender()

    @database_sync_to_async
    def mark_messages_as_read(self, sender_username):
        """Mark all messages from a sender as read"""
        PrivateMessage.objects.filter(
            recipient=self.user,
            sender__username=sender_username,
            is_read=False
        ).update(is_read=True)

    @database_sync_to_async
    def get_unread_messages_per_sender(self):
        """Get unread message counts per sender"""
        unread_messages = PrivateMessage.objects.filter(recipient=self.user, is_read=False)
        unread_counts = defaultdict(int)

        for message in unread_messages:
            unread_counts[message.sender.username] += 1

        return unread_counts

    async def send_unread_messages_per_sender(self):
        """Send unread messages for each sender to the user"""
        unread_counts = await self.get_unread_messages_per_sender()
        await self.send_json({"type": "unread_count", "unread_counts": unread_counts})

    async def notify_new_message(self, event):
        """Real-time update when a new message arrives"""
        await self.send_unread_messages_per_sender()


class ScreenShareConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'screenshare'
        logger.info("Attempting WebSocket connection")

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()
        logger.info("Websocket connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info("Websocket disconnected for Screen Shareing")

    async def receive(self, text_data):
        message = json.loads(text_data)
        logger.info("Reciving signal..")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'signal_message',
                'message': message
            }
        )

    async def signal_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps(message))


class OnlineStatusConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            await self.set_online_status(self.user, True)  # Mark online
            await self.channel_layer.group_add("online_users", self.channel_name)
            await self.accept()

            # Send the updated online user list to all users
            await self.broadcast_all_users_status()

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.set_online_status(self.user, False)  # Mark offline
            await self.channel_layer.group_discard("online_users", self.channel_name)

            # Send the updated online user list to all users
            await self.broadcast_all_users_status()

    async def broadcast_all_users_status(self):
        """Send the online status of all users to everyone in the group."""
        online_users = await self.get_online_users()
        await self.channel_layer.group_send(
            "online_users",
            {
                "type": "update_online_users",
                "online_users": online_users
            }
        )

    async def update_online_users(self, event):
        """Receive an updated list of online users and send to the frontend."""
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def set_online_status(self, user, status):
        """Update user status in the database."""
        user_status, _ = UserStatus.objects.get_or_create(user=user)
        user_status.is_online = status
        if status:
            user_status.last_seen = timezone.now()  # Update last seen time
        user_status.save()

    @database_sync_to_async
    def get_online_users(self):
        """Retrieve all currently online users."""
        return list(UserStatus.objects.filter(is_online=True).values("user__id", "user__username"))
