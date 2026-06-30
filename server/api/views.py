# server/api/views.py
import asyncio
import uuid
import time
import json
import urllib.request
import urllib.parse
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.conf import settings
from channels.db import database_sync_to_async
from geopy.distance import distance as geopy_distance

from core.models import Device, AppConfig, VisitorRecord
from ws_gateway.command_sender import send_to_device_async
from ws_gateway.action_router import router


@database_sync_to_async
def _get_online_device_id():
    """获取最近在线的设备 ID（单用户场景取第一个在线设备）"""
    device = Device.objects.filter(is_online=True).order_by('-last_seen').first()
    return device.device_id if device else None

def _get_client_ip(request):
    """从代理头或 REMOTE_ADDR 获取客户端真实 IP

    优先级: X-Forwarded-For > X-Real-IP > REMOTE_ADDR
    过滤掉 Docker 内部地址 (127.x, 172.17-31.x, 10.x) 及空值。
    """
    def _is_public_or_usable(ip):
        if not ip:
            return False
        ip = ip.strip()
        # 过滤 loopback / Docker 网桥 / 私有 A 类
        if ip.startswith('127.') or ip == '::1' or ip == '0.0.0.0':
            return False
        # Docker 默认网桥 172.17.0.0/16 — 仅过滤 172.17 ~ 172.31
        if ip.startswith('172.'):
            try:
                second = int(ip.split('.')[1])
                if 17 <= second <= 31:
                    return False
            except (IndexError, ValueError):
                pass
        # 私有 C 类一般不是容器网关，放行 (192.168.x 通常为真实客户端)
        return True

    # 1) X-Forwarded-For 最左侧 IP
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    for candidate in xff.split(','):
        ip = candidate.strip()
        if _is_public_or_usable(ip):
            return ip

    # 2) X-Real-IP
    xri = request.META.get('HTTP_X_REAL_IP', '')
    if _is_public_or_usable(xri):
        return xri.strip()

    # 3) REMOTE_ADDR（可能为 Docker 网关，兜底返回不作过滤）
    remote = request.META.get('REMOTE_ADDR', '')
    return remote.strip() if remote else ''


def _resolve_device_address(lat, lng):
    """调用腾讯地图逆地理编码 API 获取坐标地址描述"""
    key = getattr(settings, 'TENCENT_MAP_API_KEY', '')
    if not key:
        return ''
    endpoint = getattr(settings, 'TENCENT_MAP_GEOCODER_URL', 'https://apis.map.qq.com/ws/geocoder/v1/')
    url = f"{endpoint}?key={key}&location={lat},{lng}&get_poi=1"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('status') == 0 and data.get('result'):
            result = data['result']
            return result.get('formatted_addresses', {}).get('recommend') or result.get('address', '')
    except Exception as e:
        print(f"⚠️ 逆地理编码失败: {e}")
    return ''


def index_page(request):
    """渲染前端网页"""
    return render(request, 'index.html', {
        'ip_api_endpoint': getattr(settings, 'IP_API_ENDPOINT', ''),
        'ip_api_key': getattr(settings, 'IP_API_KEY', ''),
    })

# ==================== 数据库辅助 (异步包装) ====================

@database_sync_to_async
def _get_latest_config():
    """读取最新 AppConfig"""
    try:
        return AppConfig.objects.latest('version_id')
    except AppConfig.DoesNotExist:
        return None


@database_sync_to_async
def _create_visitor_record(request_id, ip_address, distance, timestamp, is_success, comment, module,
                           visitor_latitude, visitor_longitude, visitor_address,
                           device_latitude, device_longitude, device_address):
    """创建访客记录（遇 request_id 唯一约束冲突则跳过）"""
    try:
        VisitorRecord.objects.create(
            request_id=request_id,
            ip_address=ip_address if ip_address else None,
            distance=distance,
            timestamp=timestamp,
            is_success=is_success,
            comment=comment,
            module=module,
            visitor_latitude=visitor_latitude,
            visitor_longitude=visitor_longitude,
            visitor_address=visitor_address,
            device_latitude=device_latitude,
            device_longitude=device_longitude,
            device_address=device_address,
        )
    except Exception as e:
        print(f"⚠️ 创建访客记录失败: {e}")  # 唯一约束冲突，静默跳过


@database_sync_to_async
def _update_visitor_comment(request_id, comment):
    """更新访客记录的 comment 字段，同时刷新 timestamp 以便客户端同步"""
    import time
    VisitorRecord.objects.filter(request_id=request_id).update(
        comment=comment, timestamp=int(time.time() * 1000))


@database_sync_to_async
def _get_visitor_records_since(module: str, last_sync: int):
    """查询 timestamp > last_sync 且 module 匹配的记录，按时间升序"""
    return list(
        VisitorRecord.objects
        .filter(timestamp__gt=last_sync, module=module)
        .order_by('timestamp')
    )

