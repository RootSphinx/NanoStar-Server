# ws_gateway/handlers.py
import time
from channels.db import database_sync_to_async
from django.core.cache import cache
from core.models import Device, AppConfig, Fingerprint
from .action_router import router

@router.register("DEVICE_HANDSHAKE")
async def handle_device_handshake(consumer, payload: dict):
    """处理协议 #1: 设备握手"""
    device_id = payload.get("device_id")
    fcm_token = payload.get("fcm_token")
    active_modules = payload.get("active_modules", [])
    
    if not device_id:
        return

    # 1. 记录设备标识到当前连接，方便断开时清理
    consumer.device_id = device_id

    # 2. 将设备状态绑定到 Redis 通道，方便 HTTP 接口反查发消息
    # 将设备的 channel_name 存到 Redis，有效期 60 秒（心跳会续期）
    cache.set(f"device_online:{device_id}", consumer.channel_name, timeout=60)

    # 3. 异步更新数据库 (MySQL)
    await update_device_db(device_id, fcm_token, active_modules)
    
    print(f"✅ 设备握手成功: {device_id} [通道: {consumer.channel_name}]")

@database_sync_to_async
def update_device_db(device_id, fcm_token, active_modules):
    """将数据库操作转为异步，防止阻塞 ASGI 主线程"""
    device, created = Device.objects.update_or_create(
        device_id=device_id,
        defaults={
            "fcm_token": fcm_token,
            "is_online": True,
            "active_modules": active_modules,
        }
    )
    return device

@router.register("REPORT_LOCATION")
async def handle_report_location(consumer, payload: dict):
    """处理协议 #3: 手机上报当前位置"""
    request_id = payload.get("request_id")
    lat = payload.get("latitude")
    lng = payload.get("longitude")
    
    if not request_id or lat is None or lng is None:
        return
        
    print(f"📍 收到手机位置返回: req={request_id}, 坐标={lat},{lng}")
    
    # 将结果写入 Redis，这样 API 视图那个死循环就能拿到数据了
    result_key = f"location_result:{request_id}"
    # 存入完整的 payload 数据，有效期 60 秒足够视图读取
    cache.set(result_key, payload, timeout=60)
    
    # 你同时也可以更新手机的 5 分钟常规缓存 (用于防抖)
    cache.set(f"device_location_cache:{consumer.device_id}", payload, timeout=300)


# ==================== 协议 #2: 配置同步 ====================

@database_sync_to_async
def get_latest_config():
    """从数据库读取当前配置（单例）"""
    return AppConfig.objects.first()


@router.register("REQUEST_SYNC_CONFIG")
async def handle_request_sync_config(consumer, payload: dict):
    """处理协议 #2 / #9: 客户端请求同步配置

    客户端握手后主动拉取最新配置。
    last_modified=0 表示本地无缓存，服务器全量下发。
    """
    await _do_sync_config(consumer, payload)


@router.register("REQUEST_CONFIG")
async def handle_request_config(consumer, payload: dict):
    """处理 DashboardViewModel 发起的配置请求（逻辑同 REQUEST_SYNC_CONFIG）"""
    await _do_sync_config(consumer, payload)


async def _do_sync_config(consumer, payload: dict):
    """配置同步核心逻辑

    注意：此处使用 consumer.send_direct() 直接回复客户端，
    而非 send_to_device_async()。后者走 Redis 通道层，
    在 WebSocket 消费者内部调用会导致不必要的 Redis 往返甚至超时死锁。
    send_to_device_async 保留给跨进程场景 (HTTP API → WebSocket)。
    """
    request_id = payload.get("request_id", "unknown")
    client_last_modified = payload.get("last_modified", 0)
    device_id = getattr(consumer, 'device_id', None)

    config = await get_latest_config()
    total_visitors = await _count_fingerprints()
    if not config:
        print(f"⚙️ 无配置记录，跳过同步 (req={request_id})")
        return

    server_updated_ms = config.updated_at_ms

    # 客户端无缓存 或 服务端配置更新 → 下发
    if client_last_modified == 0 or server_updated_ms > client_last_modified:
        update_payload = {
            "action": "UPDATE_CONFIG",
            "request_id": request_id,
            "data": {
                "is_tracking_enabled": config.is_tracking_enabled,
                "distance_threshold": config.distance_threshold,
                "show_total_visitors": config.show_total_visitors,
                "total_visitors": total_visitors,
                "show_past_comments": config.show_past_comments,
                "show_all_history": config.show_all_history,
            }
        }

        # 直接通过当前 WebSocket 连接回复，不走 Redis 通道层
        if hasattr(consumer, 'send_direct'):
            await consumer.send_direct(update_payload)
            print(f"⚙️ 配置已下发 → {device_id}: tracking={config.is_tracking_enabled}, "
                  f"threshold={config.distance_threshold}m")
        else:
            # 回退：HttpActionContext (离线回调) 场景，无法直接回复
            print(f"⚙️ 非 WS 上下文，无法下发配置 (req={request_id})")
    else:
        print(f"⚙️ 客户端配置已是最新 (req={request_id})")




@database_sync_to_async
def _count_fingerprints():
    """统计指纹总数（累计成功访客数）"""
    return Fingerprint.objects.count()

# ==================== ACK 占位 Handler ====================

@router.register("NOTIFICATION_ACK")
async def handle_notification_ack(consumer, payload: dict):
    """客户端确认收到通知（无需处理，仅记录）"""
    request_id = payload.get("request_id", "unknown")
    status = payload.get("status", "unknown")
    print(f"📨 通知 ACK: req={request_id}, status={status}")


@router.register("CONFIG_ACK")
async def handle_config_ack(consumer, payload: dict):
    """客户端确认收到配置更新（无需处理，仅记录）"""
    request_id = payload.get("request_id", "unknown")
    success = payload.get("success", False)
    print(f"⚙️ 配置 ACK: req={request_id}, success={success}")


@router.register("PULL_DATA_ACK")
async def handle_pull_data_ack(consumer, payload: dict):
    """客户端确认 PULL_DATA 完成（无需处理，仅记录）"""
    request_id = payload.get("request_id", "unknown")
    status = payload.get("status", "unknown")
    count = payload.get("synced_count", 0)
    print(f"📥 拉取数据 ACK: req={request_id}, status={status}, synced={count}")