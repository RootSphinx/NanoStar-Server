# ws_gateway/consumers.py
"""
SignalR JSON Hub Protocol 兼容的 WebSocket Consumer。

C# 客户端 (Microsoft.AspNetCore.SignalR.Client) 使用的协议:
  握手帧:  {"protocol":"json","version":1}␞
  调用帧:  {"type":1,"target":"RespondToServer","arguments":[{...}]}␞
  心跳帧:  {"type":6}␞
  ␞ = \\x1e (ASCII Record Separator, 0x1E)

服务端响应:
  握手应答: {}␞
  下发帧:   {"type":1,"target":"ReceiveCommand","arguments":["<json>"]}␞
"""
import json
import logging
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.cache import cache

from .action_router import router
import ws_gateway.handlers

logger = logging.getLogger("ws_gateway")

# SignalR JSON Protocol 消息类型
MSG_HANDSHAKE = "handshake"   # 伪类型
MSG_INVOCATION = 1            # Hub 方法调用
MSG_PING = 6                  # 心跳
RECORD_SEP = "\x1e"           # 每条消息的帧分隔符


@database_sync_to_async
def _set_device_offline(device_id):
    from core.models import Device
    Device.objects.filter(device_id=device_id).update(is_online=False)


class AppConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_id = None
        self._handshake_done = False       # SignalR 握手是否完成
        self._client_ip = "?"

    # ==================================================================
    #  连接生命周期
    # ==================================================================

    async def connect(self):
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        self._client_ip = self.scope.get('client', ('?', 0))[0]

        expected = getattr(settings, 'APP_SECRET_TOKEN', 'nanostar2026')
        if token != expected:
            logger.warning(f"⛔ [WS] 鉴权失败 ip={self._client_ip} token={token}")
            await self.close(code=4003)
            return

        await self.accept()
        logger.info(f"🔗 [WS] 已接受 ip={self._client_ip}  等待 SignalR 握手...")

    async def disconnect(self, close_code):
        if self.device_id:
            cache.delete(f"device_online:{self.device_id}")
            await _set_device_offline(self.device_id)
            logger.warning(f"❌ [WS] 设备离线 device={self.device_id} "
                           f"ip={self._client_ip} code={close_code}")
        else:
            logger.info(f"🔌 [WS] 断开 ip={self._client_ip} code={close_code} "
                        f"(设备未绑定)")

    # ==================================================================
    #  接收：SignalR 帧 → 业务 Payload
    # ==================================================================

    async def receive(self, text_data):
        """收到的原始 WebSocket 文本 (SignalR 协议帧)"""
        raw = text_data
        raw_preview = raw[:300] if raw else "(empty)"

        # --- 1. 剥离帧分隔符 ---
        text = raw.rstrip(RECORD_SEP)
        if not text:
            logger.debug(f"📩 [WS] 空帧 ip={self._client_ip}")
            return

        # --- 2. JSON 解析 ---
        try:
            frame = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"💥 [WS] JSON 解析失败 ip={self._client_ip} "
                         f"raw={raw_preview} err={e}")
            await self._reply_error(f"Invalid JSON: {e}")
            return

        logger.debug(f"📩 [WS] RECV ip={self._client_ip} "
                     f"frame={json.dumps(frame, ensure_ascii=False)[:200]}")

        # --- 3. SignalR 握手帧 (只发生一次，连接后第一条消息) ---
        if not self._handshake_done:
            protocol = frame.get("protocol")
            version = frame.get("version")
            if protocol == "json" and version == 1:
                # 回应握手完成帧: 空对象 + 分隔符
                await self.send(text_data="{}" + RECORD_SEP)
                self._handshake_done = True
                logger.info(f"🤝 [WS] SignalR 握手完成 ip={self._client_ip}")
                return
            else:
                logger.error(f"💥 [WS] 不支持的握手协议 ip={self._client_ip} "
                             f"frame={frame}")
                await self.close(code=4000)
                return

        # --- 4. 心跳帧 ---
        msg_type = frame.get("type")
        if msg_type == MSG_PING:
            logger.debug(f"💓 [WS] Ping ip={self._client_ip}")
            if self.device_id:
                cache.set(f"device_online:{self.device_id}",
                          self.channel_name, timeout=60)
            # 回应 Ping，否则客户端 ServerTimeout 到期会主动断开
            await self.send(text_data=json.dumps({"type": MSG_PING}) + RECORD_SEP)
            return

        # --- 5. 调用帧: type=1, target=RespondToServer ---
        if msg_type == MSG_INVOCATION:
            target = frame.get("target", "?")
            args = frame.get("arguments", [])
            invocation_id = frame.get("invocationId", "")

            if target == "RespondToServer" and args:
                payload = args[0]  # arguments[0] 就是业务 JSON
                action = payload.get("action", "?")
                logger.info(f"📩 [WS] RespondToServer action={action} "
                            f"ip={self._client_ip} device={self.device_id or '(unbound)'}")
                await router.route_message(self, payload)
                # 回复 SignalR 完成帧，防止客户端 InvokeAsync 阻塞等待
                if invocation_id:
                    completion = json.dumps({
                        "type": 3,
                        "invocationId": invocation_id
                    }) + RECORD_SEP
                    await self.send(text_data=completion)
            else:
                logger.warning(f"⚠️ [WS] 未知 HubMethod target={target} "
                               f"ip={self._client_ip}")
            return

        # --- 6. 未知帧 ---
        logger.warning(f"⚠️ [WS] 未识别帧 type={msg_type} ip={self._client_ip} "
                       f"frame={json.dumps(frame, ensure_ascii=False)[:150]}")

    # ==================================================================
    #  发送：业务 Payload → SignalR 帧
    # ==================================================================

    async def send_command_to_client(self, event):
        """Channel Layer 回调 —— 跨进程发送入口（HTTP API → WebSocket）"""
        payload = event.get("payload", {})
        await self.send_direct(payload)

    # ==================================================================
    #  发送工具
    # ==================================================================

    async def send_direct(self, payload: dict):
        """直接发送 SignalR 帧给客户端（不走 Redis 通道层）

        用于 WebSocket 消费者内部的 handler 回复场景。
        跨进程场景 (HTTP API → WebSocket) 则通过 Channel Layer
        触发 send_command_to_client → send_direct。
        """
        action = payload.get("action", "?")
        device = self.device_id or "(unbound)"

        payload_json = json.dumps(payload, ensure_ascii=False)

        frame = json.dumps({
            "type": MSG_INVOCATION,
            "target": "ReceiveCommand",
            "arguments": [payload_json]
        }, ensure_ascii=False)

        message = frame + RECORD_SEP
        await self.send(text_data=message)
        logger.info(f"📤 [WS] → {device} action={action} "
                    f"size={len(message)}B")

    async def _reply_error(self, message: str):
        """向客户端发送一个错误帧"""
        await self.send_direct({"error": message})