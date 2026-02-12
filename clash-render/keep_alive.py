# keep_alive.py
import requests
import time
import threading
import os

def keep_alive():
    """定期访问服务防止休眠"""
    server_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8080")
    
    endpoints = [
        "/",
        "/status",
        "/api/credentials"
    ]
    
    while True:
        try:
            for endpoint in endpoints:
                try:
                    response = requests.get(f"{server_url}{endpoint}", timeout=5)
                    print(f"✅ 保活请求成功: {endpoint} - 状态码: {response.status_code}")
                except Exception as e:
                    print(f"⚠️ 保活请求失败: {endpoint} - 错误: {e}")
            
            # 每5分钟执行一次
            time.sleep(300)
        except Exception as e:
            print(f"❌ 保活循环错误: {e}")
            time.sleep(60)

if __name__ == "__main__":
    print("🚀 启动保活服务...")
    keep_alive()