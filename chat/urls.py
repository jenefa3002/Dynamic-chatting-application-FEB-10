from django.urls import path
from . import views
from .views import  users_view, LoginRedirectView

urlpatterns = [
    path('users/', views.user_list_view, name='user_list'),
    path('chat/<str:username>/', views.chat_view, name='chat'),
    path('', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('chat/', views.chat_view, name='chat'),
    path('users/', users_view, name='users'),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('chat/fetch-messages/<str:username>/', views.fetch_new_messages, name='fetch_new_messages'),
    path('login_redirect/', LoginRedirectView.as_view(), name='login_redirect'),
    path('screenshare/<str:room_name>/', views.screen_share, name='screen_share'),
]
