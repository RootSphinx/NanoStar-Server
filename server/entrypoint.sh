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
# 捕捉表结构变化并应用（注：确保 ws_gateway 已经创建或已移除）
python manage.py makemigrations core ws_gateway api
python manage.py migrate

# ==========================================
# 自动创建超级用户（凭据由 docker-compose 环境变量注入）
# ==========================================
echo "Checking superuser status..."
SUPERUSER_USERNAME="${SUPERUSER_USERNAME:-}"
SUPERUSER_PASSWORD="${SUPERUSER_PASSWORD:-}"

if [ -z "$SUPERUSER_USERNAME" ] || [ -z "$SUPERUSER_PASSWORD" ]; then
    echo "⚠️  SUPERUSER_USERNAME 或 SUPERUSER_PASSWORD 未设置，跳过超管创建。"
else
    python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nanostar.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = os.environ.get('SUPERUSER_USERNAME', '')
password = os.environ.get('SUPERUSER_PASSWORD', '')

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email='', password=password)
    print(f'✅ Superuser \'{username}\' created successfully!')
else:
    print(f'⚡ Superuser \'{username}\' already exists. Skipping creation.')
"
fi

# 收集静态文件
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting NanoStar ASGI server via Daphne..."
# 启动 ASGI 服务
exec daphne -b 0.0.0.0 -p 8000 nanostar.asgi:application