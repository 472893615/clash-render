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

# 初始化Flask应用（开启CORS）
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ------------------------------
# 1. 环境变量与Credentials管理
# ------------------------------
def generate_random_string(length: int) -> str:
    """生成随机字符串（默认Credentials）"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# 生成/获取Credentials（环境变量优先）
credentials = {
    "username": os.environ.get("PROXY_USERNAME", generate_random_string(8)),
    "password": os.environ.get("PROXY_PASSWORD", generate_random_string(12)),
    "generated_at": datetime.now().isoformat(),
    "source": "environment" if "PROXY_USERNAME" in os.environ else "default"
}
app.logger.info(f"✅ 服务启动成功：Credentials来源={credentials['source']}\n- Username: {credentials['username']}\n- Password: {credentials['password']}")

# ------------------------------
# 2. 配置项（适配Render平台）
# ------------------------------
config = {
    "http_port": int(os.environ.get("PORT", 8080)),  # Render分配的内部端口
    "socks5_port": 1080,  # 内部SOCKS5端口
    "server_domain": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),  # Render域名（如xxx.onrender.com）
    "external_port": 443  # 外部访问端口（Render仅开放443）
}

# ------------------------------
# 3. 根路径：调试页面（显示订阅链接和手动节点信息）
# ------------------------------
@app.route('/')
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Clash Proxy Debug</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; }}
            .box {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .title {{ color: #2c3e50; font-size: 1.2em; margin-bottom: 10px; }}
            .code {{ background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; }}
            .warning {{ color: #e74c3c; }}
        </style>
    </head>
    <body>
        <h1>🔍 Clash代理调试页面</h1>
        
        <div class="box">
            <div class="title">📌 订阅链接</div>
            <div class="code">
                <a href="/clash/subscribe" target="_blank">https://{config['server_domain']}/clash/subscribe</a>
            </div>
        </div>
        
        <div class="box">
            <div class="title">📝 手动添加节点信息（若订阅失败）</div>
            <div class="code">
                <p>服务器：{config['server_domain']}</p>
                <p>端口：{config['external_port']}（443）</p>
                <p>用户名：{credentials['username']}</p>
                <p>密码：{credentials['password']}</p>
                <p>协议：HTTP / SOCKS5（均启用TLS）</p>
            </div>
        </div>
        
        <div class="box warning">
            <div class="title">⚠️ 订阅链接无效？点击查看原始配置：</div>
            <div class="code">
                <a href="/clash/raw" target="_blank">https://{config['server_domain']}/clash/raw</a>（未编码的YAML配置）
            </div>
        </div>
    </body>
    </html>
    """

# ------------------------------
# 4. 调试接口：返回原始Clash配置（未编码，用于排查格式错误）
# ------------------------------
@app.route('/clash/raw')
def clash_raw():
    """返回未Base64编码的原始YAML配置，用于调试格式问题"""
    clash_config = _generate_clash_config()
    yaml_config = yaml.dump(clash_config, allow_unicode=True, default_flow_style=False)
    response = make_response(yaml_config)
    response.headers["Content-Type"] = "text/yaml"
    return response

# ------------------------------
# 5. 核心功能：生成Clash订阅配置（修复YAML格式和节点信息）
# ------------------------------
def _generate_clash_config():
    """生成标准Clash配置字典（单独抽离，方便调试）"""
    return {
        "proxies": [
            # HTTP代理节点（必须启用TLS，使用443端口）
            {
                "name": "Render-HTTP-Proxy",
                "type": "http",
                "server": config["server_domain"],
                "port": config["external_port"],  # 外部端口443
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": True,  # Render强制HTTPS，必须启用
                "skip-cert-verify": False  # 禁用证书跳过，避免安全风险
            },
            # SOCKS5代理节点（启用TLS和UDP）
            {
                "name": "Render-SOCKS5-Proxy",
                "type": "socks5",
                "server": config["server_domain"],
                "port": config["external_port"],  # 外部端口443
                "username": credentials["username"],
                "password": credentials["password"],
                "udp": True,  # 支持UDP转发
                "tls": True,  # 启用TLS加密
                "skip-cert-verify": False
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 自动选择",  # 分组名称（Clash客户端会显示）
                "type": "url-test",  # 按延迟自动选择节点
                "proxies": ["Render-HTTP-Proxy", "Render-SOCKS5-Proxy"],  # 包含上述两个节点
                "url": "https://www.gstatic.com/generate_204",  # 测试URL（国内可访问）
                "interval": 300  # 测试间隔（秒）
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 自动选择",  # 特定域名走代理
            "DOMAIN-SUFFIX,youtube.com,🚀 自动选择",
            "GEOIP,CN,DIRECT",  # 国内IP直连
            "MATCH,🚀 自动选择"  # 剩余流量走代理
        ]
    }

@app.route('/clash/subscribe')
def clash_subscribe():
    """生成Clash订阅链接（Base64编码的YAML配置）"""
    try:
        # 生成标准Clash配置
        clash_config = _generate_clash_config()
        # 转换为YAML格式（确保中文正常显示）
        yaml_config = yaml.dump(
            clash_config,
            allow_unicode=True,  # 保留中文
            default_flow_style=False,  # 禁用流式风格，确保格式正确
            sort_keys=False  # 保持字典顺序
        )
        # Base64编码（Clash订阅要求）
        base64_config = b64encode(yaml_config.encode()).decode()
        # 返回订阅内容
        response = make_response(base64_config)
        response.headers["Content-Type"] = "text/plain"
        response.headers["Subscription-Userinfo"] = f"upload=0; download=0; total=10737418240; expire=0"  # 可选：流量信息
        return response
    except Exception as e:
        app.logger.error(f"生成订阅配置失败：{str(e)}")
        return "订阅配置生成失败，请查看服务日志", 500

# ------------------------------
# 6. 其他必要接口与服务启动（保持不变，确保代理功能正常）
# ------------------------------
@app.route('/api/credentials')
def get_credentials():
    return jsonify({
        "username": credentials["username"],
        "password": credentials["password"],
        "server_domain": config["server_domain"],
        "external_port": config["external_port"]
    })

# HTTP代理和SOCKS5代理实现（省略，与之前版本一致，确保功能正常）
# ...

if __name__ == '__main__':
    # 启动SOCKS5服务（后台线程）
    threading.Thread(target=start_socks5_server, daemon=True).start()
    # 启动Flask应用
    app.run(host='0.0.0.0', port=config["http_port"], debug=False)