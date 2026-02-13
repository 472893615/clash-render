# app.py（修正版，支持HTTPS代理）
from flask import Flask, render_template, request, jsonify, Response, redirect
from flask_cors import CORS
import yaml
import base64
import json
import time
import threading
import os
from datetime import datetime, timedelta
import socket  # 新增：导入socket模块

app = Flask(__name__)
CORS(app)

# 存储代理信息（不变）
proxy_info = {
    "server": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),
    "port": 8080,
    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "last_accessed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "access_count": 0
}

# 生成用户凭证（不变）
import random
import string
username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

credentials = {
    "username": username,
    "password": password,
    "generated_at": datetime.now().isoformat()
}

# 新增：处理HTTPS代理的CONNECT请求
@app.route('/proxy', methods=['CONNECT'])
def proxy_connect():
    """处理HTTPS代理的CONNECT请求"""
    proxy_info["access_count"] += 1
    target = request.headers['Host']
    try:
        # 解析目标主机和端口（默认443）
        host, port = target.split(':') if ':' in target else (target, 443)
        port = int(port)
        
        # 建立与目标服务器的TCP连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        
        # 返回200连接建立响应
        response = Response('', status=200)
        response.headers['Connection'] = 'keep-alive'
        
        # 将客户端的请求转发到目标服务器（双向转发）
        def forward(source, destination):
            while True:
                data = source.recv(4096)
                if not data:
                    break
                destination.sendall(data)
        
        # 启动转发线程（客户端→目标服务器）
        threading.Thread(target=forward, args=(request.stream, sock)).start()
        # 启动转发线程（目标服务器→客户端）
        threading.Thread(target=forward, args=(sock, request.stream)).start()
        
        return response
    except Exception as e:
        app.logger.error(f"CONNECT请求失败：{str(e)}")
        return jsonify({"error": str(e)}), 500

# 其他路由（不变）
@app.route('/')
def index():
    # ... 保持不变 ...
@app.route('/status')
def status():
    # ... 保持不变 ...

# 其余路由（如/clash/config、/api/credentials等）保持不变 ...

if __name__ == '__main__':
    # ... 保持不变 ...