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
from django.utils import timezone
from datetime import timedelta
from channels.db import database_sync_to_async
from geopy.distance import distance as geopy_distance

from core.models import Device, AppConfig, VisitorRecord, Fingerprint, Comment
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
def _get_or_create_fingerprint(visitor_id):
    """根据指纹字符串查询或创建 Fingerprint，并更新最近出现时间"""
    if not visitor_id:
        return None
    fingerprint, created = Fingerprint.objects.get_or_create(visitor_fingerprint=visitor_id)
    if not created:
        fingerprint.save(update_fields=['last_seen'])
    return fingerprint


@database_sync_to_async
def _get_latest_record_by_fingerprint(fingerprint_id, cooldown_minutes):
    """查询指纹在冷却时间内的最新访问记录"""
    if not fingerprint_id or not cooldown_minutes:
        return None
    since = timezone.now() - timedelta(minutes=cooldown_minutes)
    return VisitorRecord.objects.filter(
        fingerprint_id=fingerprint_id,
        created_at__gte=since
    ).order_by('-created_at').first()


@database_sync_to_async
def _count_successful_visits(fingerprint_id):
    """统计该指纹的成功访问次数"""
    if not fingerprint_id:
        return 0
    return VisitorRecord.objects.filter(fingerprint_id=fingerprint_id, is_success=True).count()


@database_sync_to_async
def _count_total_successful_visitors():
    """统计所有成功访问人数"""
    return Fingerprint.objects.count()


