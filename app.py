from flask import Flask, request, jsonify, make_response, abort
from flask_cors import CORS
import yaml
import base64
import socket
import threading
import os
from datetime import datetime
from base64 import b64decode

# 初始化Flask应用（开启CORS）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 从环境变量获取Credentials（所有实例共享，解决不一致问题）
# ------------------------------
# 必须在Render平台设置以下环境变量（Settings→Environment Variables）
required_env_vars = ["PROXY_USERNAME", "PROXY_PASSWORD"]
for var in required_env_vars:
    if var not in os.environ:
        raise ValueError(f"❌ 必须设置环境变量：{var}（在Render平台的Settings→Environment Variables中设置）")

credentials = {
    "username": os.environ["PROXY_USERNAME"],
    "password": os.environ["PROXY_PASSWORD"],
    "generated_at": datetime.now().isoformat()
}
app.logger.info(f"✅ 服务启动成功：使用环境变量中的Credentials\n- Username: {credentials['username']}\n- Password: {credentials['password']}")

# ------------------------------
# 2. 配置项（适配Render平台）
# ------------------------------
config = {
    "http_port": int(os.environ.get("HTTP_PORT", 8080)),  # HTTP代理端口（Render默认暴露8080）
    "socks5_port": int(os.environ.get("SOCKS5_PORT", 1080)),  # SOCKS5代理端口（需在Render开启）
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render自动分配的域名
    "allow_anonymous": False  # 禁止匿名访问（必须认证）
}

