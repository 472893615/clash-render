from flask import Flask, request, make_response
from flask_cors import CORS
import yaml
import base64
import socket
import threading
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 固定认证信息（从环境变量获取）
# ------------------------------
def generate_random_string(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

credentials = {
    "username": os.environ.get("PROXY_USERNAME", generate_random_string()),
    "password": os.environ.get("PROXY_PASSWORD", generate_random_string(12)),
    "generated_at": datetime.now().isoformat(),
    "source": "environment" if "PROXY_USERNAME" in os.environ else "default"
}

app.logger.info(f"✅ 认证信息加载成功：\n- 用户名: {credentials['username']}\n- 密码: {credentials['password']}\n- 来源: {credentials['source']}")

# ------------------------------
# 2. 基础配置（适配Render平台）
# ------------------------------
config = {
    "http_port": int(os.environ.get("PORT", 8080)),
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),
    "external_port": 443
}

# ------------------------------
# 3. 根页面（显示服务信息）
# ------------------------------
@app.route('/')
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Clash代理服务（Render版）</title>
        <style>
            body {{ font-family: '微软雅黑', Arial, sans-serif; max-width: 900px; margin: 20px auto; padding: 0 20px; }}
            .card {{ border: 1px solid #eee; border-radius: 8px; padding: 20px; margin: 10px 0; }}
            .title {{ font-size: 1.2em; font-weight: bold; margin-bottom: 15px; }}
            .info {{ line-height: 1.6; margin-bottom: 10px; }}
            .code {{ background: #f8f8f8; padding: 10px; border-radius: 4px; word-break: break-all; }}
            .note {{ color: #666; font-style: italic; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>🔰 Clash代理服务（已修复接口路径）</h1>
        <div class="card">
            <div class="title">📌 服务信息</div>
            <div class="info">• 服务器域名：<span class="code">{config['server_domain']}</span></div>
            <div class="info">• 外部端口：<span class="code">{config['external_port']}</span></div>
            <div class="info">• 代理接口：<span class="code">/proxy</span></div>
            <div class="info">• 状态：<span style="color: green;">运行中</span></div>
        </div>
        <div class="card">
            <div class="title">🔑 认证信息（固定）</div>
            <div class="info">• 用户名：<span class="code">{credentials['username']}</span></div>
            <div class="info">• 密码：<span class="code">{credentials['password']}</span></div>
        </div>
        <div class="card">
            <div class="title">📥 订阅链接</div>
            <div class="info">• 原始YAML：<a href="/clash/raw" target="_blank" class="code">/clash/raw</a></div>
            <div class="info">• Base64订阅：<a href="/clash/subscribe" target="_blank" class="code">/clash/subscribe</a></div>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 生成Clash配置（含path: /proxy）
# ------------------------------
def _generate_clash_config() -> dict:
    return {
        "proxies": [
            {
                "name": "Render-HTTP-Proxy",
                "type": "http",
                "server": config["server_domain"],
                "port": config["external_port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": True,
                "skip-cert-verify": False,
                "path": "/proxy"  # 关键：指定代理接口路径
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择",
                "type": "url-test",
                "proxies": ["Render-HTTP-Proxy"],
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 自动选择",
            "DOMAIN-SUFFIX,youtube.com,🚀 自动选择",
            "GEOIP,CN,DIRECT",
            "MATCH,🚀 自动选择"
        ]
    }

# ------------------------------
# 5. Clash原始YAML接口
# ------------------------------
@app.route('/clash/raw')
def clash_raw():
    try:
        clash_config = _generate_clash_config()
        yaml_content = yaml.dump(
            clash_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )
        response = make_response(yaml_content)
        response.headers["Content-Type"] = "text/yaml; charset=utf-8"
        return response
    except Exception as e:
        app.logger.error(f"生成原始YAML失败：{str(e)}")
        return "内部服务器错误", 500

# ------------------------------
# 6. Clash订阅接口
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    try:
        clash_config = _generate_clash_config()
        yaml_content = yaml.dump(
            clash_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )
        base64_content = base64.b64encode(yaml_content.encode('utf-8')).decode('utf-8')
        response = make_response(base64_content)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Subscription-Userinfo"] = "upload=0; download=0; total=10737418240; expire=0"
        return response
    except Exception as e:
        app.logger.error(f"生成订阅内容失败：{str(e)}")
        return "内部服务器错误", 500

# ------------------------------
# 7. HTTP代理接口（独立路径/proxy）
# ------------------------------
@app.route('/proxy', methods=['CONNECT'])  # 独立路径，避免与GET冲突
def http_proxy():
    # 1. 验证Basic Auth
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return make_response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Proxy Service"'})
    
    # 2. 解析认证信息
    try:
        auth_bytes = base64.b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode('utf-8').split(':')
    except:
        return make_response("Invalid Authentication", 401)
    
    if username != credentials["username"] or password != credentials["password"]:
        return make_response("Invalid Credentials", 401)
    
    # 3. 解析目标主机和端口
    host = request.headers.get('Host')
    if not host:
        return make_response("Bad Request", 400)
    target_host, target_port = host.split(':') if ':' in host else (host, 443)
    target_port = int(target_port)
    
    # 4. 建立与目标服务器的连接
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect((target_host, target_port))
            # 返回200响应
            response = make_response("HTTP/1.1 200 Connection Established\r\n\r\n")
            response.status_code = 200
            
            # 5. 双向转发数据
            def forward(source, dest):
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        dest.sendall(data)
                except Exception as e:
                    app.logger.error(f"转发错误: {str(e)}")
                finally:
                    source.close()
                    dest.close()
            
            # 启动转发线程
            thread1 = threading.Thread(target=forward, args=(request.stream, sock))
            thread2 = threading.Thread(target=forward, args=(sock, request.stream))
            thread1.start()
            thread2.start()
            
            return response
    except Exception as e:
        app.logger.error(f"代理失败：{str(e)}")
        return make_response(f"Proxy Error: {str(e)}", 502)

# ------------------------------
# 8. 启动服务
# ------------------------------
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=config["http_port"],
        debug=False
    )