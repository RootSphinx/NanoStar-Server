import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nanostar.settings')

# 1. 必须先初始化 Django（这一步会加载所有 Apps 和 Models）
django_asgi_app = get_asgi_application()

# 2. 只有在 Django 初始化完毕后，才能导入自定义的 WebSocket 路由
from ws_gateway.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})