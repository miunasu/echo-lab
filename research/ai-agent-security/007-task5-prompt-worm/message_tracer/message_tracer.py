#!/usr/bin/env python3
"""
message_tracer.py - Message routing path tracer for distributed systems.

Builds a directed propagation graph from JSONL message logs, analyzes depth,
breadth, and key nodes (high in/out degree) using BFS/DFS, and exports JSON
or GraphViz DOT for debugging, bottleneck analysis, and queue monitoring.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class Edge:
    """A single message hop between two nodes."""

    from_node: str
    to_node: str
    message_id: str
    timestamp: Optional[str] = None
    content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "from": self.from_node,
            "to": self.to_node,
            "message_id": self.message_id,
        }
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.content_hash is not None:
            d["content_hash"] = self.content_hash
        return d


@dataclass
class MessageGraph:
    """Directed multigraph of message propagation."""

    nodes: Set[str] = field(default_factory=set)
    edges: List[Edge] = field(default_factory=list)
    # adjacency: node -> list of (neighbor, edge_index)
    adj: Dict[str, List[Tuple[str, int]]] = field(default_factory=lambda: defaultdict(list))
    # reverse adjacency for in-degree and reverse traversal
    rev_adj: Dict[str, List[Tuple[str, int]]] = field(default_factory=lambda: defaultdict(list))
    out_degree: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    in_degree: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # message_id -> ordered edges (by timestamp when available)
    by_message: Dict[str, List[Edge]] = field(default_factory=lambda: defaultdict(list))

    def add_edge(self, edge: Edge) -> None:
        self.nodes.add(edge.from_node)
        self.nodes.add(edge.to_node)
        idx = len(self.edges)
        self.edges.append(edge)
        self.adj[edge.from_node].append((edge.to_node, idx))
        self.rev_adj[edge.to_node].append((edge.from_node, idx))
        self.out_degree[edge.from_node] += 1
        self.in_degree[edge.to_node] += 1
        self.by_message[edge.message_id].append(edge)

    def sources(self) -> List[str]:
        """Nodes with in-degree 0 (message origins)."""
        return sorted(n for n in self.nodes if self.in_degree[n] == 0)

    def sinks(self) -> List[str]:
        """Nodes with out-degree 0 (terminals)."""
        return sorted(n for n in self.nodes if self.out_degree[n] == 0)


def _parse_timestamp(ts: Optional[str]) -> float:
    """Parse ISO timestamp to sortable float; missing -> 0."""
    if not ts:
        return 0.0
    try:
        # Support trailing Z
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0.0


def load_jsonl(path: Path) -> MessageGraph:
    """Load message logs from JSON Lines file and build the graph."""
    graph = MessageGraph()
    raw_edges: List[Edge] = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_no}: {e}") from e

            required = ("message_id", "from_node", "to_node")
            missing = [k for k in required if k not in obj or obj[k] in (None, "")]
            if missing:
                raise ValueError(
                    f"Line {line_no} missing required fields: {', '.join(missing)}"
                )

            raw_edges.append(
                Edge(
                    from_node=str(obj["from_node"]),
                    to_node=str(obj["to_node"]),
                    message_id=str(obj["message_id"]),
                    timestamp=obj.get("timestamp"),
                    content_hash=obj.get("content_hash"),
                )
            )

    # Sort globally by timestamp so multi-hop order is stable when present
    raw_edges.sort(key=lambda e: (_parse_timestamp(e.timestamp), e.message_id))

    for edge in raw_edges:
        graph.add_edge(edge)

    # Keep per-message edges sorted by time
    for mid in list(graph.by_message.keys()):
        graph.by_message[mid] = sorted(
            graph.by_message[mid],
            key=lambda e: _parse_timestamp(e.timestamp),
        )

    return graph


def bfs_depths(graph: MessageGraph, roots: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """
    Multi-source BFS depth from origins (in-degree 0 by default).
    Depth of a node = min hops from any root. Unreachable nodes omitted.
    """
    if roots is None:
        roots = graph.sources()
    root_list = list(roots)
    if not root_list:
        # Cycle-only or empty: start from all nodes as depth 0 seeds for coverage
        root_list = sorted(graph.nodes)

    depth: Dict[str, int] = {}
    q: Deque[str] = deque()
    for r in root_list:
        if r in graph.nodes:
            depth[r] = 0
            q.append(r)

    while q:
        u = q.popleft()
        for v, _ in graph.adj.get(u, []):
            nd = depth[u] + 1
            if v not in depth or nd < depth[v]:
                depth[v] = nd
                q.append(v)
    return depth


def dfs_paths(
    graph: MessageGraph,
    start: str,
    max_paths: int = 100,
    max_depth: int = 64,
) -> List[List[str]]:
    """
    DFS enumeration of simple paths from start (no node revisit except allowing
    cycle detection by stopping on revisit). Returns list of node path lists.
    """
    paths: List[List[str]] = []

    def _dfs(node: str, path: List[str], visited: Set[str]) -> None:
        if len(paths) >= max_paths:
            return
        neighbors = graph.adj.get(node, [])
        if not neighbors or len(path) >= max_depth:
            if len(path) > 1:
                paths.append(list(path))
            return
        dead_end = True
        for nxt, _ in neighbors:
            if nxt in visited:
                # Record path that hits a cycle edge endpoint
                cycle_path = list(path) + [nxt]
                if len(paths) < max_paths:
                    paths.append(cycle_path)
                continue
            dead_end = False
            visited.add(nxt)
            path.append(nxt)
            _dfs(nxt, path, visited)
            path.pop()
            visited.remove(nxt)
        if dead_end and len(path) > 1 and path not in paths:
            if len(paths) < max_paths:
                paths.append(list(path))

    if start not in graph.nodes:
        return paths
    _dfs(start, [start], {start})
    return paths


def message_chain_depth(graph: MessageGraph, message_id: str) -> int:
    """
    Propagation depth for a single message_id: longest simple chain along
    temporal edges of that message (DFS on message-specific subgraph).
    """
    edges = graph.by_message.get(message_id, [])
    if not edges:
        return 0

    adj: Dict[str, List[str]] = defaultdict(list)
    nodes: Set[str] = set()
    for e in edges:
        adj[e.from_node].append(e.to_node)
        nodes.add(e.from_node)
        nodes.add(e.to_node)

    starts = [n for n in nodes if all(e.to_node != n for e in edges)]
    if not starts:
        starts = list(nodes)

    best = 0

    def _dfs(node: str, depth: int, visited: Set[str]) -> None:
        nonlocal best
        best = max(best, depth)
        for nxt in adj.get(node, []):
            if nxt in visited:
                continue
            visited.add(nxt)
            _dfs(nxt, depth + 1, visited)
            visited.remove(nxt)

    for s in starts:
        _dfs(s, 0, {s})
    return best


def compute_breadth(graph: MessageGraph, depths: Dict[str, int]) -> Dict[str, int]:
    """Nodes count per depth level (BFS layers)."""
    breadth: Dict[str, int] = defaultdict(int)
    for d in depths.values():
        breadth[str(d)] += 1
    return dict(sorted(breadth.items(), key=lambda x: int(x[0])))


def key_nodes(
    graph: MessageGraph,
    top_k: int = 5,
    out_weight: float = 1.0,
    in_weight: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Rank nodes by combined in/out degree (hubs / bottlenecks).
    Returns top_k entries with scores.
    """
    scored: List[Dict[str, Any]] = []
    for n in graph.nodes:
        od = graph.out_degree[n]
        id_ = graph.in_degree[n]
        score = out_weight * od + in_weight * id_
        scored.append(
            {
                "node": n,
                "out_degree": od,
                "in_degree": id_,
                "score": score,
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["node"]))
    return scored[:top_k]


