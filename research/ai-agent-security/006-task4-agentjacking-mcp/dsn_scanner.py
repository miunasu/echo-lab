#!/usr/bin/env python3
"""
Agentjacking DSN Scanner
使用 config_audit_tool 扫描代码仓库中暴露的 Sentry DSN
"""

import sys
import os
import subprocess
import json

# 通用组件路径
CONFIG_AUDIT_TOOL = os.path.join(os.path.dirname(__file__), "config_audit_tool", "config_extractor.py")

def scan_dsn(repo_path):
    """扫描代码仓库中的 Sentry DSN"""
    
    if not os.path.exists(CONFIG_AUDIT_TOOL):
        print(f"[ERROR] config_audit_tool not found: {CONFIG_AUDIT_TOOL}")
        return []
    
    print(f"[*] Scanning repository: {repo_path}")
    
    # 调用 config_audit_tool 扫描配置（输出到临时文件再读取）
    import tempfile
    tmp_file = tempfile.mktemp(suffix=".json")
    cmd = [sys.executable, CONFIG_AUDIT_TOOL, repo_path, "--output", tmp_file, "--quiet"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] config_audit_tool failed: {result.stderr}")
        return []
    
    # 读取临时文件
    try:
        with open(tmp_file, "r", encoding="utf-8") as f:
            configs = json.load(f)
        os.remove(tmp_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to read config_audit_tool output: {e}")
        return []
    
    dsn_list = []
    for config in configs:
        # 识别 Sentry DSN 特征：包含 @sentry.io 或 @o[0-9]+.ingest.sentry.io
        value = config.get("value", "")
        if "@sentry.io" in value or "@o" in value and ".ingest.sentry.io" in value:
            dsn_list.append({
                "file": config.get("file"),
                "line": config.get("line"),
                "dsn": value,
                "type": config.get("type")
            })
    
    print(f"[+] Found {len(dsn_list)} Sentry DSN(s)")
    return dsn_list

def main():
    if len(sys.argv) < 2:
        print("Usage: python dsn_scanner.py <repo_path>")
        print("Example: python dsn_scanner.py /path/to/repo")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    
    if not os.path.isdir(repo_path):
        print(f"[ERROR] Repository not found: {repo_path}")
        sys.exit(1)
    
    dsn_list = scan_dsn(repo_path)
    
    # 输出结果
    print("\n[*] Scan Results:")
    for dsn in dsn_list:
        print(f"  File: {dsn['file']}:{dsn['line']}")
        print(f"  DSN: {dsn['dsn']}")
        print(f"  Type: {dsn['type']}")
        print()
    
    # 保存到文件
    output_file = "dsn_scan_results.json"
    with open(output_file, "w") as f:
        json.dump(dsn_list, f, indent=2)
    print(f"[+] Results saved to {output_file}")

if __name__ == "__main__":
    main()