@database_sync_to_async
def _create_visitor_record(request_id, ip_address, distance, timestamp, is_success, module,
                           visitor_latitude, visitor_longitude, visitor_address,
                           device_latitude, device_longitude, device_address,
                           fingerprint):
    """创建访客记录（遇 request_id 唯一约束冲突则跳过）"""
    try:
        VisitorRecord.objects.create(
            request_id=request_id,
            fingerprint=fingerprint,
            ip_address=ip_address if ip_address else None,
            distance=distance,
            timestamp=timestamp,
            is_success=is_success,
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
def _get_comments_for_record(record_id):
    """查询单条访问记录下的所有评论"""
    if not record_id:
        return []
    return list(Comment.objects.filter(visitor_record_id=record_id).order_by('created_at'))


@database_sync_to_async
def _count_comments_for_record(record_id):
    """查询单条访问记录下的评论数量"""
    if not record_id:
        return 0
    return Comment.objects.filter(visitor_record_id=record_id).count()


@database_sync_to_async
def _create_comment(record_id, fingerprint_id, content, timestamp_ms):
    """创建评论记录"""
    return Comment.objects.create(
        visitor_record_id=record_id,
        fingerprint_id=fingerprint_id,
        content=content,
        timestamp=timestamp_ms,
    )


@database_sync_to_async
def _get_visitor_records_since(module: str, last_sync: int):
    """查询 timestamp > last_sync 且 module 匹配的记录，按时间升序"""
    return list(
        VisitorRecord.objects
        .filter(timestamp__gt=last_sync, module=module)
        .select_related('fingerprint')
        .prefetch_related('comments')
        .order_by('timestamp')
    )


def _build_comment_list(comments, show_past_comments):
    """构建前端所需的评论列表"""
    if not show_past_comments:
        return []
    return [
        {
            "content": c.content,
            "timestamp": c.timestamp,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]


@database_sync_to_async
def _get_fingerprint_by_string(visitor_id):
    """根据指纹字符串查询 Fingerprint（不创建）"""
    if not visitor_id:
        return None
    try:
        return Fingerprint.objects.get(visitor_fingerprint=visitor_id)
    except Fingerprint.DoesNotExist:
        return None


@database_sync_to_async
def _get_comments_for_fingerprint(fingerprint_id):
    """查询该指纹下的所有评论（跨记录）"""
    if not fingerprint_id:
        return []
    return list(Comment.objects.filter(fingerprint_id=fingerprint_id).order_by('created_at'))


async def check_visitor_session(request):
    """页面加载时检查当前指纹是否在冷却期内有有效记录"""
    if request.method != 'POST':
        return JsonResponse({"status": "error", "msg": "Bad method"}, status=405)

    try:
        data = json.loads(request.body)
        visitor_fingerprint = data.get('fingerprint', '')
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "msg": "Invalid JSON"}, status=400)

    config = await _get_latest_config()
    cooldown_minutes = config.visit_cooldown_minutes if config else 30
    max_comments = config.max_comments_per_record if config else 3
    show_past_comments = config.show_past_comments if config else True
    show_all_history = config.show_all_history if config else False

    fingerprint = await _get_fingerprint_by_string(visitor_fingerprint)
    existing_record = await _get_latest_record_by_fingerprint(
        fingerprint.id if fingerprint else None,
        cooldown_minutes
    )

    if not existing_record:
        return JsonResponse({
            "status": "new",
            "has_session": False,
            "max_comments": max_comments,
        })

    comments_count = await _count_comments_for_record(existing_record.id)
    if comments_count < max_comments:
        record_status = "existing"
    else:
        record_status = "full"

    past_comments = []
    if show_past_comments:
        if show_all_history and fingerprint:
            comments = await _get_comments_for_fingerprint(fingerprint.id)
        else:
            comments = await _get_comments_for_record(existing_record.id)
        past_comments = _build_comment_list(comments, show_past_comments)

    return JsonResponse({
        "status": record_status,
        "has_session": True,
        "request_id": existing_record.request_id,
        "distance": existing_record.distance or -1,
        "visitor_latitude": existing_record.visitor_latitude,
        "visitor_longitude": existing_record.visitor_longitude,
        "visitor_address": existing_record.visitor_address or "",
        "device_latitude": existing_record.device_latitude,
        "device_longitude": existing_record.device_longitude,
        "device_address": existing_record.device_address or "",
        "location_source": "gps",
        "max_comments": max_comments,
        "comments_count": comments_count,
        "past_comments": past_comments,
    })


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
        visitor_fingerprint = data.get('fingerprint', '')
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
        return JsonResponse({"status": "fail", "msg": "设备不在线，等会儿再试试吧~"})

    sent_success = await send_to_device_async(online_device, payload)

    if not sent_success:
        return JsonResponse({"status": "fail", "msg": "设备不在线，等会儿再试试吧~"})

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

            # 获取或创建指纹
            fingerprint = await _get_or_create_fingerprint(visitor_fingerprint)

            # 根据指纹 + 冷却时间判断是新记录还是回访
            cooldown_minutes = config.visit_cooldown_minutes if config else 30
            max_comments = config.max_comments_per_record if config else 3
            show_past_comments = config.show_past_comments if config else True
            show_all_history = config.show_all_history if config else False
            show_total_visitors = config.show_total_visitors if config else False
            show_first_comments = config.show_first_comments if config else False

            existing_record = await _get_latest_record_by_fingerprint(
                fingerprint.id if fingerprint else None,
                cooldown_minutes
            )

            record_status = "new"
            visit_count = 0
            total_visitors = 0
            comments_count = 0
            past_comments = []

            if existing_record:
                # 回访场景：不创建新记录，仅返回已有记录信息
                request_id = existing_record.request_id
                comments_count = await _count_comments_for_record(existing_record.id)
                if comments_count < max_comments:
                    record_status = "existing"
                else:
                    record_status = "full"
                if show_past_comments:
                    if show_all_history and fingerprint:
                        comments = await _get_comments_for_fingerprint(fingerprint.id)
                    else:
                        comments = await _get_comments_for_record(existing_record.id)
                    past_comments = _build_comment_list(comments, show_past_comments)
            else:
                # 新记录场景
                await _create_visitor_record(
                    request_id=request_id,
                    ip_address=visitor_ip,
                    distance=calc_distance,
                    timestamp=timestamp_ms,
                    is_success=is_success,
                    module="tracking",
                    visitor_latitude=visitor_lat,
                    visitor_longitude=visitor_lng,
                    visitor_address=visitor_address,
                    device_latitude=device_lat,
                    device_longitude=device_lng,
                    device_address=device_address,
                    fingerprint=fingerprint,
                )
                if fingerprint:
                    visit_count = await _count_successful_visits(fingerprint.id)
                else:
                    visit_count = 1 if is_success else 0

                total_visitors = 0
                if show_total_visitors:
                    total_visitors = await _count_total_successful_visitors()

                past_comments = []
                if show_first_comments and show_past_comments and fingerprint:
                    if show_all_history:
                        comments = await _get_comments_for_fingerprint(fingerprint.id)
                    else:
                        comments = await _get_comments_for_record(fingerprint.id)
                    past_comments = _build_comment_list(comments, show_past_comments)

                # 给手机发送验证结果通知（仅新记录触发）
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
                    "comments": [],
                    "fingerprint_index": fingerprint.id if fingerprint else 0,
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
            distance_msg = f"距离 {calc_distance:.1f}m，阈值 {threshold:.0f}m" if calc_distance is not None else "无法计算距离"
            if not is_success and location_source == 'ip_fallback':
                distance_msg += "，打开GPS再试试？"
            else:
                distance_msg += "\n你在哪里?你真的有看到二维码吗(｡•́︿•̀｡)?"

            response_data = {
                "status": "success" if is_success else "fail",
                "record_status": record_status,
                "msg": distance_msg,
                "request_id": request_id,
                "distance": calc_distance if calc_distance is not None else -1,
                "visitor_latitude": visitor_lat,
                "visitor_longitude": visitor_lng,
                "visitor_address": visitor_address,
                "device_latitude": device_lat,
                "device_longitude": device_lng,
                "device_address": device_address,
                "location_source": location_source,
                "max_comments": max_comments,
                "comments_count": comments_count,
            }

            if record_status == "new":
                response_data["visit_count"] = visit_count
                if past_comments:
                    response_data["past_comments"] = past_comments
                if show_total_visitors:
                    response_data["total_visitors"] = total_visitors
            else:
                response_data["past_comments"] = past_comments

            return JsonResponse(response_data)

        # 休息 0.5 秒，避免占满 CPU
        await asyncio.sleep(0.5)

    # 6. 等待超时
    return JsonResponse({"status": "fail", "msg": "等待手机响应超时，如果你看到他了就去提醒他一下吧"})