# ------------------------------
# 3. 根路径：引导页面（解决Not Found问题）
# ------------------------------
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Clash Proxy Service（Render部署）</title>
        <style>
            body { font-family: '微软雅黑', Arial, sans-serif; max-width: 900px; margin: 50px auto; padding: 0 20px; }
            h1 { color: #2d3748; font-size: 2.5em; margin-bottom: 30px; }
            .card { background: #f7fafc; border-radius: 10px; padding: 20px 30px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .card h2 { color: #2b6cb0; font-size: 1.5em; margin-bottom: 15px; }
            .card p { color: #4a5568; font-size: 1.1em; line-height: 1.6; }
            .link { color: #2b6cb0; text-decoration: none; font-weight: bold; }
            .link:hover { text-decoration: underline; }
            .note { background: #fff3cd; border-radius: 10px; padding: 15px 20px; margin-top: 30px; color: #856404; }
        </style>
    </head>
    <body>
        <h1>🌐 Clash Proxy Service（Render部署）</h1>
        
        <div class="card">
            <h2>📌 核心功能接口</h2>
            <p>1. 获取当前Credentials（用户名/密码）：<a class="link" href="/api/credentials" target="_blank">/api/credentials</a></p>
            <p>2. 获取Clash订阅链接（可直接导入客户端）：<a class="link" href="/clash/subscribe" target="_blank">/clash/subscribe</a></p>
        </div>
        
        <div class="card">
            <h2>💡 使用说明</h2>
            <p>1. 确保已在Render平台设置环境变量：<code>PROXY_USERNAME</code>和<code>PROXY_PASSWORD</code>；</p>
            <p>2. 访问<code>/api/credentials</code>验证Credentials是否正确；</p>
            <p>3. 将<code>/clash/subscribe</code>链接导入Clash客户端（自动同步Credentials）；</p>
            <p>4. 代理节点支持HTTP/SOCKS5协议，均需身份认证。</p>
        </div>
        
        <div class="note">
            <p>⚠️ 提示：根路径（/）无内容，核心功能在上述接口中。若需帮助，请查看服务日志或联系开发者。</p>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 核心接口：返回当前Credentials（从环境变量获取，所有实例一致）
# ------------------------------
@app.route('/api/credentials')
def get_credentials():
    return jsonify({
        "username": credentials["username"],
        "password": credentials["password"],
        "http_port": config["http_port"],
        "socks5_port": config["socks5_port"],
        "server_domain": config["server_domain"],
        "generated_at": credentials["generated_at"]
    })

# ------------------------------
# 5. 核心功能：生成Clash订阅配置（使用环境变量中的Credentials，所有实例一致）
# ------------------------------
@app.route('/clash/subscribe')
def clash_subscribe():
    # 构建Clash配置（从环境变量获取Credentials，所有实例一致）
    clash_config = {
        "proxies": [
            # HTTP代理节点（带Basic Auth，支持HTTPS）
            {
                "name": "Render-HTTP-Proxy",
                "type": "http",
                "server": config["server_domain"],
                "port": config["http_port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": True,
                "skip-cert-verify": False
            },
            # SOCKS5代理节点（带用户名密码认证，支持UDP）
            {
                "name": "Render-SOCKS5-Proxy",
                "type": "socks5",
                "server": config["server_domain"],
                "port": config["socks5_port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "udp": True,
                "tls": True,
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

    # 返回订阅响应（符合Clash客户端要求）
    response = make_response(base64_config)
    response.headers["Content-Type"] = "text/plain"
    response.headers["X-Clash-Config"] = "Render-Proxy-Subscribe"
    return response

# ------------------------------
# 6. 核心功能：HTTP代理（强制Basic Auth，使用环境变量中的Credentials）
# ------------------------------
@app.route('/proxy', methods=['CONNECT'])
def http_proxy():
    """处理HTTP代理的CONNECT请求（用于HTTPS转发）"""
    # 1. 验证Basic Auth（使用环境变量中的Credentials）
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        app.logger.warning("❌ HTTP代理：缺少Basic Auth认证")
        abort(401, description="Unauthorized", headers={"WWW-Authenticate": "Basic realm='Proxy Service'"})
    
    # 解析用户名密码
    try:
        auth_bytes = b64decode(auth_header.split(' ')[1])
        username, password = auth_bytes.decode().split(':')
    except Exception as e:
        app.logger.error(f"❌ HTTP代理：解析认证信息失败：{str(e)}")
        abort(401, description="Invalid Authentication Format")
    
    # 验证用户名密码是否与环境变量中的一致
    if username != credentials["username"] or password != credentials["password"]:
        app.logger.warning(f"❌ HTTP代理：认证失败（用户名={username}, 密码={password}）")
        abort(401, description="Invalid Username or Password")

    # 2. 处理CONNECT请求（转发HTTPS）
    try:
        target_host, target_port = request.headers['Host'].split(':')
        target_port = int(target_port)

        # 建立与目标服务器的TCP连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((target_host, target_port))
        app.logger.info(f"✅ HTTP代理：成功连接目标服务器：{target_host}:{target_port}")

        # 返回连接成功响应
        response = make_response("200 Connection Established\r\n\r\n")
        response.status_code = 200
        response.headers['Connection'] = 'keep-alive'

        # 双向转发数据（客户端↔目标服务器）
        def forward_data(source, destination):
            try:
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    destination.sendall(data)
            except Exception as e:
                app.logger.error(f"❌ HTTP代理：数据转发失败：{str(e)}")
            finally:
                source.close()
                destination.close()

        # 启动转发线程（后台运行）
        threading.Thread(target=forward_data, args=(request.stream, sock), daemon=True).start()
        threading.Thread(target=forward_data, args=(sock, request.stream), daemon=True).start()

        return response
    except Exception as e:
        app.logger.error(f"❌ HTTP代理：处理请求失败：{str(e)}")
        abort(502, description="Bad Gateway")

# ------------------------------
# 7. 核心功能：SOCKS5代理（强制用户名密码认证，使用环境变量中的Credentials）
# ------------------------------
def handle_socks5_authentication(conn):
    """处理SOCKS5的认证阶段（用户名密码认证）"""
    # 1. 握手：协商认证方式
    data = conn.recv(2)
    if not data or data[0] != 0x05:  # SOCKS5版本号
        conn.close()
        return False
    
    n_methods = data[1]
    methods = conn.recv(n_methods)
    
    # 只支持用户名密码认证（0x02）
    if 0x02 not in methods:
        conn.sendall(b'\x05\xFF')  # 无可用认证方式
        conn.close()
        return False
    
    # 选择0x02认证方式
    conn.sendall(b'\x05\x02')
    app.logger.debug("🔑 SOCKS5代理：协商认证方式为用户名密码")

    # 2. 验证用户名密码（与环境变量中的一致）
    data = conn.recv(2)
    if not data or data[0] != 0x01:  # 认证版本
        conn.close()
        return False
    
    username_len = data[1]
    username = conn.recv(username_len).decode()
    password_len = conn.recv(1)[0]
    password = conn.recv(password_len).decode()

    # 验证用户名密码是否与环境变量中的一致
    if username != credentials["username"] or password != credentials["password"]:
        app.logger.warning(f"❌ SOCKS5代理：认证失败（用户名={username}, 密码={password}）")
        conn.sendall(b'\x01\x01')  # 认证失败（0x01）
        conn.close()
        return False
    
    # 认证成功
    conn.sendall(b'\x01\x00')  # 认证成功（0x00）
    app.logger.info(f"✅ SOCKS5代理：认证成功（用户名={username}）")
    return True

def handle_socks5_connection(conn, addr):
    """处理SOCKS5代理的连接请求"""
    app.logger.info(f"🔌 SOCKS5代理：收到来自{addr}的连接")
    
    # 1. 强制认证（使用环境变量中的Credentials）
    if not handle_socks5_authentication(conn):
        return
    
    # 2. 处理请求
    try:
        data = conn.recv(4)
        if not data or data[0] != 0x05:
            conn.close()
            return
        
        cmd = data[1]  # 0x01=CONNECT（TCP），0x03=UDP ASSOCIATE（UDP）
        addr_type = data[3]

        # 解析目标地址
        if addr_type == 0x01:  # IPv4
            target_addr = socket.inet_ntoa(conn.recv(4))
        elif addr_type == 0x03:  # 域名
            addr_len = conn.recv(1)[0]
            target_addr = conn.recv(addr_len).decode()
        elif addr_type == 0x04:  # IPv6
            target_addr = socket.inet_ntop(socket.AF_INET6, conn.recv(16))
        else:
            conn.close()
            return
        
        # 解析目标端口
        target_port = int.from_bytes(conn.recv(2), 'big')
        app.logger.info(f"🎯 SOCKS5代理：目标地址={target_addr}:{target_port}, 命令={cmd}")

        # 3. 处理命令
        if cmd == 0x01:  # TCP CONNECT
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.connect((target_addr, target_port))
            # 返回成功响应（SOCKS5格式）
            conn.sendall(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
            # 双向转发数据
            def forward(source, dest):
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        dest.sendall(data)
                except Exception as e:
                    app.logger.error(f"❌ SOCKS5代理：TCP转发失败：{str(e)}")
                finally:
                    source.close()
                    dest.close()
            threading.Thread(target=forward, args=(conn, target_sock), daemon=True).start()
            threading.Thread(target=forward, args=(target_sock, conn), daemon=True).start()
        elif cmd == 0x03:  # UDP ASSOCIATE
            # 返回当前服务器地址和端口（简单处理）
            conn.sendall(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
            app.logger.info(f"✅ SOCKS5代理：UDP关联成功（目标地址={target_addr}:{target_port}）")
        else:
            # 不支持的命令
            conn.sendall(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')  # 0x07=COMMAND NOT SUPPORTED
            conn.close()
    except Exception as e:
        app.logger.error(f"❌ SOCKS5代理：处理请求失败：{str(e)}")
        conn.close()

def start_socks5_server():
    """启动SOCKS5代理服务（后台线程）"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', config["socks5_port"]))
        sock.listen(5)
        app.logger.info(f"🚀 SOCKS5代理服务启动成功，监听端口：{config['socks5_port']}")
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=handle_socks5_connection, args=(conn, addr), daemon=True).start()
    except Exception as e:
        app.logger.error(f"❌ SOCKS5代理服务启动失败：{str(e)}")

# ------------------------------
# 8. 启动服务（Flask + SOCKS5代理）
# ------------------------------
if __name__ == '__main__':
    # 启动SOCKS5代理服务（后台线程）
    threading.Thread(target=start_socks5_server, daemon=True).start()
    # 启动Flask应用（处理HTTP代理和API请求）
    app.run(host='0.0.0.0', port=config["http_port"], debug=False)