#!/bin/bash
# server/entrypoint.sh

echo "Waiting for MySQL database to be ready..."

# 启动一个无限循环，使用 Django 环境进行真实的数据库连接测试
until python -c "
import os
import django
from django.db import connection
from django.db.utils import OperationalError

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nanostar.settings')
django.setup()

try:
    connection.ensure_connection()
except OperationalError:
    exit(1)
" 2>/dev/null; do
    echo "Database is unavailable - sleeping 2 seconds..."
    sleep 2
done

echo "✅ MySQL database is fully ready!"

echo "Apply database migrations..."
# 捕捉表结构变化并应用
python manage.py makemigrations core ws_gateway api
python manage.py migrate

# 收集静态文件
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting NanoStar ASGI server via Daphne..."
# 启动 ASGI 服务
exec daphne -b 0.0.0.0 -p 8000 nanostar.asgi:application