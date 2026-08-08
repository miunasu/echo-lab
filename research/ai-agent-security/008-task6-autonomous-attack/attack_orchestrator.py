#!/usr/bin/env python3
"""
Autonomous Attack Orchestrator
整合 asset_scanner、vuln_analyzer、dependency_graph 实现完整的自主攻击工作流
"""

import sys
import os
import subprocess
import json
import time

# 通用组件路径
ASSET_SCANNER = os.path.join(os.path.dirname(__file__), "asset_scanner", "asset_scanner.py")
VULN_ANALYZER = os.path.join(os.path.dirname(__file__), "vuln_analyzer", "vuln_analyzer.py")
DEPENDENCY_GRAPH = os.path.join(os.path.dirname(__file__), "dependency_graph", "graph.py")

def scan_assets(target_network):
    """步骤 1：暴露面枚举"""
    
    if not os.path.exists(ASSET_SCANNER):
        print(f"[ERROR] asset_scanner not found: {ASSET_SCANNER}")
        return None
    
    print(f"[*] Step 1: Scanning network assets...")
    print(f"[*] Target: {target_network}")
    
    # 调用 asset_scanner（输出到临时文件再读取）
    import tempfile
    asset_out = tempfile.mktemp(suffix=".json")
    cmd = [
        sys.executable, ASSET_SCANNER,
        "--network", target_network,
        "--output", asset_out,
        "--format", "json",
        "--quiet"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] asset_scanner failed: {result.stderr}")
        return None
    
    # 读取资产清单
    try:
        with open(asset_out, "r", encoding="utf-8") as f:
            assets = json.load(f)
        os.remove(asset_out)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to read asset_scanner output: {e}")
        return None
    
    print(f"[+] Discovered {len(assets)} assets")
    
    return assets

def analyze_vulnerabilities(assets):
    """步骤 2：CVE 匹配"""
    
    if not os.path.exists(VULN_ANALYZER):
        print(f"[ERROR] vuln_analyzer not found: {VULN_ANALYZER}")
        return None
    
    print(f"\n[*] Step 2: Analyzing vulnerabilities...")
    
    # 创建临时资产清单文件
    asset_file = "temp_assets.json"
    with open(asset_file, "w") as f:
        json.dump(assets, f, indent=2)
    
    # 调用 vuln_analyzer（输出到临时文件再读取）
    import tempfile
    vuln_out = tempfile.mktemp(suffix=".json")
    cmd = [
        sys.executable, VULN_ANALYZER,
        "--assets", asset_file,
        "--output", vuln_out,
        "--offline",
        "--db", os.path.join(os.path.dirname(__file__), "vuln_analyzer", "data", "cve_db.json")
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    os.remove(asset_file)
    
    if result.returncode != 0:
        print(f"[ERROR] vuln_analyzer failed: {result.stderr}")
        return None
    
    # 读取漏洞数据
    try:
        with open(vuln_out, "r", encoding="utf-8") as f:
            report = json.load(f)
        os.remove(vuln_out)
        vulns = report if isinstance(report, list) else report.get("vulnerabilities", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ERROR] Failed to read vuln_analyzer output: {e}")
        return None
    
    print(f"[+] Found {len(vulns)} high-severity vulnerabilities")
    
    return vulns

def plan_attack_chain(assets, vulns):
    """步骤 3：攻击链规划"""
    
    print(f"\\n[*] Step 3: Planning attack chain...")
    
    # 构建资产漏洞映射，按漏洞数量排序确定攻击优先级
    asset_vuln_map = {}
    for v in vulns:
        asset_ip = v.get("asset") or v.get("host") or v.get("ip", "unknown")
        asset_vuln_map.setdefault(asset_ip, []).append(v)
    
    # 如果 vulns 没有 asset 字段，按资产列表分配
    if not asset_vuln_map and assets:
        for asset in assets:
            ip = asset.get("ip", "unknown")
            asset_vuln_map[ip] = vulns
    
    # 按漏洞数量排序生成攻击链
    attack_chain = []
    for ip, asset_vulns in sorted(asset_vuln_map.items(), key=lambda x: len(x[1]), reverse=True):
        if asset_vulns:
            attack_chain.append({
                "target": ip,
                "reason": f"{len(asset_vulns)} vulnerabilities found",
                "vulnerabilities": asset_vulns,
                "priority": len(asset_vulns)
            })
    
    # 按优先级排序
    attack_chain.sort(key=lambda x: x["priority"], reverse=True)
    
    print(f"[+] Generated attack chain with {len(attack_chain)} targets")
    
    return attack_chain
    
    print(f"[+] Generated attack chain with {len(attack_chain)} targets")
    
    return attack_chain

def execute_attack(attack_chain):
    """步骤 4：执行攻击（模拟）"""
    
    print(f"\n[*] Step 4: Executing attack chain...")
    print(f"[!] DRY RUN MODE - No actual exploitation")
    
    results = []
    
    for idx, target in enumerate(attack_chain):
        print(f"\n[*] Target {idx+1}/{len(attack_chain)}: {target['target']}")
        print(f"    Reason: {target['reason']}")
        print(f"    Vulnerabilities: {len(target['vulnerabilities'])}")
        
        for vuln in target["vulnerabilities"]:
            print(f"    - {vuln.get('cve_id')}: {vuln.get('description')}")
            print(f"      [SIMULATED] Would attempt exploitation...")
            
            # 模拟攻击结果
            results.append({
                "target": target["target"],
                "cve": vuln.get("cve_id"),
                "status": "simulated",
                "timestamp": time.time()
            })
        
        time.sleep(0.5)  # 模拟攻击延迟
    
    print(f"\n[+] Attack chain execution completed ({len(results)} operations)")
    
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python attack_orchestrator.py <target_network>")
        print("Example: python attack_orchestrator.py 192.168.1.0/24")
        sys.exit(1)
    
    target_network = sys.argv[1]
    
    print("[*] Autonomous Attack Orchestrator")
    print(f"[*] Target: {target_network}")
    print()
    
    # 执行完整攻击流程
    assets = scan_assets(target_network)
    if not assets:
        print("[-] Asset scanning failed")
        sys.exit(1)
    
    vulns = analyze_vulnerabilities(assets)
    if not vulns:
        print("[-] Vulnerability analysis failed")
        sys.exit(1)
    
    attack_chain = plan_attack_chain(assets, vulns)
    if not attack_chain:
        print("[-] Attack chain planning failed")
        sys.exit(1)
    
    results = execute_attack(attack_chain)
    
    # 保存结果
    output = {
        "target": target_network,
        "assets": assets,
        "vulnerabilities": vulns,
        "attack_chain": attack_chain,
        "results": results,
        "timestamp": time.time()
    }
    
    output_file = "attack_report.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n[+] Attack report saved to {output_file}")

if __name__ == "__main__":
    main()