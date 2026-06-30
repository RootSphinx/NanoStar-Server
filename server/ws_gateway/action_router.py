# ws_gateway/action_router.py
import logging

logger = logging.getLogger(__name__)

class ActionRouter:
    """WebSocket 动作分发器"""
    def __init__(self):
        self._routes = {}

    def register(self, action_name):
        """装饰器：注册一个处理函数到指定的 action 上"""
        def decorator(func):
            self._routes[action_name] = func
            return func
        return decorator

    async def route_message(self, consumer, payload: dict):
        """执行路由分发"""
        action = payload.get("action")
        if not action:
            logger.warning("收到没有 action 字段的消息")
            return

        handler = self._routes.get(action)
        if not handler:
            logger.warning(f"未知的 Action: {action}")
            return

        try:
            # 将 consumer 实例（代表当前连接）和数据包传给处理函数
            await handler(consumer, payload)
        except Exception as e:
            logger.error(f"处理 Action {action} 时发生错误: {e}")

# 实例化全局路由器
router = ActionRouter()