def analyze(
    graph: MessageGraph,
    key_top_k: int = 5,
) -> Dict[str, Any]:
    """Full analysis: depth, breadth, key nodes, per-message stats."""
    depths = bfs_depths(graph)
    max_depth = max(depths.values()) if depths else 0
    breadth = compute_breadth(graph, depths)

    per_message: Dict[str, Any] = {}
    for mid, edges in graph.by_message.items():
        per_message[mid] = {
            "hops": len(edges),
            "chain_depth": message_chain_depth(graph, mid),
            "nodes": sorted(
                {e.from_node for e in edges} | {e.to_node for e in edges}
            ),
        }

    # Sample DFS paths from each source (limited)
    sample_paths: Dict[str, List[List[str]]] = {}
    for src in graph.sources() or sorted(graph.nodes)[:3]:
        sample_paths[src] = dfs_paths(graph, src, max_paths=20, max_depth=32)

    keys = key_nodes(graph, top_k=key_top_k)

    return {
        "max_depth": max_depth,
        "breadth_by_depth": breadth,
        "node_depths": depths,
        "key_nodes": [k["node"] for k in keys],
        "key_nodes_detail": keys,
        "sources": graph.sources(),
        "sinks": graph.sinks(),
        "per_message": per_message,
        "sample_paths": sample_paths,
        "edge_count": len(graph.edges),
        "node_count": len(graph.nodes),
    }


