# core/firebase_client.py
import firebase_admin
from firebase_admin import credentials, messaging
import os
from django.conf import settings

# 确保只初始化一次
if not firebase_admin._apps:
    cred_path = os.path.join(settings.BASE_DIR, 'firebase-adminsdk.json')
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase Admin SDK 初始化成功")
    except Exception as e:
        print(f"⚠️ Firebase 初始化失败 (如果是开发环境暂无密钥可忽略): {e}")

def send_silent_push(fcm_token: str, payload: dict) -> bool:
    """
    发送高优先级的数据消息 (静默推送)
    注意：绝对不要在 message 中添加 notification 字段，否则会触发系统弹窗而不是静默唤醒！
    """
    if not fcm_token:
        return False

    # FCM 规定 data 里的所有 value 必须是字符串
    # 所以我们将整个 payload 序列化成一个 JSON 字符串，放到一个 data 键里
    import json
    message = messaging.Message(
        data={
            "nano_payload": json.dumps(payload)
        },
        token=fcm_token,
        # 安卓的特权：设置高优先级，穿透 Doze 深度休眠模式
        android=messaging.AndroidConfig(priority='high') 
    )

    try:
        response = messaging.send(message)
        print(f"🚀 FCM 静默指令已发出: {response}")
        return True
    except Exception as e:
        print(f"❌ FCM 发送失败: {e}")
        return False