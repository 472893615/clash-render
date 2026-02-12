#!/bin/bash
# start.sh

echo "🚀 启动 Clash 代理服务..."

# 打印环境信息
echo "📋 环境信息:"
echo "   主机名: ${RENDER_EXTERNAL_HOSTNAME:-localhost}"
echo "   服务ID: ${RENDER_SERVICE_ID:-N/A}"
echo "   实例ID: ${RENDER_INSTANCE_ID:-N/A}"

# 启动保活服务（在后台运行）
echo "🔧 启动保活服务..."
python3 keep_alive.py &

# 启动主应用
echo "🌐 启动 Web 服务..."
exec gunicorn \
    --bind 0.0.0.0:8080 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app