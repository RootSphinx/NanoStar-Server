# NanoStar 前端粉暖重设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 NanoStar 访客页从暗黑科技风改为粉暖马卡龙可爱风，适配手机端

**Architecture:** 仅修改前端三文件（HTML/CSS/JS），不改 JS 逻辑和后端。保留三视图结构，替换所有文案和配色

**Tech Stack:** 纯 HTML/CSS/JS，Django 模板渲染

## Global Constraints

- 配色使用马卡龙粉紫渐变：背景 `#fdf2f8`→`#fce4ec`→`#e8eaf6`→`#e0f7fa`，主色 `#c084d8`
- 主角视觉: 🐱 猫
- 不出现: 日文、"主人"、"藏在XX"、"星星"（视图3除外）
- 按钮最小高度 44px，字号 ≥14px（移动端触控）
- 位置卡片仅保留访客信息（2行），删除设备坐标/地址行

---

### Task 1: 重写 style.css — 粉暖马卡龙配色

**Files:**
- Modify: `server/api/static/css/style.css`（完整替换）

**Interfaces:**
- Consumes: 无前置依赖
- Produces: CSS 变量 `--primary-color`, `--bg-gradient`, `--card-bg`, `--text-main`, `--text-muted`, `--accent-purple`, `--warm-brown`; 类 `.glass-card`, `.glow-on-hover`, `.submit-btn`, `.location-detail`, `.detail-row`, `.gps-warning` 等（HTML 和 JS 已引用这些类名）

- [ ] **Step 1: 完整替换 style.css**

```css
:root {
    --primary-color: #c084d8;
    --accent-pink: #f48fb1;
    --accent-mint: #80deea;
    --bg-gradient: linear-gradient(175deg, #fdf2f8 0%, #fce4ec 40%, #e8eaf6 85%, #e0f7fa 100%);
    --card-bg: rgba(255, 255, 255, 0.65);
    --card-border: rgba(225, 190, 231, 0.25);
    --text-main: #6d4c41;
    --text-muted: #b39ddb;
    --text-sub: #8d6e63;
    --btn-gradient: linear-gradient(135deg, #e1bee7, #b3e5fc);
    --btn-send-gradient: linear-gradient(135deg, #f48fb1, #ce93d8);
    --shadow-soft: 0 6px 30px rgba(180, 140, 220, 0.25);
    --shadow-btn: 0 4px 20px rgba(180, 140, 220, 0.35);
}

*, *::before, *::after { box-sizing: border-box; }

body, html {
    margin: 0; padding: 0;
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: var(--bg-gradient);
    color: var(--text-main);
    display: flex;
    justify-content: center;
    align-items: center;
    -webkit-tap-highlight-color: transparent;
}

/* 顶条装饰 */
body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #ce93d8, #f48fb1, #80deea);
    z-index: 10;
}

/* 卡片 */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(12px);
    border: 1px solid var(--card-border);
    border-radius: 24px;
    padding: 36px 28px;
    width: 92%;
    max-width: 380px;
    text-align: center;
    box-shadow: var(--shadow-soft);
    margin: 16px;
}

.logo {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 2.5px;
    color: var(--primary-color);
    margin-bottom: 8px;
}

/* 猫猫 */
.cat-emoji {
    font-size: 48px;
    display: block;
    margin-bottom: 4px;
    animation: catBounce 2s ease-in-out infinite;
}

@keyframes catBounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-6px); }
}

/* 视图切换 */
.view-section {
    display: none;
    opacity: 0;
    transform: translateY(12px);
}

.view-section.active {
    display: block;
    animation: fadeUp 0.4s ease forwards;
}

@keyframes fadeUp {
    to { opacity: 1; transform: translateY(0); }
}

/* 主按钮 */
.glow-on-hover {
    width: 80%;
    min-height: 48px;
    border: none;
    outline: none;
    color: #6a1b9a;
    background: var(--btn-gradient);
    cursor: pointer;
    border-radius: 30px;
    font-size: 15px;
    font-weight: 600;
    margin-top: 16px;
    box-shadow: var(--shadow-btn);
    transition: transform 0.15s, box-shadow 0.15s;
    letter-spacing: 0.5px;
    -webkit-appearance: none;
}

.glow-on-hover:active {
    transform: scale(0.96);
    box-shadow: 0 2px 10px rgba(180, 140, 220, 0.25);
}

/* 加载动画 */
.spinner {
    width: 36px; height: 36px;
    border: 3px solid rgba(192, 132, 216, 0.2);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 20px auto;
}
.hidden { display: none !important; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

/* 状态文字 */
.status-text {
    margin-top: 14px;
    font-size: 14px;
    color: var(--text-muted);
}

/* 成功图标 */
.success-icon {
    font-size: 42px;
    margin-bottom: 8px;
    animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
@keyframes popIn {
    0% { transform: scale(0); }
    100% { transform: scale(1); }
}

/* 成功标题 */
.success-title {
    font-size: 18px;
    font-weight: 700;
    color: #6a1b9a;
    margin: 0 0 6px 0;
}

.success-desc {
    font-size: 13px;
    color: var(--text-sub);
    margin: 0 0 16px 0;
}

/* 位置卡片（简化版） */
.location-detail {
    margin-top: 12px;
    margin-bottom: 14px;
    padding: 12px 18px;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    text-align: center;
    line-height: 1.7;
}

.detail-row {
    padding: 2px 0;
}

.detail-label {
    font-size: 13px;
    color: var(--text-sub);
}

.detail-value {
    font-size: 14px;
    color: var(--primary-color);
    font-weight: 600;
}

/* GPS 警告 */
.gps-warning {
    background: rgba(255, 183, 77, 0.12);
    border: 1px solid rgba(255, 183, 77, 0.25);
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 12px;
    font-size: 12px;
    color: #e6960a;
    text-align: center;
}

/* 留言区 */
.comment-box {
    margin-top: 8px;
    text-align: left;
}
.comment-box label {
    font-size: 13px;
    color: var(--text-muted);
}
textarea {
    width: 100%;
    margin-top: 6px;
    padding: 12px;
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(225, 190, 231, 0.4);
    border-radius: 14px;
    color: var(--text-main);
    resize: none;
    outline: none;
    box-sizing: border-box;
    font-size: 14px;
    font-family: inherit;
    -webkit-appearance: none;
}
textarea:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(192, 132, 216, 0.1);
}

.submit-btn {
    width: 100%;
    min-height: 44px;
    padding: 12px;
    margin-top: 12px;
    border: none;
    background: var(--btn-send-gradient);
    color: #fff;
    border-radius: 30px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(206, 147, 216, 0.3);
    transition: transform 0.15s, box-shadow 0.15s;
    -webkit-appearance: none;
}
.submit-btn:active {
    transform: scale(0.96);
}

.submit-btn:disabled {
    opacity: 0.6;
    transform: none;
}

/* h2 统一样式 */
.glass-card h2 {
    font-size: 18px;
    font-weight: 700;
    color: #6a1b9a;
    margin: 8px 0 6px 0;
}

.glass-card p {
    font-size: 14px;
    color: var(--text-sub);
    line-height: 1.7;
}

/* 完成页脚注 */
.done-footer {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 24px;
}
```

