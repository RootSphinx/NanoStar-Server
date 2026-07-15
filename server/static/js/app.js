// server/api/static/js/app.js
document.addEventListener('DOMContentLoaded', () => {
    const btnVerify = document.getElementById('btn-verify');
    const spinner = document.getElementById('loading-spinner');
    const statusMsg = document.getElementById('status-msg');
    const commentTitle = document.getElementById('comment-title');
    const commentSubtitle = document.getElementById('comment-subtitle');
    const commentForm = document.getElementById('comment-form');
    const visitCountEl = document.getElementById('visit-count');
    const visitMyCountEl = document.getElementById('visit-my-count');
    const totalVisitorsEl = document.getElementById('total-visitors');
    const pastCommentsEl = document.getElementById('past-comments');
    const pastCommentsList = document.getElementById('past-comments-list');
    const successMessageEl = document.getElementById('success-message');

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
    let visitorFingerprint = '';
    let maxComments = 3;

    // 页面加载后自动初始化指纹并检查 session
    initFingerprint()
        .then(fp => {
            visitorFingerprint = fp;
            checkSession();
        })
        .catch(err => {
            console.warn('FingerprintJS 初始化失败，使用兜底指纹:', err);
            visitorFingerprint = generateFallbackFingerprint();
            checkSession();
        });

    btnVerify.addEventListener('click', () => {
        startVerification();
    });

    async function initFingerprint() {
        const fp = await FingerprintJS.load();
        const result = await fp.get();
        return result.visitorId;
    }

    function generateFallbackFingerprint() {
        try {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillText('NanoStar fingerprint fallback', 2, 2);
            const canvasData = canvas.toDataURL();
            const raw = navigator.userAgent + '|' + navigator.language + '|' + screen.colorDepth + '|' + canvasData;
            let hash = 0;
            for (let i = 0; i < raw.length; i++) {
                const char = raw.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            return 'fb_' + Math.abs(hash).toString(16);
        } catch (e) {
            return 'fb_' + Date.now().toString(16);
        }
    }

    async function checkSession() {
        try {
            const response = await fetch('/api/visitor/session/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': typeof csrfToken !== 'undefined' ? csrfToken : '' },
                body: JSON.stringify({ fingerprint: visitorFingerprint })
            });
            const data = await response.json();
            if (response.ok && data.has_session) {
                currentRequestId = data.request_id;
                maxComments = data.max_comments || 3;
                showLocationDetail(data);
                handleExistingSession(data);
            } else {
                showVerifyButton();
            }
        } catch (err) {
            console.error('检查 session 失败:', err);
            showVerifyButton();
        }
    }

    function showVerifyButton() {
        spinner.classList.add('hidden');
        btnVerify.classList.remove('hidden');
        statusMsg.innerText = '';
    }

    function handleExistingSession(data) {
        const recordStatus = data.status || 'existing';
        renderSuccessMessage(data.success_message);
        if (recordStatus === 'existing') {
            setCommentTitle('你已经触发过一次啦，是还想再说点什么吗？', '之前的内容都还在呢');
            hideVisitCount();
            showCommentForm();
            renderPastComments(data.past_comments || []);
            resetCommentForm();
            switchView('view-verify', 'view-comment');
        } else if (recordStatus === 'full') {
            setCommentTitle('已经收到你的留言啦，更多的话留到下次相遇吧！', '可以先休息一会儿');
            hideVisitCount();
            hideCommentForm();
            renderPastComments(data.past_comments || []);
            switchView('view-verify', 'view-comment');
        } else {
            showVerifyButton();
        }
    }

    function startVerification() {
        const catEmoji = document.getElementById('cat-emoji');
        if (catEmoji) catEmoji.innerText = '🐱';
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
    }

    // 通过服务器代理获取真实公网 IP（API key 不暴露给前端）
    async function getPublicIp() {
        try {
            const resp = await fetch('/api/ip-location/', { signal: AbortSignal.timeout(5000) });
            const json = await resp.json();
            return json.ip || null;
        } catch (e) { return null; }
    }

    // 通过服务器代理获取 IP 地理定位经纬度
    async function getIpLocation() {
        try {
            const resp = await fetch('/api/ip-location/', { signal: AbortSignal.timeout(5000) });
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
            const payload = { latitude: lat, longitude: lng, fingerprint: visitorFingerprint };
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
                maxComments = data.max_comments || 3;
                showLocationDetail(data);
                handleVerifySuccess(data);
            } else {
                showError(data.msg || '验证失败，请重试。');
            }
        } catch (err) {
            console.error("请求失败:", err);
            showError('通讯失败，请按 F12 查看控制台报错。');
        }
    }

    function handleVerifySuccess(data) {
        const recordStatus = data.record_status || 'new';
        renderSuccessMessage(data.success_message);

        if (recordStatus === 'new') {
            setCommentTitle('已悄悄通知对方～', '对方知道有人路过啦');
            showVisitCount(data.visit_count, data.total_visitors);
            showCommentForm();
            clearPastComments();
            renderPastComments(data.past_comments || []);
            resetCommentForm();
            switchView('view-verify', 'view-comment');
        } else if (recordStatus === 'existing') {
            setCommentTitle('你已经触发过一次啦，是还想再说点什么吗？', '之前的内容都还在呢');
            hideVisitCount();
            showCommentForm();
            renderPastComments(data.past_comments || []);
            resetCommentForm();
            switchView('view-verify', 'view-comment');
        } else if (recordStatus === 'full') {
            setCommentTitle('已经收到你的留言啦，更多的话留到下次相遇吧！', '可以先休息一会儿');
            hideVisitCount();
            hideCommentForm();
            renderPastComments(data.past_comments || []);
            switchView('view-verify', 'view-comment');
        }
    }

    function setCommentTitle(title, subtitle) {
        if (commentTitle) commentTitle.textContent = title;
        if (commentSubtitle) commentSubtitle.textContent = subtitle || '';
    }

    function showVisitCount(count, totalVisitors) {
        if (!visitCountEl) return;
        if (visitMyCountEl) visitMyCountEl.textContent = `这是你第 ${count || 1} 次成功访问`;
        if (totalVisitorsEl) {
            if (totalVisitors) {
                totalVisitorsEl.textContent = `已经有 ${totalVisitors} 个人成功光顾过`;
                totalVisitorsEl.classList.remove('hidden');
            } else {
                totalVisitorsEl.classList.add('hidden');
            }
        }
        visitCountEl.classList.remove('hidden');
    }

    function hideVisitCount() {
        if (visitCountEl) visitCountEl.classList.add('hidden');
    }

    function showCommentForm() {
        if (commentForm) commentForm.style.display = 'block';
    }

    function hideCommentForm() {
        if (commentForm) commentForm.style.display = 'none';
    }

    function resetCommentForm() {
        const textarea = document.getElementById('visitor-comment');
        if (textarea) textarea.value = '';
        const btn = document.getElementById('btn-submit-comment');
        if (btn) {
            btn.disabled = false;
            btn.innerText = '💬 发送';
        }
    }

    function clearPastComments() {
        if (pastCommentsEl) pastCommentsEl.classList.add('hidden');
        if (pastCommentsList) pastCommentsList.innerHTML = '';
    }

    function renderPastComments(comments) {
        if (!pastCommentsList || !pastCommentsEl) return;
        pastCommentsList.innerHTML = '';
        if (!comments || comments.length === 0) {
            pastCommentsEl.classList.add('hidden');
            return;
        }
        comments.forEach(c => {
            const li = document.createElement('li');
            li.className = 'past-comment-item';
            const content = document.createElement('div');
            content.className = 'past-comment-content';
            content.textContent = c.content;
            const time = document.createElement('div');
            time.className = 'past-comment-time';
            time.textContent = formatCommentTime(c.created_at || c.timestamp);
            li.appendChild(content);
            li.appendChild(time);
            pastCommentsList.appendChild(li);
        });
        pastCommentsEl.classList.remove('hidden');
    }

    function formatCommentTime(value) {
        if (!value) return '';
        try {
            const d = new Date(value);
            if (isNaN(d.getTime())) {
                // 尝试毫秒时间戳
                const d2 = new Date(Number(value));
                if (!isNaN(d2.getTime())) {
                    return d2.toLocaleString('zh-CN');
                }
                return '';
            }
            return d.toLocaleString('zh-CN');
        } catch (e) {
            return '';
        }
    }

    function appendComment(comment) {
        if (!comment || !pastCommentsList || !pastCommentsEl) return;
        const li = document.createElement('li');
        li.className = 'past-comment-item';
        const content = document.createElement('div');
        content.className = 'past-comment-content';
        content.textContent = comment.content;
        const time = document.createElement('div');
        time.className = 'past-comment-time';
        time.textContent = formatCommentTime(comment.created_at || comment.timestamp);
        li.appendChild(content);
        li.appendChild(time);
        pastCommentsList.appendChild(li);
        pastCommentsEl.classList.remove('hidden');
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

    function renderSuccessMessage(message) {
        if (!successMessageEl) return;
        const contentEl = successMessageEl.querySelector('.success-message-content');
        if (!message || !message.trim()) {
            successMessageEl.classList.add('hidden');
            if (contentEl) contentEl.innerHTML = '';
            return;
        }
        if (contentEl) contentEl.innerHTML = message;
        successMessageEl.classList.remove('hidden');
    }

    function showError(msg) {
        const catEmoji = document.getElementById('cat-emoji');
        if (catEmoji) catEmoji.innerText = '😭';
        spinner.classList.add('hidden');
        btnVerify.classList.remove('hidden');
        statusMsg.style.color = '#ff5252';
        statusMsg.innerText = msg;
    }

    const btnSubmitComment = document.getElementById('btn-submit-comment');
    const doneBlankNote = document.getElementById('done-blank-note');
    const doneNormalFooter = document.getElementById('done-normal-footer');

    function setDonePage(isBlank) {
        if (doneBlankNote) {
            doneBlankNote.classList.toggle('hidden', !isBlank);
        }
        if (doneNormalFooter) {
            doneNormalFooter.classList.toggle('hidden', isBlank);
        }
    }

    if (btnSubmitComment) {
        btnSubmitComment.addEventListener('click', async () => {
            const commentTxt = document.getElementById('visitor-comment').value;
            const isBlankComment = !commentTxt || !commentTxt.trim();
            const origText = btnSubmitComment.innerText;
            btnSubmitComment.innerText = '发送中...';
            btnSubmitComment.disabled = true;
            try {
                const resp = await fetch('/api/visitor/comment/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': typeof csrfToken !== 'undefined' ? csrfToken : '' },
                    body: JSON.stringify({ request_id: currentRequestId, comment: commentTxt })
                });
                const data = await resp.json();
                if (resp.ok && data.status === 'success') {
                    if (!data.is_blank && data.comment) {
                        appendComment(data.comment);
                    }
                    const currentCount = pastCommentsList ? pastCommentsList.children.length : 0;
                    if (!data.is_blank && currentCount >= maxComments) {
                        hideCommentForm();
                        setCommentTitle('已经收到你的留言啦，更多的话留到下次相遇吧！', '可以先休息一会儿');
                    }
                    setDonePage(data.is_blank);
                    switchView('view-comment', 'view-done');
                } else {
                    alert(data.msg || '留言发送失败。');
                    btnSubmitComment.innerText = origText;
                    btnSubmitComment.disabled = false;
                }
            } catch (err) {
                alert("留言发送失败。");
                btnSubmitComment.innerText = origText;
                btnSubmitComment.disabled = false;
            }
        });
    }
});
