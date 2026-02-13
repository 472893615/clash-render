from flask import Flask, request, jsonify, make_response, abort
from flask_cors import CORS
import yaml
import base64
import socket
import threading
import os
import random
import string
from datetime import datetime
from base64 import b64decode

# 初始化Flask应用（开启CORS）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 环境变量获取与默认值（解决启动失败问题）
# ------------------------------
def generate_random_string(length: int) -> str:
    """生成随机字符串（用于默认Credentials）"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# 从环境变量获取Credentials，未设置时使用默认值（随机生成）
credentials = {
    "username": os.environ.get("PROXY_USERNAME", generate_random_string(8)),
    "password": os.environ.get("PROXY_PASSWORD", generate_random_string(12)),
    "generated_at": datetime.now().isoformat(),
    "source": "environment" if "PROXY_USERNAME" in os.environ else "default"
}
app.logger.info(f"✅ 服务启动成功：Credentials来源={credentials['source']}\n- Username: {credentials['username']}\n- Password: {credentials['password']}")

# ------------------------------
# 2. 配置项（适配Render平台端口限制）
# ------------------------------
config = {
    # Render仅开放80/443端口，内部映射到应用端口（由Render自动分配，从环境变量获取）
    "http_port": int(os.environ.get("PORT", 8080)),  # Render会自动设置PORT环境变量
    "socks5_port": 1080,  # 内部SOCKS5端口（仅服务内部使用）
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render分配的域名（如xxx.onrender.com）
    "external_port": 443  # 外部访问统一使用443端口（HTTPS）
}

# ------------------------------
# 3. 根路径：引导页面（更新端口说明）
# ------------------------------
@app.route('/')
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Clash Proxy Service（Render部署）</title>
        <style>
            body {{ font-family: '微软雅黑', Arial, sans-serif; max-width: 900px; margin: 50px auto; padding: 0 20px; }}
            h1 {{ color: #2d3748; font-size: 2.5em; margin-bottom: 30px; }}
            .card {{ background: #f7fafc; border-radius: 10px; padding: 20px 30px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .card h2 {{ color: #2b6cb0; font-size: 1.5em; margin-bottom: 15px; }}
            .card p {{ color: #4a5568; font-size: 1.1em; line-height: 1.6; }}
            .link {{ color: #2b6cb0; text-decoration: none; font-weight: bold; }}
            .link:hover {{ text-decoration: underline; }}
            .note {{ background: #fff3cd; border-radius: 10px; padding: 15px 20px; margin-top: 30px; color: #856404; }}
            .warning {{ color: #dc2626; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🌐 Clash Proxy Service（Render部署）</h1>
        
        <div class="card">
            <h2>📌 核心功能接口</h2>
            <p>1. 获取当前Credentials：<a class="link" href="/api/credentials" target="_blank">/api/credentials</a></p>
            <p>2. Clash订阅链接：<a class="link" href="/clash/subscribe" target="_blank">/clash/subscribe</a></p>
        </div>
        
        <div class="card">
            <h2>💡 节点连接说明</h2>
            <p>✅ 外部访问端口：<code>443</code>（HTTPS，Render平台统一端口）</p>
            <p>✅ 服务器域名：<code>{config['server_domain']}</code></p>
            <p>✅ 协议：HTTP/SOCKS5（均需认证，Credentials见上方接口）</p>
        </div>
        
        <div class="note">
            <p>⚠️ 提示：若Clash无法找到节点，请检查订阅链接是否正确，或尝试手动添加节点（服务器：{config['server_domain']}，端口：443，用户名/密码见/api/credentials）。</p>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 核心接口：返回Credentials（包含外部端口）
# ------------------------------
@app.route('/api/credentials')
def get_credentials():
    return jsonify({
        "username": credentials["username"],
        "password": credentials["password"],
        "server_domain": config["server_domain"],
        "external_port": config["external_port"],  # 外部访问端口（443）
        "generated_at": credentials["generated_at"],
        "source": credentials["source"]
    })

# ------------------------------
# 5. 核心功能：生成Clash订阅配置（修复节点端口和协议）
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    # 构建Clash配置（使用Render外部域名+443端口，确保外部可访问）
    clash_config = {
        "proxies": [
            # HTTP代理节点（使用443端口+HTTPS）
            {
                "name": "Render-HTTP-Proxy",
                "type": "http",
                "server": config["server_domain"],
                "port": config["external_port"],  # 外部端口443（非内部8080）
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": True,  # 必须启用HTTPS（Render强制HTTPS）
                "skip-cert-verify": False
            },
            # SOCKS5代理节点（使用443端口+TLS）
            {
                "name": "Render-SOCKS5-Proxy",
                "type": "socks5",
                "server": config["server_domain"],
                "port": config["external_port"],  # 外部端口443（非内部1080）
                "username": credentials["username"],
                "password": credentials["password"],
                "udp": True,
                "tls": True,  # 启用TLS加密
                "skip-cert-verify": False
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择节点",
                "type": "url-test",
                "proxies": ["Render-HTTP-Proxy", "Render-SOCKS5-Proxy"],
                "url": "https://www.google.com/generate_204",
                "interval": 300
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 自动选择节点",
            "DOMAIN-SUFFIX,youtube.com,🚀 自动选择节点",
            "GEOIP,CN,DIRECT",
            "MATCH,🚀 自动选择节点"
        ]
    }

    # 转换为YAML并Base64编码（Clash订阅格式）
    yaml_config = yaml.dump(clash_config, allow_unicode=True, default_flow_style=False)
    base64_config = base64.b64encode(yaml_config.encode()).decode()

    # 返回订阅响应
    response = make_response(base64_config)
    response.headers["Content-Type"] = "text/plain"
    response.headers["X-Clash-Config"] = "Render-Proxy-Subscribe"
    return response

# ------------------------------
# 6. HTTP代理（处理Render 443端口转发）
# ------------------------------
@app.route('/proxy', methods=['CONNECT'])
def http_proxy():
    """处理HTTPS代理（通过Render 443端口转发到内部HTTP服务）"""
    # 1. 验证Basic Auth
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        abort(401, description="Unauthorized", headers={"WWW-Authenticate": "Basic realm='Proxy Service'"})
    
    # 解析用户名密码
    try:
        auth_bytes = b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode().split(':')
    except:
        abort(401, description="Invalid Authentication")
    
    if username != credentials["username"] or password != credentials["password"]:
        abort(401, description="Invalid Credentials")

    # 2. 转发HTTPS请求
    try:
        target_host, target_port = request.headers['Host'].split(':')
        target_port = int(target_port)

        # 连接目标服务器
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((target_host, target_port))

        # 返回连接成功响应
        response = make_response("200 Connection Established\r\n\r\n")
        response.status_code = 200

        # 双向转发数据
        def forward(source, dest):
            try:
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    dest.sendall(data)
            finally:
                source.close()
                dest.close()

        threading.Thread(target=forward, args=(request.stream, sock), daemon=True).start()
        threading.Thread(target=forward, args=(sock, request.stream), daemon=True).start()

        return response
    except Exception as e:
        app.logger.error(f"HTTP代理错误：{str(e)}")
        abort(502, description="Bad Gateway")

# ------------------------------
# 7. SOCKS5代理（内部端口，通过Render 443转发）
# ------------------------------
def handle_socks5_connection(conn, addr):
    """处理SOCKS5连接请求"""
    app.logger.info(f"SOCKS5连接来自：{addr}")

    # 认证逻辑（与HTTP代理共享Credentials）
    if not handle_socks5_authentication(conn):
        return

    # 处理SOCKS5请求（解析目标地址、转发数据，逻辑同上一版本）
    # ...（省略与之前相同的SOCKS5数据解析和转发代码）...

def start_socks5_server():
    """启动内部SOCKS5服务（监听1080端口）"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', config["socks5_port"]))
        sock.listen(5)
        app.logger.info(f"SOCKS5服务启动，内部端口：{config['socks5_port']}")
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=handle_socks5_connection, args=(conn, addr), daemon=True).start()
    except Exception as e:
        app.logger.error(f"SOCKS5启动失败：{str(e)}")

# ------------------------------
# 8. 启动服务
# ------------------------------
if __name__ == '__main__':
    # 启动SOCKS5服务（后台线程）
    threading.Thread(target=start_socks5_server, daemon=True).start()
    # 启动Flask（监听Render分配的PORT，外部通过443访问）
    app.run(host='0.0.0.0', port=config["http_port"], debug=False)