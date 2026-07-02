# Dockerfile
FROM python:3.10-slim-bookworm

# 设置环境变量，防止 Python 写 .pyc 文件，强制标准输出无缓冲
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 定义工作目录
WORKDIR /app

# ==========================================
# [新增] 将 Debian 12 系统源替换为清华源，极速提速 apt-get
# ==========================================
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖 (主要为了编译 mysqlclient)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# [新增] 配置 pip 全局使用清华源
# ==========================================
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制并安装 Python 依赖
COPY server/requirements.txt /app/
# (顺手帮你加了 --no-cache-dir，防止缓存拉大镜像体积)
RUN pip install --upgrade pip --no-cache-dir \
    && pip install -r requirements.txt --no-cache-dir

# 复制整个项目代码到容器中
COPY server/ /app/

# 赋予启动脚本执行权限
RUN chmod +x /app/entrypoint.sh

# 暴露 ASGI 服务端口
EXPOSE 8000

# 使用自定义脚本启动
ENTRYPOINT ["/app/entrypoint.sh"]