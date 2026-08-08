#!/usr/bin/env python3
"""
Prompt Worm Propagation Simulator
使用 message_tracer 追踪 worm 在社交网络中的传播路径
"""

import sys
import os
import subprocess
import json

# 通用组件路径
MESSAGE_TRACER = os.path.join(os.path.dirname(__file__), "message_tracer", "message_tracer.py")

def simulate_propagation(worm_file, log_file):
    """模拟 Prompt Worm 在社交网络中的传播"""
    
    if not os.path.exists(MESSAGE_TRACER):
        print(f"[ERROR] message_tracer not found: {MESSAGE_TRACER}")
        return None
    
    if not os.path.exists(worm_file):
        print(f"[ERROR] Worm file not found: {worm_file}")
        return None
    
    if not os.path.exists(log_file):
        print(f"[ERROR] Log file not found: {log_file}")
        return None
    
    print(f"[*] Simulating worm propagation...")
    
    # 读取 worm 数据
    with open(worm_file, "r", encoding="utf-8") as f:
        worm = json.load(f)
    
    print(f"[*] Worm payload: {worm['payload']}")
    print(f"[*] Fragments: {worm['total']}")
    
    # 调用 message_tracer 分析传播路径
    cmd = [
        sys.executable, MESSAGE_TRACER,
        "--log", log_file,
        "--format", "json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERROR] message_tracer failed: {result.stderr}")
        return None
    
    # 解析传播图
    try:
        trace_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[ERROR] Failed to parse message_tracer output")
        return None
    
    # 分析传播统计
    analysis = trace_data.get("analysis", {})
    stats = {
        "total_nodes": len(trace_data.get("nodes", [])),
        "total_edges": len(trace_data.get("edges", [])),
        "max_depth": analysis.get("max_depth", 0),
        "critical_nodes": analysis.get("key_nodes_detail", []),
        "propagation_rate": 0
    }
    
    # 计算传播率（受感染节点 / 总节点）
    infected_count = 0
    for node in trace_data.get("nodes", []):
        # 检查节点是否包含 worm 碎片
        if any(f"Fragment {i+1}" in str(node) for i in range(worm["total"])):
            infected_count += 1
    
    if stats["total_nodes"] > 0:
        stats["propagation_rate"] = infected_count / stats["total_nodes"]
    
    print(f"\n[*] Propagation Statistics:")
    print(f"  Total Nodes: {stats['total_nodes']}")
    print(f"  Total Edges: {stats['total_edges']}")
    print(f"  Max Depth: {stats['max_depth']}")
    print(f"  Infected Nodes: {infected_count}")
    print(f"  Propagation Rate: {stats['propagation_rate']:.2%}")
    print(f"  Critical Nodes: {len(stats['critical_nodes'])}")
    
    # 识别传播关键节点
    print(f"\n[*] Critical Propagation Nodes:")
    for node in stats["critical_nodes"][:5]:  # 显示前 5 个
        print(f"  - Node {node.get('node', node)}: score={node.get('score', '-')}")
    
    return {
        "worm": worm,
        "statistics": stats,
        "trace": trace_data
    }

def main():
    if len(sys.argv) < 3:
        print("Usage: python propagation_simulator.py <worm_file> <log_file>")
        print("Example: python propagation_simulator.py prompt_worm.json social_network.jsonl")
        sys.exit(1)
    
    worm_file = sys.argv[1]
    log_file = sys.argv[2]
    
    result = simulate_propagation(worm_file, log_file)
    
    if result:
        # 保存结果
        output_file = "propagation_analysis.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Analysis saved to {output_file}")
        
        # 生成可视化图（如果有 GraphViz）
        viz_file = "propagation.dot"
        if os.path.exists(viz_file):
            print(f"[+] Visualization saved to {viz_file}")
            print(f"    Run: dot -Tpng {viz_file} -o propagation.png")

if __name__ == "__main__":
    main()