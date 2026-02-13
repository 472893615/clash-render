from flask import Flask, request, make_response, jsonify
from flask_cors import CORS
import yaml
import base64
import socket
import threading
import os
import random
import string
from datetime import datetime

# 初始化Flask应用（开启CORS）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 认证信息（用户名/密码）
# ------------------------------
def generate_random_string(length: int) -> str:
    """生成随机字符串，用于默认认证信息"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# 从环境变量获取认证信息（未设置则自动生成）
credentials = {
    "username": os.environ.get("PROXY_USERNAME", generate_random_string(8)),
    "password": os.environ.get("PROXY_PASSWORD", generate_random_string(12)),
    "generated_at": datetime.now().isoformat(),
    "source": "environment" if "PROXY_USERNAME" in os.environ else "default"
}
app.logger.info(f"✅ 服务启动成功：\n- 用户名: {credentials['username']}\n- 密码: {credentials['password']}")

# ------------------------------
# 2. 基础配置（适配Render）
# ------------------------------
config = {
    "http_port": int(os.environ.get("PORT", 8080)),  # Render分配的内部端口（必填）
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render域名
    "external_port": 443  # Render外部端口（固定443）
}

# ------------------------------
# 3. 根页面（调试信息）
# ------------------------------
@app.route('/')
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>HTTP代理服务（Render适配版）</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; }}
            .section {{ border: 1px solid #e0e0e0; padding: 15px; margin: 10px 0; border-radius: 8px; }}
            .title {{ color: #2c3e50; margin-top: 0; }}
            .code {{ background: #f5f5f5; padding: 10px; border-radius: 4px; word-break: break-all; }}
            .note {{ color: #3498db; font-style: italic; }}
            .warning {{ color: #e74c3c; }}
        </style>
    </head>
    <body>
        <h1>🔧 HTTP代理服务（已修复Timeout问题）</h1>
        
        <div class="section">
            <h2 class="title">📌 订阅链接</h2>
            <div class="code">
                <a href="/clash/subscribe" target="_blank">https://{config['server_domain']}/clash/subscribe</a>
            </div>
            <p class="note">使用Clash客户端导入，仅支持HTTP代理（Render限制）。</p>
        </div>
        
        <div class="section">
            <h2 class="title">🔍 调试工具</h2>
            <p>1. 原始YAML配置（用于手动导入）：<br>
            <a href="/clash/raw" target="_blank" class="code">https://{config['server_domain']}/clash/raw</a></p>
            <p>2. 认证信息：<br>
            <a href="/api/credentials" target="_blank" class="code">https://{config['server_domain']}/api/credentials</a></p>
        </div>
        
        <div class="section warning">
            <h2 class="title">⚠️ 注意事项</h2>
            <p>1. Render仅开放443端口，故移除SOCKS5服务，仅支持HTTP代理。</p>
            <p>2. 若节点超时，检查网络是否允许访问443端口（如校园网/公司网可能封锁）。</p>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 生成Clash配置（仅HTTP节点）
# ------------------------------
def _generate_clash_config():
    """生成符合Clash规范的YAML配置（仅包含HTTP代理节点）"""
    return {
        "proxies": [
            {
                "name": "Render-HTTP-Proxy",
                "type": "http",
                "server": config["server_domain"],
                "port": config["external_port"],  # 固定443（Render外部端口）
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": True,  # Render强制HTTPS
                "skip-cert-verify": False  # 不跳过证书验证
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择",
                "type": "url-test",
                "proxies": ["Render-HTTP-Proxy"],  # 仅HTTP节点
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
# 5. Clash订阅接口（Base64编码）
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    """生成Clash订阅链接（Base64编码的YAML配置）"""
    try:
        clash_config = _generate_clash_config()
        # 转换为YAML格式（保留中文、固定缩进）
        yaml_config = yaml.dump(
            clash_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )
        # Base64编码（Clash订阅要求）
        base64_config = base64.b64encode(yaml_config.encode()).decode()
        # 返回订阅内容
        response = make_response(base64_config)
        response.headers["Content-Type"] = "text/plain"
        response.headers["Subscription-Userinfo"] = "upload=0; download=0; total=10737418240; expire=0"
        return response
    except Exception as e:
        app.logger.error(f"订阅生成失败：{str(e)}")
        return "订阅配置错误", 500

# ------------------------------
# 6. 原始YAML配置接口（调试用）
# ------------------------------
@app.route('/clash/raw')
def clash_raw():
    """返回未编码的原始YAML配置"""
    clash_config = _generate_clash_config()
    yaml_config = yaml.dump(
        clash_config,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2
    )
    response = make_response(yaml_config)
    response.headers["Content-Type"] = "text/yaml"
    return response

# ------------------------------
# 7. 认证信息接口
# ------------------------------
@app.route('/api/credentials')
def get_credentials():
    """返回当前认证信息"""
    return jsonify({
        "username": credentials["username"],
        "password": credentials["password"],
        "server_domain": config["server_domain"],
        "external_port": config["external_port"],
        "generated_at": credentials["generated_at"]
    })

# ------------------------------
# 8. HTTP代理接口（处理CONNECT请求）
# ------------------------------
@app.route('/proxy', methods=['CONNECT'])
def http_proxy():
    """处理HTTPS代理请求（Render适配版）"""
    # 1. 验证Basic Auth
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return make_response(
            "Unauthorized",
            401,
            {"WWW-Authenticate": 'Basic realm="Proxy Service"'})
    
    # 2. 解析认证信息
    try:
        auth_bytes = base64.b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode().split(':')
    except Exception as e:
        app.logger.error(f"认证信息解析失败：{str(e)}")
        return make_response("Invalid Authentication", 401)
    
    # 3. 验证用户名密码
    if username != credentials["username"] or password != credentials["password"]:
        app.logger.warning(f"无效的认证信息：{username}:{password}")
        return make_response("Invalid Credentials", 401)
    
    # 4. 解析目标主机和端口（处理无端口的情况，默认443）
    host = request.headers.get('Host')
    if not host:
        return make_response("Bad Request (Missing Host Header)", 400)
    
    # 分割主机和端口（如"google.com:443" → ("google.com", 443)；"google.com" → ("google.com", 443)）
    target_host, target_port = host.split(':') if ':' in host else (host, 443)
    try:
        target_port = int(target_port)
    except ValueError:
        return make_response(f"Invalid Port: {target_port}", 400)
    
    # 5. 建立与目标服务器的连接
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((target_host, target_port))
            # 返回连接成功响应
            response = make_response("200 Connection Established\r\n\r\n")
            response.status_code = 200
            
            # 6. 双向转发数据（使用线程确保并发）
            def forward(source, dest):
                """双向转发数据"""
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        dest.sendall(data)
                except Exception as e:
                    app.logger.error(f"数据转发失败：{str(e)}")
                finally:
                    source.close()
                    dest.close()
            
            # 启动转发线程（daemon=True 确保线程随进程退出）
            threading.Thread(target=forward, args=(request.stream, sock), daemon=True).start()
            threading.Thread(target=forward, args=(sock, request.stream), daemon=True).start()
            
            return response
    except Exception as e:
        app.logger.error(f"连接目标服务器失败：{str(e)}")
        return make_response(f"Bad Gateway ({str(e)})", 502)

# ------------------------------
# 9. 启动服务
# ------------------------------
if __name__ == '__main__':
    # 启动Flask应用（监听Render分配的端口）
    app.run(
        host='0.0.0.0',
        port=config["http_port"],
        debug=False  # Render生产环境禁用debug
    )