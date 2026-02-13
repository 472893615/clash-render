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
from base64 import b64decode, b64encode

# 初始化Flask应用（开启CORS，允许跨域请求）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 生成/获取认证信息（用户名/密码）
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
# 2. 基础配置（适配Render平台）
# ------------------------------
config = {
    "http_port": int(os.environ.get("PORT", 8080)),  # Render分配的内部端口（必填）
    "socks5_port": 1080,  # 内部SOCKS5服务端口（仅服务内部使用）
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render自动分配的域名
    "external_port": 443  # 外部访问端口（Render仅开放443，不可修改）
}

# ------------------------------
# 3. 根页面（调试信息与帮助）
# ------------------------------
@app.route('/')
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Clash代理服务（已修复）</title>
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
        <h1>🔧 Clash代理服务（已修复YAML格式）</h1>
        
        <div class="section">
            <h2 class="title">📌 订阅链接</h2>
            <div class="code">
                <a href="/clash/subscribe" target="_blank">https://{config['server_domain']}/clash/subscribe</a>
            </div>
            <p class="note">请在Clash中添加此链接，确保网络正常。</p>
        </div>
        
        <div class="section">
            <h2 class="title">🔍 调试工具</h2>
            <p>1. 查看原始YAML配置（用于检查格式）：<br>
            <a href="/clash/raw" target="_blank" class="code">https://{config['server_domain']}/clash/raw</a></p>
            <p>2. 获取认证信息（用户名/密码）：<br>
            <a href="/api/credentials" target="_blank" class="code">https://{config['server_domain']}/api/credentials</a></p>
        </div>
        
        <div class="section warning">
            <h2 class="title">⚠️ 注意事项</h2>
            <p>1. 确保Render服务状态为"Running"（可在Render控制台查看）。</p>
            <p>2. 若节点仍不显示，检查Clash客户端版本（建议使用Clash for Windows 0.20.0+）。</p>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 生成Clash配置（核心：修复YAML格式）
# ------------------------------
def _generate_clash_config():
    """生成格式正确的Clash配置字典（确保缩进、字段顺序、无乱码）"""
    return {
        "proxies": [
            # HTTP代理节点（字段按标准顺序排列，确保Clash能解析）
            {
                "name": "Render-HTTP-Proxy",  # 节点名称（必须唯一）
                "type": "http",               # 协议类型（核心字段，放首位）
                "server": config["server_domain"],  # 服务器域名（Render分配）
                "port": config["external_port"],    # 外部端口（固定443）
                "username": credentials["username"],  # 认证用户名
                "password": credentials["password"],  # 认证密码
                "tls": True,                  # 启用TLS（Render强制HTTPS）
                "skip-cert-verify": False     # 禁用证书跳过（避免安全风险）
            },
            # SOCKS5代理节点
            {
                "name": "Render-SOCKS5-Proxy",
                "type": "socks5",
                "server": config["server_domain"],
                "port": config["external_port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "udp": True,                  # 支持UDP转发
                "tls": True,                  # 启用TLS加密
                "skip-cert-verify": False
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择",  # 分组名称（无乱码，支持中文/emoji）
                "type": "url-test",    # 按延迟自动选择节点
                "proxies": [           # 关联上述两个节点（名称必须完全匹配）
                    "Render-HTTP-Proxy",
                    "Render-SOCKS5-Proxy"
                ],
                "url": "https://www.gstatic.com/generate_204",  # 延迟测试URL（稳定）
                "interval": 300         # 测试间隔（300秒=5分钟）
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 自动选择",  # 谷歌域名走代理
            "DOMAIN-SUFFIX,youtube.com,🚀 自动选择", # YouTube走代理
            "GEOIP,CN,DIRECT",  # 国内IP直连
            "MATCH,🚀 自动选择"  # 剩余流量走代理
        ]
    }

# ------------------------------
# 5. Clash订阅接口（Base64编码）
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    """生成Clash订阅链接（Base64编码的YAML配置）"""
    try:
        # 生成标准Clash配置
        clash_config = _generate_clash_config()
        # 转换为YAML格式（修复缩进、保留中文、固定顺序）
        yaml_config = yaml.dump(
            clash_config,
            allow_unicode=True,      # 保留中文和emoji（关键！避免乱码）
            default_flow_style=False,  # 禁用流式格式（强制换行显示）
            sort_keys=False,          # 保持字段定义顺序（避免Clash解析失败）
            indent=2                  # 缩进2空格（YAML标准格式）
        )
        # Base64编码（Clash订阅要求）
        base64_config = b64encode(yaml_config.encode()).decode()
        # 返回订阅内容
        response = make_response(base64_config)
        response.headers["Content-Type"] = "text/plain"
        response.headers["Subscription-Userinfo"] = "upload=0; download=0; total=10737418240; expire=0"  # 流量信息（可选）
        return response
    except Exception as e:
        app.logger.error(f"生成订阅配置失败：{str(e)}")
        return "订阅配置生成失败，请查看服务日志", 500

# ------------------------------
# 6. 原始YAML配置接口（调试用）
# ------------------------------
@app.route('/clash/raw')
def clash_raw():
    """返回未编码的原始YAML配置（用于调试格式问题）"""
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
    """返回当前认证信息（用户名/密码/服务器域名）"""
    return jsonify({
        "username": credentials["username"],
        "password": credentials["password"],
        "server_domain": config["server_domain"],
        "external_port": config["external_port"],
        "generated_at": credentials["generated_at"]
    })

# ------------------------------
# 8. HTTP代理实现（处理HTTPS请求转发）
# ------------------------------
@app.route('/proxy', methods=['CONNECT'])
def http_proxy():
    """处理HTTPS代理请求（通过Render 443端口转发）"""
    # 验证Basic Auth
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return make_response("Unauthorized", 401, {"WWW-Authenticate": "Basic realm='Proxy Service'"})
    
    # 解析用户名密码
    try:
        auth_bytes = b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode().split(':')
    except:
        return make_response("Invalid Authentication", 401)
    
    if username != credentials["username"] or password != credentials["password"]:
        return make_response("Invalid Credentials", 401)
    
    # 转发HTTPS请求
    try:
        target_host, target_port = request.headers['Host'].split(':')
        target_port = int(target_port)
        
        # 连接目标服务器
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((target_host, target_port))
            # 返回连接成功响应
            response = make_response("200 Connection Established\r\n\r\n")
            response.status_code = 200
            
            # 双向转发数据（使用协程提高性能）
            def forward(source, dest):
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    dest.sendall(data)
            
            threading.Thread(target=forward, args=(request.stream, sock), daemon=True).start()
            threading.Thread(target=forward, args=(sock, request.stream), daemon=True).start()
            
            return response
    except Exception as e:
        app.logger.error(f"HTTP代理错误：{str(e)}")
        return make_response("Bad Gateway", 502)

# ------------------------------
# 9. SOCKS5代理实现（内部服务）
# ------------------------------
def handle_socks5_authentication(conn):
    """处理SOCKS