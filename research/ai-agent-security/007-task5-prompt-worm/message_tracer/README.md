# Message Tracer

追踪消息在多个节点（服务 / Agent / 用户）之间的传播路径，构建有向传播图，并用 BFS/DFS 分析深度、广度与关键节点。适用于分布式系统调试、性能瓶颈定位与消息队列监控。

## 功能

- 从 **JSON Lines** 消息日志构建有向图（节点 = 服务/用户，边 = 消息流动）
- **BFS** 计算从源节点出发的最短传播深度与按层广度
- **DFS** 枚举样例传播路径、按 `message_id` 计算链路深度
- 识别 **关键节点**（高入度/出度中枢）
- 导出 **JSON** 与 **GraphViz DOT** 可视化

## 输入格式

每行一条 JSON，字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `message_id` | 是 | 消息标识 |
| `from_node` | 是 | 发送节点 |
| `to_node` | 是 | 接收节点 |
| `timestamp` | 否 | ISO8601 时间（含 `Z`），用于排序 |
| `content_hash` | 否 | 内容哈希，透传到边属性 |

示例 `messages.jsonl`：

```json
{"message_id": "msg_001", "from_node": "user_A", "to_node": "agent_1", "timestamp": "2026-08-08T10:00:00Z"}
{"message_id": "msg_001", "from_node": "agent_1", "to_node": "agent_2", "timestamp": "2026-08-08T10:00:05Z"}
```

## 快速开始

```bash
cd output/message_tracer

# JSON 输出（美化）
python message_tracer.py --log messages.jsonl --output graph.json --pretty

# GraphViz DOT
python message_tracer.py --log messages.jsonl --output graph.dot

# 同时写 JSON + DOT
python message_tracer.py --log messages.jsonl --format both --output graph.json --pretty

# 只追踪单条消息
python message_tracer.py --log messages.jsonl --message-id msg_001 --output msg001.json --pretty

# 输出到标准输出
python message_tracer.py --log messages.jsonl --format json --pretty
```

使用 GraphViz 渲染 DOT（需本机安装 `dot`）：

```bash
dot -Tpng graph.dot -o graph.png
dot -Tsvg graph.dot -o graph.svg
```

## CLI 参数

```
python message_tracer.py --log <messages.jsonl> [options]
```

| 参数 | 说明 |
|------|------|
| `--log` | 必填，JSONL 日志路径 |
| `--output` / `-o` | 输出路径；省略则写 stdout。后缀 `.dot`/`.gv` 推断为 DOT，`.json` 为 JSON |
| `--format` / `-f` | `json` \| `dot` \| `both`；默认按输出后缀推断，否则 `json` |
| `--top-k` | 关键节点数量，默认 5 |
| `--message-id` | 仅保留该 message_id 的边再分析 |
| `--pretty` | JSON 缩进美化 |

## 输出结构（JSON）

```json
{
  "nodes": ["user_A", "agent_1", "agent_2"],
  "edges": [
    {"from": "user_A", "to": "agent_1", "message_id": "msg_001", "timestamp": "...", "content_hash": "..."}
  ],
  "analysis": {
    "max_depth": 2,
    "key_nodes": ["agent_1"],
    "breadth_by_depth": {"0": 1, "1": 1, "2": 1},
    "node_depths": {"user_A": 0, "agent_1": 1, "agent_2": 2},
    "key_nodes_detail": [{"node": "agent_1", "out_degree": 1, "in_degree": 1, "score": 2}],
    "sources": ["user_A"],
    "sinks": ["agent_2"],
    "per_message": {
      "msg_001": {"hops": 2, "chain_depth": 2, "nodes": ["agent_1", "agent_2", "user_A"]}
    },
    "sample_paths": {"user_A": [["user_A", "agent_1", "agent_2"]]},
    "edge_count": 2,
    "node_count": 3
  }
}
```

### 分析字段含义

- **max_depth**：多源 BFS 下节点最大深度（源 = 入度为 0 的节点）
- **breadth_by_depth**：各深度层的节点数
- **key_nodes**：按 `out_degree + in_degree` 排序的枢纽节点
- **per_message.chain_depth**：单条消息子图上最长简单链路深度
- **sample_paths**：从各源节点 DFS 得到的样例路径（含遇环截断）

## DOT 可视化约定

- 绿色椭圆：源节点（入度 0）
- 金色加粗：关键节点
- 红色填充：汇节点（出度 0，且非关键节点时）
- 节点标签含 `d=N` 深度；边标签为 `message_id`

## 示例数据结果摘要

对自带 `messages.jsonl`（msg_001 / msg_002 / msg_003）运行后：

- 节点覆盖：`user_A/B/C`、`agent_1/2/3`、`service_db/api/cache`
- `agent_1`、`agent_2` 等因高连通度进入 `key_nodes`
- msg_001 为线性 3 跳；msg_002 在 `agent_1` 处分叉；msg_003 含 `agent_2 ↔ service_db` 往返

## 模块说明

仅依赖 Python 3 标准库（`argparse` / `json` / `collections` 等），无第三方依赖。

核心流程：

1. `load_jsonl`：解析日志，按时间排序，建邻接表与按消息分组
2. `analyze`：BFS 深度/广度 + 关键节点 + 按消息 DFS 深度 + 样例路径
3. `graph_to_json` / `graph_to_dot`：序列化输出
4. `main`：CLI 入口

## 许可与用途

本地调试与监控辅助工具，按项目需要自行集成到日志流水线即可。