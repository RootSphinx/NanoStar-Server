# ws_gateway/command_sender.py
import asyncio
import logging
from channels.layers import get_channel_layer
from django.core.cache import cache
from channels.db import database_sync_to_async
from core.models import Device
from core.firebase_client import send_silent_push

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_device_fcm_token(device_id):
    try:
        device = Device.objects.get(device_id=device_id)
        return device.fcm_token
    except Device.DoesNotExist:
        return None


async def send_to_device_async(device_id: str, payload: dict) -> bool:
    """智能双通道下发引擎

    优先通过 WebSocket 下发，失败或离线时降级为 FCM 静默推送。
    """
    # 1. 尝试通道 A：WebSocket
    channel_name = cache.get(f"device_online:{device_id}")

    if channel_name:
        channel_layer = get_channel_layer()
        try:
            await channel_layer.send(
                channel_name,
                {"type": "send_command_to_client", "payload": payload}
            )
            logger.info(f"⚡ [WS通道] 指令 {payload.get('action')} 已发送给 {device_id}")
            return True
        except Exception as e:
            logger.error(f"WS发送失败，尝试回退 FCM: {e}")

    # 2. 尝试通道 B：FCM 静默推送
    logger.info(f"💤 [降级FCM] 准备唤醒离线设备 {device_id}")
    fcm_token = await get_device_fcm_token(device_id)

    if not fcm_token:
        logger.error("设备无 FCM Token，彻底失联")
        return False

    success = await asyncio.to_thread(send_silent_push, fcm_token, payload)
    return success


def send_to_device_sync(device_id: str, payload: dict) -> bool:
    """为同步视图提供的同步发送包装器"""
    from asgiref.sync import async_to_sync
    return async_to_sync(send_to_device_async)(device_id, payload)