async def verify_visitor_click(request):
    """处理前端验证请求 (真实双通道通讯完整版)"""
    if request.method != 'POST':
        return JsonResponse({"status": "error", "msg": "Bad method"}, status=405)

    try:
        # 1. 提取前端传来的访客坐标（即使用户拒绝授权，这里也是 None）
        data = json.loads(request.body)
        visitor_lat = data.get('latitude')
        visitor_lng = data.get('longitude')
        location_source = data.get('location_source', 'gps')  # 'gps' 或 'ip_fallback'
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "msg": "Invalid JSON"}, status=400)

    # 2. 生成唯一的请求追踪 ID
    request_id = f"req_loc_{uuid.uuid4().hex[:8]}"
    
    # 3. 构造下发给手机的指令载荷
    payload = {
        "action": "GET_LOCATION",
        "request_id": request_id,
        "visitor_lat": visitor_lat,
        "visitor_lng": visitor_lng
    }
    
    # 4. 动态查找在线设备并发送索要位置的指令
    online_device = await _get_online_device_id()
    if not online_device:
        return JsonResponse({"status": "fail", "msg": "机主设备离线，请稍后再试"})

    sent_success = await send_to_device_async(online_device, payload)

    if not sent_success:
        return JsonResponse({"status": "fail", "msg": "机主设备离线，请稍后再试"})
        
    # 5. 指令已发出，将请求挂起，循环等待手机把结果写进 Redis
    timeout_seconds = 10
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        result_key = f"location_result:{request_id}"
        location_data = cache.get(result_key)

        if location_data:
            device_lat = location_data.get('latitude')
            device_lng = location_data.get('longitude')

            # 计算访客与设备之间的距离
            calc_distance = None
            if visitor_lat is not None and visitor_lng is not None and device_lat is not None and device_lng is not None:
                try:
                    calc_distance = geopy_distance(
                        (visitor_lat, visitor_lng),
                        (device_lat, device_lng)
                    ).meters
                except Exception as ex:
                    print(f"⚠️ 距离计算失败: {ex}")

            # 读取阈值，默认 500m
            config = await _get_latest_config()
            threshold = config.distance_threshold if config else 500.0
            is_success = calc_distance is not None and calc_distance <= threshold

            # 获取访客 IP：前端 JS 传来的真实公网 IP 优先，Docker 代理头次之
            visitor_ip = data.get('client_ip') or _get_client_ip(request)
            timestamp_ms = int(time.time() * 1000)

            # 逆地理编码：访客地址 + 设备地址
            visitor_address = ''
            if visitor_lat is not None and visitor_lng is not None:
                visitor_address = await asyncio.to_thread(_resolve_device_address, visitor_lat, visitor_lng)

            device_address = ''
            if device_lat is not None and device_lng is not None:
                device_address = await asyncio.to_thread(_resolve_device_address, device_lat, device_lng)

            # 持久化访客记录
            await _create_visitor_record(
                request_id=request_id,
                ip_address=visitor_ip,
                distance=calc_distance,
                timestamp=timestamp_ms,
                is_success=is_success,
                comment="",
                module="tracking",
                visitor_latitude=visitor_lat,
                visitor_longitude=visitor_lng,
                visitor_address=visitor_address,
                device_latitude=device_lat,
                device_longitude=device_lng,
                device_address=device_address,
            )

            # 给手机发送验证结果通知
            body_parts = []
            if visitor_ip:
                body_parts.append(f"访客IP: {visitor_ip}")
            if calc_distance is not None:
                body_parts.append(f"距离: {calc_distance:.1f}m (阈值{threshold:.0f}m)")
            if visitor_address:
                body_parts.append(f"访客位置: {visitor_address}")
            if device_address:
                body_parts.append(f"设备位置: {device_address}")
            notify_body = "\n".join(body_parts) or "验证完成"

            await send_to_device_async(online_device, {
                "action": "SHOW_NOTIFICATION",
                "request_id": request_id,
                "title": "✅ 验证成功" if is_success else "❌ 验证失败",
                "body": notify_body,
                "is_success": is_success,
                "visitor_ip": visitor_ip,
                "distance": calc_distance if calc_distance is not None else -1,
                "comment": "",
                "timestamp": timestamp_ms,
                "visitor_latitude": visitor_lat,
                "visitor_longitude": visitor_lng,
                "visitor_address": visitor_address,
                "device_latitude": device_lat,
                "device_longitude": device_lng,
                "device_address": device_address,
            })

            # 阅后即焚，清理 Redis
            cache.delete(result_key)

            # 返回前端（包含双方坐标和地址）
            return JsonResponse({
                "status": "success" if is_success else "fail",
                "msg": f"距离 {calc_distance:.1f}m，阈值 {threshold:.0f}m" if calc_distance is not None else "无法计算距离",
                "request_id": request_id,
                "distance": calc_distance if calc_distance is not None else -1,
                "visitor_latitude": visitor_lat,
                "visitor_longitude": visitor_lng,
                "visitor_address": visitor_address,
                "device_latitude": device_lat,
                "device_longitude": device_lng,
                "device_address": device_address,
                "location_source": location_source,
            })

        # 休息 0.5 秒，避免占满 CPU
        await asyncio.sleep(0.5)

    # 6. 等待超时
    return JsonResponse({"status": "fail", "msg": "等待手机响应超时"})