- [ ] **Step 2: 验证 CSS 语法无误** — 在浏览器中打开页面确认无样式崩溃

- [ ] **Step 3: 提交**

```bash
git add server/api/static/css/style.css
git commit -m "style: 粉暖马卡龙配色重写"
```

---

### Task 2: 更新 index.html — 文案与结构

**Files:**
- Modify: `server/api/templates/index.html`

**Interfaces:**
- Consumes: Task 1 的 CSS 类名（`.cat-emoji`, `.success-title`, `.success-desc`, `.done-footer`）
- Produces: DOM 元素 id 不变（`view-verify`, `view-comment`, `view-done`, `btn-verify`, `visitor-comment`, `btn-submit-comment`, `location-detail`, `lbl-visitor-coord`, `lbl-visitor-addr`, `gps-warning`），JS 不受影响

- [ ] **Step 1: 替换 index.html 全部内容**

```django
{% load static %}
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>NanoStar</title>
    <link rel="stylesheet" href="{% static 'css/style.css' %}">
</head>
<body>
    <div class="glass-card">
        <div class="logo">NanoStar</div>

        <!-- 视图 1：首页 -->
        <div id="view-verify" class="view-section active">
            <span class="cat-emoji">🐱</span>
            <p>哇，你发现了一个神秘标记</p>
            <button id="btn-verify" class="glow-on-hover">✨ 摸一下</button>
            <div id="loading-spinner" class="spinner hidden"></div>
            <p id="status-msg" class="status-text"></p>
        </div>

        <!-- 视图 2：点亮后 + 留言 -->
        <div id="view-comment" class="view-section hidden">
            <div class="success-icon">🌟</div>
            <h2>已悄悄通知对方～</h2>
            <p class="success-desc">对方知道有人路过啦</p>

            <!-- 位置卡片（仅访客信息） -->
            <div id="location-detail" class="location-detail" style="display:none">
                <div id="gps-warning" class="gps-warning" style="display:none">
                    ⚠️ 没有GPS权限，位置是个大概
                </div>
                <div class="detail-row">
                    <span class="detail-label">📍 你在这里</span>
                </div>
                <div class="detail-row">
                    <span class="detail-value" id="lbl-visitor-addr">就在附近呢～</span>
                </div>
            </div>

            <div class="comment-box">
                <label for="visitor-comment">想说点什么吗？（随便啦）</label>
                <textarea id="visitor-comment" rows="3" placeholder="比如：路过打个卡～"></textarea>
                <button id="btn-submit-comment" class="submit-btn">💬 发送</button>
            </div>
        </div>

        <!-- 视图 3：完成 -->
        <div id="view-done" class="view-section hidden">
            <h2>搞定啦</h2>
            <p>你的信号已经发出去了 ✨<br>可以关掉这个页面啦</p>
            <p class="done-footer">有缘还会再遇到的 👋</p>
        </div>
    </div>

    <script>
        const csrfToken = "{{ csrf_token }}";
        const ipApiConfig = {
            endpoint: "{{ ip_api_endpoint }}",
            key: "{{ ip_api_key }}"
        };
    </script>
    <script src="{% static 'js/app.js' %}"></script>
</body>
</html>
```

