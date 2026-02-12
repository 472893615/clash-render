# app.py
from flask import Flask, render_template, request, jsonify, Response, redirect
from flask_cors import CORS
import yaml
import base64
import json
import time
import threading
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# 存储代理信息
proxy_info = {
    "server": os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),
    "port": 8080,
    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "last_accessed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "access_count": 0
}

# 生成用户凭证
import random
import string
username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

# 存储凭证
credentials = {
    "username": username,
    "password": password,
    "generated_at": datetime.now().isoformat()
}

@app.route('/')
def index():
    """Web 界面"""
    proxy_info["access_count"] += 1
    proxy_info["last_accessed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return render_template('index.html', 
                         server=proxy_info["server"],
                         port=proxy_info["port"],
                         username=credentials["username"],
                         password=credentials["password"],
                         access_count=proxy_info["access_count"])

@app.route('/status')
def status():
    """服务状态"""
    return jsonify({
        "status": "running",
        "uptime": str(datetime.now() - datetime.strptime(proxy_info["created_at"], "%Y-%m-%d %H:%M:%S")),
        "access_count": proxy_info["access_count"],
        "last_accessed": proxy_info["last_accessed"],
        "server_info": proxy_info
    })

@app.route('/clash/config')
def clash_config():
    """生成 Clash 配置文件"""
    proxy_info["access_count"] += 1
    
    # 构建 Clash 配置
    clash_config = {
        "port": 7890,
        "socks-port": 7891,
        "redir-port": 7892,
        "mixed-port": 7893,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "0.0.0.0:9090",
        "secret": "",
        "allow-lan": False,
        "proxies": [
            {
                "name": f"Render-Proxy-{proxy_info['server']}",
                "type": "http",
                "server": proxy_info["server"],
                "port": proxy_info["port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "tls": False,
                "skip-cert-verify": True,
                "udp": True
            },
            {
                "name": f"Render-SOCKS5-{proxy_info['server']}",
                "type": "socks5",
                "server": proxy_info["server"],
                "port": proxy_info["port"],
                "username": credentials["username"],
                "password": credentials["password"],
                "udp": True
            }
        ],
        "proxy-groups": [
            {
                "name": "🚀 Render-Proxy",
                "type": "select",
                "proxies": [
                    f"Render-Proxy-{proxy_info['server']}",
                    f"Render-SOCKS5-{proxy_info['server']}",
                    "DIRECT"
                ]
            },
            {
                "name": "🎯 Auto-Select",
                "type": "url-test",
                "proxies": [
                    f"Render-Proxy-{proxy_info['server']}",
                    f"Render-SOCKS5-{proxy_info['server']}"
                ],
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,google.com,🚀 Render-Proxy",
            "DOMAIN-SUFFIX,github.com,🚀 Render-Proxy",
            "DOMAIN-SUFFIX,youtube.com,🚀 Render-Proxy",
            "DOMAIN-SUFFIX,openai.com,🚀 Render-Proxy",
            "DOMAIN-SUFFIX,cloudflare.com,🚀 Render-Proxy",
            "GEOIP,CN,DIRECT",
            "MATCH,🚀 Render-Proxy"
        ]
    }
    
    # 转换为 YAML
    yaml_str = yaml.dump(clash_config, allow_unicode=True, default_flow_style=False)
    
    # 生成订阅链接格式
    encoded_config = base64.b64encode(yaml_str.encode()).decode()
    
    return Response(yaml_str, mimetype='text/plain', 
                    headers={'Content-Disposition': 'attachment; filename="render_clash.yaml"'})

@app.route('/clash/subscribe')
def clash_subscribe():
    """Clash 订阅链接"""
    proxy_info["access_count"] += 1
    
    clash_config_response = clash_config()
    config_yaml = clash_config_response.get_data(as_text=True)
    encoded = base64.b64encode(config_yaml.encode()).decode()
    
    return Response(encoded, mimetype='text/plain')

@app.route('/proxy/<path:url>')
def proxy_request(url):
    """简单的 HTTP 代理"""
    proxy_info["access_count"] += 1
    
    import requests
    from urllib.parse import unquote
    
    try:
        target_url = unquote(url)
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        
        response = requests.get(target_url, timeout=10)
        return Response(response.content, status=response.status_code, 
                       content_type=response.headers.get('content-type'))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/credentials')
def get_credentials():
    """获取代理凭证"""
    proxy_info["access_count"] += 1
    
    return jsonify({
        "server": proxy_info["server"],
        "port": proxy_info["port"],
        "username": credentials["username"],
        "password": credentials["password"],
        "protocols": ["HTTP", "SOCKS5"],
        "clash_config_url": f"http://{proxy_info['server']}/clash/config",
        "clash_subscribe_url": f"http://{proxy_info['server']}/clash/subscribe"
    })

if __name__ == '__main__':
    print(f"🔑 生成的代理凭证:")
    print(f"   服务器: {proxy_info['server']}")
    print(f"   端口: {proxy_info['port']}")
    print(f"   用户名: {credentials['username']}")
    print(f"   密码: {credentials['password']}")
    print(f"   Clash 配置: http://{proxy_info['server']}/clash/config")
    print(f"   订阅链接: http://{proxy_info['server']}/clash/subscribe")
    
    app.run(host='0.0.0.0', port=8080, debug=False)