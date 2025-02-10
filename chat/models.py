from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_online = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {'Online' if self.is_online else 'Offline'}"

    @receiver(post_save, sender=User)
    def create_user_status(sender, instance, created, **kwargs):
        if created:
            UserStatus.objects.create(user=instance)

class PrivateMessage(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='chat_files/', blank=True, null=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.sender.username} -> {self.recipient.username}: {self.content}"

    def delete_message(self):
        self.is_deleted = True
        self.save()

    @staticmethod
    def get_unread_count_for_dialog_with_user(sender, recipient):
        return PrivateMessage.objects.filter(sender_id=sender, recipient_id=recipient, read=False).count()

    @staticmethod
    def get_last_message_for_dialog(sender, recipient):
        return PrivateMessage.objects.filter(
            Q(sender_id=sender, recipient_id=recipient) | Q(sender_id=recipient, recipient_id=sender)) \
            .select_related('sender', 'recipient').first()

    def __str__(self):
        return str(self.pk)

    def save(self, *args, **kwargs):
        super(PrivateMessage, self).save(*args, **kwargs)


@receiver(post_save, sender=PrivateMessage)
def notify_new_message(sender, instance, created, **kwargs):
    """Send a WebSocket notification when a new message is received."""
    if created and not instance.is_read:
        channel_layer = get_channel_layer()
        group_name = f"notifications_{instance.recipient.username}"

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notify_new_message",
                "sender_username": instance.sender.username
            }
        )


