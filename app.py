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

# 初始化Flask应用（开启CORS，允许跨域访问）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 固定认证信息（从环境变量获取）
# ------------------------------
def generate_random_string(length: int = 8) -> str:
    """生成随机字符串（用于环境变量未设置时的默认值）"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# 从环境变量获取认证信息（优先使用环境变量，无则生成默认值）
credentials = {
    "username": os.environ.get("PROXY_USERNAME", generate_random_string()),
    "password": os.environ.get("PROXY_PASSWORD", generate_random_string(12)),
    "generated_at": datetime.now().isoformat(),
    "source": "environment" if "PROXY_USERNAME" in os.environ else "default"
}

# 打印认证信息（方便部署时查看）
app.logger.info(f"✅ 认证信息加载成功：\n- 用户名: {credentials['username']}\n- 密码: {credentials['password']}\n- 来源: {credentials['source']}")

# ------------------------------
# 2. 基础配置（适配Render平台）
# ------------------------------
config = {
    "http_port": int(os.environ.get("PORT", 8080)),  # Render分配的内部端口（必填）
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render外部域名（自动获取）
    "external_port": 443  # Render外部端口（固定为443，HTTPS）
}

# ------------------------------
# 3. 根页面（显示服务信息，方便用户查看）
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
        <h1>🔰 Clash代理服务（已固定认证信息）</h1>
        
        <div class="card">
            <div class="title">📌 服务信息</div>
            <div class="info">• 服务器域名：<span class="code">{config['server_domain']}</span></div>
            <div class="info">• 外部端口：<span class="code">{config['external_port']}</span></div>
            <div class="info">• 状态：<span style="color: green;">运行中</span></div>
        </div>
        
        <div class="card">
            <div class="title">🔑 认证信息（固定）</div>
            <div class="info">• 用户名：<span class="code">{credentials['username']}</span></div>
            <div class="info">• 密码：<span class="code">{credentials['password']}</span></div>
            <div class="info">• 生成时间：<span class="code">{credentials['generated_at']}</span></div>
            <div class="info">• 来源：<span class="code">{credentials['source']}</span></div>
            <div class="note">提示：若需修改认证信息，请在Render控制台设置环境变量（PROXY_USERNAME/PROXY_PASSWORD）。</div>
        </div>
        
        <div class="card">
            <div class="title">📥 订阅链接</div>
            <div class="info">• 原始YAML（调试用）：<a href="/clash/raw" target="_blank" class="code">/clash/raw</a></div>
            <div class="info">• Base64订阅（Clash用）：<a href="/clash/subscribe" target="_blank" class="code">/clash/subscribe</a></div>
            <div class="note">提示：将订阅链接复制到Clash客户端（从URL导入）即可使用。</div>
        </div>
        
        <div class="card">
            <div class="title">⚠️ 注意事项</div>
            <div class="info">1. 请使用Clash官方客户端（如Clash for Windows）导入订阅；</div>
            <div class="info">2. 若节点无法连接，请检查网络是否允许访问443端口；</div>
            <div class="info">3. 环境变量设置后，需重启Render服务生效。</div>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 生成Clash配置（用于/raw和/subscribe接口）
# ------------------------------
def _generate_clash_config() -> dict:
    """生成符合Clash规范的YAML配置（包含HTTP代理节点）"""
    return {
        "proxies": [
            {
                "name": "Render-HTTP-Proxy",  # 代理节点名称（唯一）
                "type": "http",  # 代理类型（HTTP）
                "server": config["server_domain"],  # 代理服务器域名（Render外部域名）
                "port": config["external_port"],  # 代理端口（固定443）
                "username": credentials["username"],  # 认证用户名（来自环境变量）
                "password": credentials["password"],  # 认证密码（来自环境变量）
                "tls": True,  # 启用TLS（Render强制HTTPS）
                "skip-cert-verify": False  # 不跳过证书验证（安全起见）
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择",  # 代理分组名称（用户可见）
                "type": "url-test",  # 分组类型（URL延迟测试）
                "proxies": ["Render-HTTP-Proxy"],  # 关联的代理节点（需与proxies中的name一致）
                "url": "https://www.gstatic.com/generate_204",  # 延迟测试URL（谷歌公共服务）
                "interval": 300  # 测试间隔（5分钟）
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 自动选择",  # 谷歌域名走自动选择
            "DOMAIN-SUFFIX,youtube.com,🚀 自动选择",  # YouTube域名走自动选择
            "GEOIP,CN,DIRECT",  # 国内IP直连（节省代理流量）
            "MATCH,🚀 自动选择"  # 其他所有流量走自动选择
        ]
    }

# ------------------------------
# 5. Clash原始YAML接口（/clash/raw，调试用）
# ------------------------------
@app.route('/clash/raw')
def clash_raw():
    """返回未编码的原始YAML配置（方便调试）"""
    try:
        clash_config = _generate_clash_config()
        # 将配置转换为YAML字符串（保留中文、固定缩进）
        yaml_content = yaml.dump(
            clash_config,
            allow_unicode=True,  # 保留中文（如分组名称中的"🚀 自动选择"）
            default_flow_style=False,  # 禁用流式格式（保持YAML结构清晰）
            sort_keys=False,  # 不排序字段（保持配置顺序）
            indent=2  # 缩进2空格（YAML标准）
        )
        # 返回YAML内容（设置正确的Content-Type）
        response = make_response(yaml_content)
        response.headers["Content-Type"] = "text/yaml; charset=utf-8"
        return response
    except Exception as e:
        app.logger.error(f"生成原始YAML失败：{str(e)}")
        return "内部服务器错误", 500

# ------------------------------
# 6. Clash订阅接口（/clash/subscribe，Base64编码）
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    """返回Base64编码的Clash订阅内容（符合Clash客户端要求）"""
    try:
        clash_config = _generate_clash_config()
        # 将配置转换为YAML字符串（同/raw接口）
        yaml_content = yaml.dump(
            clash_config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )
        # 将YAML字符串转换为Base64编码（Clash订阅要求）
        base64_content = base64.b64encode(yaml_content.encode('utf-8')).decode('utf-8')
        # 返回Base64内容（设置正确的Content-Type）
        response = make_response(base64_content)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        # 添加订阅用户信息（可选，部分客户端显示流量使用情况）
        response.headers["Subscription-Userinfo"] = "upload=0; download=0; total=10737418240; expire=0"
        return response
    except Exception as e:
        app.logger.error(f"生成订阅内容失败：{str(e)}")
        return "内部服务器错误", 500

# ------------------------------
# 7. HTTP代理接口（/proxy，处理CONNECT请求）
# ------------------------------
@app.route('/', methods=['CONNECT'])  # 绑定根路径
def http_proxy():
    # 1. 验证Basic Auth（不变）
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return make_response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Proxy Service"'})
    
    # 2. 解析认证信息（不变）
    try:
        auth_bytes = base64.b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode('utf-8').split(':')
    except:
        return make_response("Invalid Authentication", 401)
    
    if username != credentials["username"] or password != credentials["password"]:
        return make_response("Invalid Credentials", 401)
    
    # 3. 解析目标主机和端口（从Host头获取）
    host = request.headers.get('Host')
    if not host:
        return make_response("Bad Request", 400)
    target_host, target_port = host.split(':') if ':' in host else (host, 443)
    target_port = int(target_port)
    
    # 4. 建立与目标服务器的连接（修复异常处理）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)  # 设置超时，避免无限等待
            sock.connect((target_host, target_port))
            # 返回200响应，告知客户端连接成功（必须返回）
            response = make_response("HTTP/1.1 200 Connection Established\r\n\r\n")
            response.status_code = 200
            
            # 5. 双向转发数据（使用非阻塞IO，避免线程问题）
            def forward(source, dest):
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    dest.sendall(data)
            # 启动转发线程（修复daemon=True可能导致线程提前退出的问题）
            threading.Thread(target=forward, args=(request.stream, sock)).start()
            threading.Thread(target=forward, args=(sock, request.stream)).start()
            
            return response
    except Exception as e:
        app.logger.error(f"代理失败：{str(e)}")  # 记录错误到Render日志
        return make_response(f"Proxy Error: {str(e)}", 502)

# ------------------------------
# 8. 启动服务（适配Render平台）
# ------------------------------
if __name__ == '__main__':
    # 启动Flask应用（监听Render分配的端口）
    app.run(
        host='0.0.0.0',  # 监听所有接口（Render要求）
        port=config["http_port"],  # 从环境变量获取端口（Render分配）
        debug=False  # 生产环境禁用debug模式（安全起见）
    )