- [ ] **Step 2: 确认** — 检查所有 id 与 JS 中引用一致：`view-verify`, `view-comment`, `view-done`, `btn-verify`, `loading-spinner`, `status-msg`, `location-detail`, `gps-warning`, `lbl-visitor-addr`, `visitor-comment`, `btn-submit-comment`

- [ ] **Step 3: 提交**

```bash
git add server/api/templates/index.html
git commit -m "feat: 更新前端文案与结构为粉暖风格"
```

---

### Task 3: 更新 app.js — JS 文案

**Files:**
- Modify: `server/api/static/js/app.js`

**Interfaces:**
- Consumes: Task 2 的 DOM id（`lbl-visitor-addr` 替代了 `lbl-visitor-coord`），需确保 JS 不再引用已删除的 `lbl-visitor-coord`, `lbl-device-coord`, `lbl-device-addr`
- Produces: 无新增接口，行为不变

- [ ] **Step 1: 修改 JS 中的文案和适配简化后的位置卡片**

需要修改以下几处：

**1a. 修改 `btnVerify` 点击事件中的加载文案（约第 27 行）:**

```javascript
// 旧:
statusMsg.innerText = '正在获取位置授权...';
// 新:
statusMsg.innerText = '正在寻找信号...';
```

**1b. 修改 GPS 降级提示（约第 36 行）:**

```javascript
// 旧:
statusMsg.innerText = '⚠️ 无GPS权限，使用网络定位（位置可能不准确）...';
// 新:
statusMsg.innerText = '⚠️ 没拿到GPS，用网络定位凑合一下...';
```

**1c. 修改设备不支持 GPS 提示（约第 45 行）:**

```javascript
// 旧:
statusMsg.innerText = '⚠️ 设备不支持GPS，使用网络定位（位置可能不准确）...';
// 新:
statusMsg.innerText = '⚠️ 设备不支持GPS，用网络定位大概看一下...';
```

**1d. 修改 `sendVerification` 中的加载文案（约第 78 行）:**

```javascript
// 旧:
statusMsg.innerText = '正在呼叫机主并核对位置...';
// 新:
statusMsg.innerText = '正在发送信号...';
```

**1e. 修改 `showLocationDetail` 函数（约第 103-125 行）:**

简化为只显示访客地址，删除坐标和设备信息：

```javascript
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
```

**1f. 修改 `showError` 中的错误文案（约第 130 行，可选）:**

```javascript
// 保持现有错误文案或改为:
// statusMsg.innerText = msg;  // 不变，错误信息来自后端
```

- [ ] **Step 2: 确认所有 id 引用** — 确保 `showLocationDetail` 只引用存在的 DOM 元素（`location-detail`, `lbl-visitor-addr`, `gps-warning`），不引用已删除的 `lbl-visitor-coord`, `lbl-device-coord`, `lbl-device-addr`

- [ ] **Step 3: 提交**

```bash
git add server/api/static/js/app.js
git commit -m "feat: 更新 JS 文案为轻松语气，简化位置卡片逻辑"
```

---

### Task 4: 全局验证

- [ ] **Step 1: 检查残余** — 搜索旧文案确认无遗漏

```bash
grep -rn "安全验证\|获取权限\|呼叫机主\|机主设备\|验证通过\|身份验证\|留个言吧\|找我什么事\|访客坐标\|设备坐标\|感谢您的访问" server/api/
```

预期：无匹配结果

- [ ] **Step 2: 检查 id 一致性** — 确认 HTML 和 JS 之间的 DOM id 匹配

```bash
# HTML 中的 id
grep -oP 'id="([^"]*)"' server/api/templates/index.html | sort > /tmp/html_ids.txt
# JS 中引用的 id (getElementById)
grep -oP "getElementById\('([^']*)'\)" server/api/static/js/app.js | sort > /tmp/js_ids.txt
diff /tmp/html_ids.txt /tmp/js_ids.txt
```

JS 引用的 id 应全部在 HTML 中存在。

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore: 验证无旧文案残留，id 一致性检查通过"
```
