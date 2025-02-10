from django.contrib import admin
from chat.models import PrivateMessage, UserStatus

admin.site.register(PrivateMessage)
admin.site.register(UserStatus)
# Register your models here.
