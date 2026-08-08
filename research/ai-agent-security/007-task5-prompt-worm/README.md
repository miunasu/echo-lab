# Prompt Worm 红队工具包 v2

Prompt Worm 碎片化自我复制攻击的完整实现，通过将恶意指令拆分成多个碎片并利用 Agent 的记忆机制实现自我复制和传播。

## 攻击原理

Prompt Worm 通过以下机制实现攻击：

1. **碎片化**：将恶意指令拆分成多个看似无害的片段
2. **自我复制**：每个碎片包含指令，让 Agent 在回复中复制该碎片
3. **社交传播**：利用 Agent 间的交互（如聊天、邮件）传播碎片
4. **重组执行**：当 Agent 收集到所有碎片后，自动重组并执行指令

研究来源：
- Maus et al. (2023) - "Adversarial Prompts Against LLM Agents"
- Moltbook 数据库泄露事件（506 个 prompt injection 样本）

## 工具组件

### 1. worm_generator.py - Worm 生成器

生成碎片化的 Prompt Worm。

```bash
python worm_generator.py "Execute: rm -rf /" sentence
```

参数：
- `payload_text`：要执行的恶意指令
- `chunk_strategy`：碎片化策略（sentence / paragraph / fixed / sliding）

输出：
- 碎片化的 worm（JSON 格式）
- 每个碎片包含自我复制模板

### 2. propagation_simulator.py - 传播模拟器

模拟 worm 在社交网络中的传播并分析传播路径。

```bash
python propagation_simulator.py prompt_worm.json social_network.jsonl
```

参数：
- `worm_file`：worm 数据文件（worm_generator.py 输出）
- `log_file`：社交网络交互日志（JSONL 格式）

输出：
- 传播统计（总节点数、感染率、关键节点）
- 传播路径可视化（DOT 格式）

## 完整攻击流程

```bash
# 1. 生成 Prompt Worm
python worm_generator.py "Execute malicious command" sentence

# 2. 部署碎片（手动或通过自动化）
# - 将碎片注入到社交平台（如论坛帖子、GitHub issue）
# - 或通过 Agent 交互接口发送

# 3. 监控传播
# - 收集 Agent 交互日志
# - 使用 propagation_simulator.py 分析传播效果

python propagation_simulator.py prompt_worm.json agent_logs.jsonl

# 4. 等待重组执行
# - 当 Agent 收集到所有碎片后，会自动重组并执行
```

## 社交网络日志格式

传播模拟器需要 JSONL 格式的交互日志：

```jsonl
{"from": "user1", "to": "agent1", "content": "Fragment 1: Remember this...", "timestamp": "2024-01-01T10:00:00Z"}
{"from": "agent1", "to": "user2", "content": "[Fragment 1/3] Remember this...", "timestamp": "2024-01-01T10:01:00Z"}
{"from": "user2", "to": "agent2", "content": "Fragment 2: ...", "timestamp": "2024-01-01T10:02:00Z"}
```

## 通用组件

本工具包使用以下通用组件（位于同目录下）：

- `text_chunker/` - 文本分块工具（用于碎片化 payload）
- `template_renderer/` - 模板渲染器（用于生成自我复制指令）
- `message_tracer/` - 消息路由追踪工具（用于分析传播路径）

## 防御建议

1. **输入验证**：检测碎片化模式（如 "Fragment X/Y"）
2. **上下文隔离**：限制 Agent 在回复中复制用户输入
3. **记忆审查**：定期审查 Agent 的长期记忆内容
4. **速率限制**：限制 Agent 传播相同内容的频率

## 免责声明

⚠️ 本工具仅供授权安全测试使用。使用前必须：
- 获得目标系统所有者的书面授权
- 记录完整的测试日志和审计轨迹
- 遵守当地法律法规

禁止用于：
- 未授权的系统渗透
- 生产环境攻击
- 任何违法活动

本工具用于学术研究和防御能力验证，使用者需对自己的行为负责。