async def add_visitor_comment(request):
    """处理前端发来的留言"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            req_id = data.get('request_id')
            comment_text = data.get('comment', '')

            # 持久化 comment 到数据库
            await _update_visitor_comment(req_id, comment_text)

            # 仅当留言非空时才推送到在线设备
            if comment_text and comment_text.strip():
                online_device = await _get_online_device_id()
                if online_device:
                    await send_to_device_async(online_device, {
                        "action": "SHOW_NOTIFICATION",
                        "request_id": req_id,
                        "title": "💬 收到访客留言",
                        "body": comment_text,
                        "is_success": True,
                        "visitor_ip": "",
                        "distance": 0,
                        "comment": comment_text,
                        "timestamp": int(time.time() * 1000),
                    })
            return JsonResponse({"status": "success"})
        except Exception:
            return JsonResponse({"status": "error"}, status=400)
    return JsonResponse({"status": "error"}, status=405)


# ================== 协议 #4: 历史数据拉取 ==================

async def get_history(request):
    """协议 #4: 手机拉取历史访客记录

    GET /api/app/history?module=tracking&last_sync={本地最大Timestamp毫秒值}

    返回 timestamp > last_sync 的记录数组，按时间升序。
    last_sync 为空库时传 0。
    """
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    module = request.GET.get('module', 'tracking')
    last_sync_str = request.GET.get('last_sync', '0')

    try:
        last_sync = int(last_sync_str)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid last_sync"}, status=400)

    records = await _get_visitor_records_since(module, last_sync)

    data = [
        {
            "RequestId": r.request_id,
            "IpAddress": r.ip_address or "",
            "Distance": r.distance or 0,
            "Timestamp": r.timestamp,
            "IsSuccess": r.is_success,
            "Comment": r.comment,
            "VisitorLatitude": r.visitor_latitude,
            "VisitorLongitude": r.visitor_longitude,
            "VisitorAddress": r.visitor_address or "",
            "DeviceLatitude": r.device_latitude,
            "DeviceLongitude": r.device_longitude,
            "DeviceAddress": r.device_address or "",
        }
        for r in records
    ]

    return JsonResponse(data, safe=False)


# ================== 协议 #5: 静默位置上报 ==================

@csrf_exempt
async def report_location_http(request):
    """协议 #5: 手机后台保活时通过 HTTP 直接上报位置

    POST /api/app/report-location
    由 Android MainGuardService 每 60s 调用一次，不依赖 WebSocket。
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    auth_header = request.headers.get("Authorization", "")
    if settings.APP_SECRET_TOKEN not in auth_header:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    device_id = request.headers.get("X-Device-ID") or payload.get("device_id") or "unknown"

    # 写入 Redis 缓存，供 verify 流程或监控使用
    cache.set(f"device_location_cache:{device_id}", payload, timeout=300)

    # 同时也写入 location_result，方便配合 verify 轮询
    request_id = payload.get("request_id")
    if request_id:
        cache.set(f"location_result:{request_id}", payload, timeout=60)

    print(f"📍 HTTP 位置上报: device={device_id}, lat={payload.get('latitude')}, lng={payload.get('longitude')}")
    return JsonResponse({"status": "received"})


# ================== 手机端离线回调底层逻辑 ==================

class HttpActionContext:
    def __init__(self, device_id):
        self.device_id = device_id
        self.channel_name = "http_stateless"

@csrf_exempt
async def app_action_callback(request):
    """手机被 FCM 唤醒后，走 HTTP 接口上报坐标的入口"""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    auth_header = request.headers.get("Authorization", "")
    if settings.APP_SECRET_TOKEN not in auth_header:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body)
        device_id = request.headers.get("X-Device-ID", "unknown")
        context = HttpActionContext(device_id)

        # 丢给 WebSocket 路由器统一处理（会触发 handlers.py 里的写入 Redis 逻辑）
        await router.route_message(context, payload)

        return JsonResponse({"status": "received"})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)