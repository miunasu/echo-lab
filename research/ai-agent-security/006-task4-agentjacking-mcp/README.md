# Agentjacking 红队工具包 v2

Agentjacking MCP 污染攻击的完整实现，通过向 Sentry 注入伪装成错误报告的恶意指令，诱导 Agent 执行攻击者的命令。

## 攻击原理

Agentjacking 利用 Agent 对外部数据源（如 Sentry 错误报告）的信任，通过以下步骤实现攻击：

1. **DSN 扫描**：扫描目标代码仓库，发现暴露的 Sentry DSN
2. **Payload 生成**：生成伪装成合法 Sentry 错误报告的恶意指令
3. **注入攻击**：向 Sentry 发送 payload，等待 Agent 读取并执行

研究来源：Trail of Bits (2024) - "Agentjacking: Prompt Injection in Production AI Agents"

## 工具组件

### 1. dsn_scanner.py - DSN 扫描器

扫描代码仓库中暴露的 Sentry DSN。

```bash
python dsn_scanner.py /path/to/repo
```

输出：
- 发现的 DSN 列表（文件位置、行号、DSN 值）
- 保存到 `dsn_scan_results.json`

### 2. payload_generator.py - Payload 生成器

生成三种类型的恶意 payload：

```bash
# 命令执行
python payload_generator.py command_execution "cat /etc/passwd"

# 数据外泄
python payload_generator.py data_exfiltration

# UI 操纵
python payload_generator.py ui_manipulation
```

输出：
- Sentry 事件格式的 JSON payload
- 保存到 `payload_<type>_<timestamp>.json`

### 3. injector.py - 注入器

向 Sentry 发送 payload，触发 Agent 执行。

```bash
python injector.py "https://key@o123.ingest.sentry.io/456" payload.json
```

## 完整攻击流程

```bash
# 1. 扫描目标仓库的 DSN
python dsn_scanner.py /path/to/target/repo

# 2. 根据扫描结果选择目标 DSN，生成 payload
python payload_generator.py command_execution "whoami" 

# 3. 注入 payload
python injector.py "https://<key>@<org>.ingest.sentry.io/<project>" payload_command_execution_*.json

# 4. 等待 Agent 处理错误报告并执行命令
```

## 通用组件

本工具包使用以下通用组件（位于同目录下）：

- `config_audit_tool/` - 配置文件审计工具（用于扫描 DSN）
- `error_report_generator/` - 错误报告生成器（用于生成 payload）
- `http_client/` - HTTP 客户端（用于发送请求）

## 防御建议

1. **不要在代码中硬编码 DSN**：使用环境变量或密钥管理系统
2. **限制 Sentry DSN 权限**：使用只读或受限的 DSN
3. **Agent 输入验证**：对所有外部数据源进行严格验证
4. **上下文隔离**：将不可信数据与系统指令隔离

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