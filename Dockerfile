# Dockerfile
FROM python:3.10-slim-bookworm

# 设置环境变量，防止 Python 写 .pyc 文件，强制标准输出无缓冲
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 定义工作目录
WORKDIR /app

# 安装系统依赖 (主要为了编译 mysqlclient)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY server/requirements.txt /app/
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# 复制整个项目代码到容器中
COPY server/ /app/

# 赋予启动脚本执行权限
RUN chmod +x /app/entrypoint.sh

# 暴露 ASGI 服务端口
EXPOSE 8000

# 使用自定义脚本启动
ENTRYPOINT ["/app/entrypoint.sh"]