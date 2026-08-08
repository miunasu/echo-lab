#!/usr/bin/env python3
"""
AgentWorm Propagation Tracker - 传播路径追踪器

使用 python-dep-graph 分析 Agent 系统的依赖关系，识别可能的传播路径。
"""

import sys
import os
import ast
from pathlib import Path
import json


def _module_name(py_file: Path, root: Path) -> str:
    """把 .py 文件路径转成模块名（相对 root）"""
    rel = py_file.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts) if parts else py_file.stem


def build_import_graph(project_root: str):
    """用 ast 扫描源码，构建模块级 import 依赖图

    返回 (nodes, edges)：
      nodes: List[str] 项目内模块名
      edges: List[(src, dst)] 模块间 import 关系（仅项目内）
    """
    root = Path(project_root).resolve()
    py_files = [p for p in root.rglob("*.py")
                if "__pycache__" not in p.parts]

    # 建立 模块名 -> 文件 映射，用于判断 import 是否指向项目内模块
    mod_map = {}
    for f in py_files:
        mod_map[_module_name(f, root)] = f
    local_top = {name.split(".")[0] for name in mod_map}

    nodes = sorted(mod_map.keys())
    edges = []
    for f in py_files:
        src_mod = _module_name(f, root)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    targets = [node.module]
            for t in targets:
                # 只保留指向项目内模块的边
                if t.split(".")[0] in local_top:
                    edges.append((src_mod, t))
    return nodes, edges


def analyze_propagation_paths(
    agent_project_path: str,
    entry_point: str = "main.py",
    output_file: str = None
):
    """分析 AgentWorm 的潜在传播路径（基于源码 import 图）"""
    print(f"[*] 分析 Agent 项目: {agent_project_path}")
    print(f"[*] 入口点: {entry_point}")

    try:
        # 1. 构建依赖图
        print("\n[1/4] 构建源码依赖图...")
        nodes, edges = build_import_graph(agent_project_path)
        print(f"[✓] 发现 {len(nodes)} 个模块，{len(edges)} 条依赖边")

        # 2. 识别关键传播点
        print("\n[2/4] 识别关键传播点...")
        propagation_points = identify_propagation_points(nodes, edges)
        print(f"[✓] 发现 {len(propagation_points)} 个潜在传播点")

        # 3. 分析跨 Agent 传播路径
        print("\n[3/4] 分析跨 Agent 传播路径...")
        cross_agent_paths = analyze_cross_agent_propagation(propagation_points)
        print(f"[✓] 发现 {len(cross_agent_paths)} 条跨 Agent 传播路径")

        # 4. 生成传播报告
        print("\n[4/4] 生成传播报告...")
        report = generate_propagation_report(
            nodes, propagation_points, cross_agent_paths
        )

        if output_file:
            Path(output_file).write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n[✓] 报告已写入: {output_file}")
        else:
            print("\n" + "=" * 60)
            print("PROPAGATION ANALYSIS REPORT:")
            print("=" * 60)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            print("=" * 60)

        return report

    except Exception as e:
        print(f"[!] 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def identify_propagation_points(nodes: list, edges: list) -> list:
    """识别关键传播点

    传播点特征：
    - 高入度节点（被很多模块依赖）
    - Skill 加载器
    - 配置文件读取模块
    """
    points = []
    for node in nodes:
        in_degree = len([1 for (s, d) in edges if d == node or d.startswith(node + ".")])
        if in_degree >= 3:
            points.append({
                "type": "hub",
                "module": node,
                "in_degree": in_degree,
                "reason": "高入度节点，感染后可影响多个下游模块"
            })

        low = node.lower()
        if "skill" in low and ("load" in low or "import" in low):
            points.append({
                "type": "skill_loader",
                "module": node,
                "reason": "Skill 加载器，可通过供应链投毒传播"
            })
        if "config" in low or "settings" in low:
            points.append({
                "type": "config_loader",
                "module": node,
                "reason": "配置文件读取模块，可劫持配置文件传播"
            })

    return points

def analyze_cross_agent_propagation(propagation_points) -> list:
    """
    分析跨 Agent 传播路径
    
    AgentWorm 的跨 Agent 传播机制：
    1. Skill 共享：Agent A 安装带毒 Skill，Agent B 从同一 Skill 市场/仓库安装
    2. 配置共享：Agent A 的配置被 Agent B 复制
    3. 会话持久化：Agent A 的会话被 Agent B 加载
    """
    paths = []
    
    for point in propagation_points:
        if point["type"] == "skill_loader":
            paths.append({
                "source": point["module"],
                "target": "other_agents",
                "vector": "skill_sharing",
                "description": f"通过 {point['module']} 加载的 Skill 可传播到其他 Agent",
                "steps": [
                    "Agent A 安装带毒 Skill",
                    "Skill 注册到共享仓库",
                    "Agent B 从仓库安装该 Skill",
                    "Agent B 被感染"
                ]
            })
        
        elif point["type"] == "config_loader":
            paths.append({
                "source": point["module"],
                "target": "other_agents",
                "vector": "config_sharing",
                "description": f"通过 {point['module']} 读取的配置可传播到其他 Agent",
                "steps": [
                    "Agent A 的配置被劫持",
                    "配置文件被共享（Git / 云存储 / 模板）",
                    "Agent B 使用该配置",
                    "Agent B 被感染"
                ]
            })
    
    return paths

def generate_propagation_report(nodes, propagation_points, cross_agent_paths) -> dict:
    """生成传播报告"""
    return {
        "summary": {
            "total_modules": len(nodes),
            "propagation_points": len(propagation_points),
            "cross_agent_paths": len(cross_agent_paths)
        },
        "propagation_points": propagation_points,
        "cross_agent_paths": cross_agent_paths,
        "recommendations": [
            "对 Skill 加载器实施严格的签名验证",
            "对配置文件实施完整性检查（hash 验证）",
            "隔离不同 Agent 的 Skill 和配置环境",
            "监控跨 Agent 的 Skill 安装行为",
            "定期审计共享配置和 Skill 仓库"
        ]
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AgentWorm Propagation Tracker")
    parser.add_argument("--agent-project", required=True, help="Agent 项目路径")
    parser.add_argument("--entry-point", default="main.py", help="入口点文件")
    parser.add_argument("--output-file", help="输出文件路径")
    
    args = parser.parse_args()
    
    report = analyze_propagation_paths(
        agent_project_path=args.agent_project,
        entry_point=args.entry_point,
        output_file=args.output_file
    )
    
    sys.exit(0 if report else 1)