async def add_visitor_comment(request):
    """处理前端发来的留言"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            req_id = data.get('request_id')
            comment_text = data.get('comment', '')
            is_blank = not (comment_text and comment_text.strip())

            config = await _get_latest_config()
            max_comments = config.max_comments_per_record if config else 3

            # 查找对应记录
            try:
                record = await database_sync_to_async(VisitorRecord.objects.get)(request_id=req_id)
            except VisitorRecord.DoesNotExist:
                return JsonResponse({"status": "error", "msg": "记录不存在"}, status=404)

            comments_count = await _count_comments_for_record(record.id)
            if comments_count >= max_comments:
                return JsonResponse({"status": "error", "msg": "该记录下的评论已达上限"}, status=400)

            timestamp_ms = int(time.time() * 1000)
            comment = None
            if not is_blank:
                comment = await _create_comment(
                    record_id=record.id,
                    fingerprint_id=record.fingerprint_id,
                    content=comment_text,
                    timestamp_ms=timestamp_ms,
                )

                # 仅当留言非空时才推送到在线设备
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
                        "timestamp": timestamp_ms,
                    })

            response_data = {
                "status": "success",
                "is_blank": is_blank,
            }
            if comment:
                response_data["comment"] = {
                    "content": comment.content,
                    "timestamp": comment.timestamp,
                    "created_at": comment.created_at.isoformat(),
                }
            return JsonResponse(response_data)
        except Exception as e:
            print(f"⚠️ 提交评论失败: {e}")
            return JsonResponse({"status": "error", "msg": str(e)}, status=400)
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
            "FingerprintIndex": r.fingerprint_id or 0,
            "IpAddress": r.ip_address or "",
            "Distance": r.distance or 0,
            "Timestamp": r.timestamp,
            "IsSuccess": r.is_success,
            "Comment": _get_latest_comment_text(r),
            "Comments": [
                {"content": c.content, "timestamp": c.timestamp, "created_at": c.created_at.isoformat()}
                for c in r.comments.all().order_by('created_at')
            ],
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


def _get_latest_comment_text(record):
    """获取记录的最新评论文本（兼容旧版单评论字段）"""
    latest = record.comments.order_by('-created_at').first()
    return latest.content if latest else ""


# ================== 协议 #5: 静默位置上报 ==================

@csrf_exempt

@database_sync_to_async
def _get_record_by_request_id(request_id):
    """查询单条记录（含指纹和评论预加载）"""
    try:
        return VisitorRecord.objects.select_related('fingerprint').prefetch_related('comments').get(request_id=request_id)
    except VisitorRecord.DoesNotExist:
        return None


@database_sync_to_async
def _get_past_records_for_fingerprint(fingerprint_id, exclude_request_id, show_all_history):
    """查询指纹的过往记录（不含当前记录）"""
    if not fingerprint_id or not show_all_history:
        return []
    return list(
        VisitorRecord.objects
        .filter(fingerprint_id=fingerprint_id)
        .exclude(request_id=exclude_request_id)
        .prefetch_related('comments')
        .order_by('-timestamp')
    )


async def get_record_detail(request, request_id):
    """GET /api/app/history/detail/<request_id>/
    返回当前记录完整信息 + 同一指纹的过往记录（受 AppConfig 控制）"""
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    config = await _get_latest_config()
    show_past_comments = config.show_past_comments if config else True
    show_all_history = config.show_all_history if config else False

    record = await _get_record_by_request_id(request_id)
    if not record:
        return JsonResponse({"error": "Record not found"}, status=404)

    current_comments = [
        {"content": c.content, "timestamp": c.timestamp, "created_at": c.created_at.isoformat()}
        for c in record.comments.order_by('created_at')
    ]

    past_records = []
    if show_past_comments and record.fingerprint_id:
        past = await _get_past_records_for_fingerprint(
            record.fingerprint_id, request_id, show_all_history
        )
        past_records = [
            {
                "RequestId": pr.request_id,
                "FingerprintIndex": pr.fingerprint_id or 0,
                "Distance": pr.distance or 0,
                "Timestamp": pr.timestamp,
                "IsSuccess": pr.is_success,
                "VisitorAddress": pr.visitor_address or "",
                "Comments": [
                    {"content": c.content, "timestamp": c.timestamp, "created_at": c.created_at.isoformat()}
                    for c in pr.comments.order_by('created_at')
                ],
            }
            for pr in past
        ]

    return JsonResponse({
        "Record": {
            "RequestId": record.request_id,
            "FingerprintIndex": record.fingerprint_id or 0,
            "IpAddress": record.ip_address or "",
            "Distance": record.distance or 0,
            "Timestamp": record.timestamp,
            "IsSuccess": record.is_success,
            "VisitorLatitude": record.visitor_latitude,
            "VisitorLongitude": record.visitor_longitude,
            "VisitorAddress": record.visitor_address or "",
            "DeviceLatitude": record.device_latitude,
            "DeviceLongitude": record.device_longitude,
            "DeviceAddress": record.device_address or "",
            "Comments": current_comments,
        },
        "PastRecords": past_records,
    })


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
