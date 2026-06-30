# ws_gateway/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 匹配 ws://domain/ws/app/
    re_path(r'^ws/app/$', consumers.AppConsumer.as_asgi()),
]