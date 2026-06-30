// server/api/static/js/app.js
document.addEventListener('DOMContentLoaded', () => {
    const btnVerify = document.getElementById('btn-verify');
    const spinner = document.getElementById('loading-spinner');
    const statusMsg = document.getElementById('status-msg');

    const switchView = (hideId, showId) => {
        const hideEl = document.getElementById(hideId);
        const showEl = document.getElementById(showId);
        hideEl.classList.remove('active');
        setTimeout(() => {
            hideEl.style.display = 'none';
            hideEl.classList.add('hidden');
            showEl.classList.remove('hidden');
            showEl.style.display = 'block';
            setTimeout(() => showEl.classList.add('active'), 50);
        }, 400);
    };

    let currentRequestId = null;
    let isIpFallback = false;

    btnVerify.addEventListener('click', () => {
        btnVerify.classList.add('hidden');
        spinner.classList.remove('hidden');
        statusMsg.style.color = 'var(--text-muted)';
        statusMsg.innerText = '正在寻找信号...';
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    isIpFallback = false;
                    sendVerification(position.coords.latitude, position.coords.longitude);
                },
                async (error) => {
                    console.warn("GPS denied:", error);
                    statusMsg.innerText = '⚠️ 没拿到GPS，用网络定位凑合一下...';
                    statusMsg.style.color = '#E8BF6A';
                    const ipLoc = await getIpLocation();
                    isIpFallback = true;
                    sendVerification(ipLoc.lat, ipLoc.lng);
                },
                { enableHighAccuracy: true, timeout: 8000 }
            );
        } else {
            statusMsg.innerText = '⚠️ 设备不支持GPS，用网络定位大概看一下...';
            statusMsg.style.color = '#E8BF6A';
            getIpLocation().then(ipLoc => {
                isIpFallback = true;
                sendVerification(ipLoc.lat, ipLoc.lng);
            });
        }
    });

    // 通过 uapis.cn 获取真实公网 IP（配置由 Django 模板注入）
    async function getPublicIp() {
        try {
            const url = ipApiConfig.endpoint + '?source=commercial&key=' + ipApiConfig.key;
            const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
            const json = await resp.json();
            return json.ip || null;
        } catch (e) { return null; }
    }

    // 通过 uapis.cn 获取 IP 地理定位经纬度
    async function getIpLocation() {
        try {
            const url = ipApiConfig.endpoint + '?source=commercial&key=' + ipApiConfig.key;
            const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
            const json = await resp.json();
            if (json.latitude && json.longitude) {
                return { lat: json.latitude, lng: json.longitude };
            }
        } catch (e) { /* fall through */ }
        return { lat: null, lng: null };
    }

    async function sendVerification(lat, lng) {
        statusMsg.innerText = '正在发送信号...';
        const [clientIp] = await Promise.all([getPublicIp()]);
        try {
            const payload = { latitude: lat, longitude: lng };
            if (clientIp) payload.client_ip = clientIp;
            if (isIpFallback) payload.location_source = 'ip_fallback';
            const response = await fetch('/api/visitor/verify/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': typeof csrfToken !== 'undefined' ? csrfToken : '' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                currentRequestId = data.request_id;
                showLocationDetail(data);
                switchView('view-verify', 'view-comment');
            } else {
                showError(data.msg || '验证失败，请重试。');
            }
        } catch (err) {
            console.error("请求失败:", err);
            showError('通讯失败，请按 F12 查看控制台报错。');
        }
    }

    function showLocationDetail(data) {
        const card = document.getElementById('location-detail');
        if (!card) return;
        card.style.display = 'block';

        // 访客地址
        const addrEl = document.getElementById('lbl-visitor-addr');
        if (addrEl) {
            addrEl.textContent = data.visitor_address || '就在附近呢～';
        }

        // GPS 降级警告
        if (data.location_source === 'ip_fallback') {
            const warnEl = document.getElementById('gps-warning');
            if (warnEl) warnEl.style.display = 'block';
        }
    }

    function showError(msg) {
        spinner.classList.add('hidden');
        btnVerify.classList.remove('hidden');
        statusMsg.style.color = '#ff5252';
        statusMsg.innerText = msg;
    }

    const btnSubmitComment = document.getElementById('btn-submit-comment');
    if (btnSubmitComment) {
        btnSubmitComment.addEventListener('click', async () => {
            const commentTxt = document.getElementById('visitor-comment').value;
            const origText = btnSubmitComment.innerText;
            btnSubmitComment.innerText = '发送中...';
            btnSubmitComment.disabled = true;
            try {
                await fetch('/api/visitor/comment/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': typeof csrfToken !== 'undefined' ? csrfToken : '' },
                    body: JSON.stringify({ request_id: currentRequestId, comment: commentTxt })
                });
                switchView('view-comment', 'view-done');
            } catch (err) {
                alert("留言发送失败。");
                btnSubmitComment.innerText = origText;
                btnSubmitComment.disabled = false;
            }
        });
    }
});