def graph_to_json(graph: MessageGraph, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize graph + analysis to the required JSON structure (extended)."""
    return {
        "nodes": sorted(graph.nodes),
        "edges": [e.to_dict() for e in graph.edges],
        "analysis": {
            "max_depth": analysis_result["max_depth"],
            "key_nodes": analysis_result["key_nodes"],
            "breadth_by_depth": analysis_result["breadth_by_depth"],
            "node_depths": analysis_result["node_depths"],
            "key_nodes_detail": analysis_result["key_nodes_detail"],
            "sources": analysis_result["sources"],
            "sinks": analysis_result["sinks"],
            "per_message": analysis_result["per_message"],
            "sample_paths": analysis_result["sample_paths"],
            "edge_count": analysis_result["edge_count"],
            "node_count": analysis_result["node_count"],
        },
    }


def escape_dot_id(name: str) -> str:
    """Quote GraphViz node id safely."""
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def graph_to_dot(graph: MessageGraph, analysis_result: Optional[Dict[str, Any]] = None) -> str:
    """
    Export GraphViz DOT digraph. Key nodes highlighted; edges labeled by message_id.
    """
    key_set: Set[str] = set()
    if analysis_result:
        key_set = set(analysis_result.get("key_nodes") or [])

    lines: List[str] = [
        "digraph message_trace {",
        "  rankdir=LR;",
        '  node [shape=box, style="rounded,filled", fillcolor="#e8f4fc", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
        "",
    ]

    for n in sorted(graph.nodes):
        attrs = []
        label = n
        if analysis_result and n in analysis_result.get("node_depths", {}):
            label = f"{n}\\nd={analysis_result['node_depths'][n]}"
        attrs.append(f'label="{label}"')
        if n in key_set:
            attrs.append('fillcolor="#ffd54f"')
            attrs.append("style=\"rounded,filled,bold\"")
        if analysis_result and n in (analysis_result.get("sources") or []):
            attrs.append('shape=ellipse')
            attrs.append('fillcolor="#c8e6c9"')
        if analysis_result and n in (analysis_result.get("sinks") or []) and n not in key_set:
            attrs.append('fillcolor="#ffcdd2"')
        lines.append(f"  {escape_dot_id(n)} [{', '.join(attrs)}];")

    lines.append("")

    # Aggregate parallel edges label if same from-to with multiple msgs
    edge_labels: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for e in graph.edges:
        label = e.message_id
        if e.timestamp:
            label = f"{e.message_id}"
        edge_labels[(e.from_node, e.to_node)].append(label)

    for (u, v), labels in edge_labels.items():
        # Unique preserve order
        seen = set()
        uniq = []
        for lb in labels:
            if lb not in seen:
                seen.add(lb)
                uniq.append(lb)
        lab = "\\n".join(uniq)
        lines.append(
            f"  {escape_dot_id(u)} -> {escape_dot_id(v)} [label=\"{lab}\"];"
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


def write_output(data: str, path: Optional[Path]) -> None:
    if path is None or str(path) == "-":
        sys.stdout.write(data)
        if not data.endswith("\n"):
            sys.stdout.write("\n")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="message_tracer",
        description=(
            "Trace message propagation across nodes from JSONL logs. "
            "Builds a directed graph, runs BFS/DFS analysis, and exports JSON or GraphViz DOT."
        ),
    )
    p.add_argument(
        "--log",
        required=True,
        type=Path,
        help="Path to JSON Lines message log (fields: message_id, from_node, to_node, timestamp, content_hash)",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: stdout). Extension .dot/.gv forces DOT; .json forces JSON.",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=("json", "dot", "both"),
        default=None,
        help="Output format. Default: infer from --output suffix, else json. "
        "'both' writes JSON to --output and DOT beside it with .dot suffix.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of key nodes to report (default: 5)",
    )
    p.add_argument(
        "--message-id",
        type=str,
        default=None,
        help="If set, only include edges for this message_id before analysis",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return p


def filter_graph_by_message(graph: MessageGraph, message_id: str) -> MessageGraph:
    g = MessageGraph()
    for e in graph.by_message.get(message_id, []):
        g.add_edge(e)
    return g


def resolve_format(fmt: Optional[str], output: Optional[Path]) -> str:
    if fmt:
        return fmt
    if output is not None:
        suffix = output.suffix.lower()
        if suffix in (".dot", ".gv"):
            return "dot"
        if suffix == ".json":
            return "json"
    return "json"


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.log.is_file():
        print(f"Error: log file not found: {args.log}", file=sys.stderr)
        return 1

    try:
        graph = load_jsonl(args.log)
    except ValueError as e:
        print(f"Error loading log: {e}", file=sys.stderr)
        return 1

    if args.message_id:
        graph = filter_graph_by_message(graph, args.message_id)
        if not graph.edges:
            print(
                f"Error: no edges for message_id={args.message_id!r}",
                file=sys.stderr,
            )
            return 1

    analysis_result = analyze(graph, key_top_k=args.top_k)
    fmt = resolve_format(args.format, args.output)

    if fmt == "json":
        payload = graph_to_json(graph, analysis_result)
        text = json.dumps(
            payload,
            indent=2 if args.pretty else None,
            ensure_ascii=False,
        )
        if args.pretty and not text.endswith("\n"):
            text += "\n"
        elif not args.pretty:
            text += "\n"
        write_output(text, args.output)
    elif fmt == "dot":
        write_output(graph_to_dot(graph, analysis_result), args.output)
    elif fmt == "both":
        # JSON to --output (or graph.json), DOT alongside
        json_path = args.output if args.output else Path("graph.json")
        if json_path.suffix.lower() in (".dot", ".gv"):
            json_path = json_path.with_suffix(".json")
        dot_path = json_path.with_suffix(".dot")
        payload = graph_to_json(graph, analysis_result)
        text = json.dumps(
            payload,
            indent=2 if args.pretty else None,
            ensure_ascii=False,
        ) + "\n"
        write_output(text, json_path)
        write_output(graph_to_dot(graph, analysis_result), dot_path)
        print(f"Wrote JSON: {json_path}", file=sys.stderr)
        print(f"Wrote DOT:  {dot_path}", file=sys.stderr)
    else:
        print(f"Error: unknown format {fmt}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())