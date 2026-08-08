# Error Report Generator

基于 Jinja2 的错误报告模板生成工具，用于日志系统测试、错误监控集成，以及对 Sentry / Datadog 等平台的数据格式验证。

## 功能

- 按错误类型生成格式化报告（JSON 或结构化文本）
- 内置多种错误类型：运行时、数据库、API 调用失败、权限、校验、超时、网络、配置
- 报告字段：`timestamp`、`error_type`、`severity`、`message`、`stack_trace`、`context`、可选 `custom_fields`
- 支持 CLI 参数与配置文件覆盖默认值
- 可一次生成多条报告（`--count`）

## 安装

```bash
cd output/error_report_generator
pip install -r requirements.txt
```

## 快速开始

```bash
# 查看支持的错误类型
python log_generator.py --list-types

# 生成运行时错误 JSON 报告
python log_generator.py --type runtime_error --message "Null pointer exception in user_service" --context "{\"user_id\": 123, \"request_path\": \"/api/users\"}"

# 生成文本格式
python log_generator.py --type database_error --format text

# 自定义字段（可重复 --field，或使用 JSON）
python log_generator.py --type api_call_failure --field trace_id=abc123 --field retryable=true --custom-fields "{\"region\": \"us-east-1\"}"

# 写入文件
python log_generator.py --type permission_error -o sample_report.json

# 使用配置文件
python log_generator.py --type timeout_error --config config/default.json
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--type`, `-t` | 错误类型（必填，除非 `--list-types`） |
| `--message`, `-m` | 覆盖错误消息 |
| `--stack-trace` | 覆盖堆栈信息 |
| `--context`, `-c` | 上下文 JSON 对象 |
| `--field key=value` | 自定义字段（可重复；值优先按 JSON 解析） |
| `--custom-fields` | 自定义字段 JSON 对象 |
| `--timestamp` | ISO-8601 时间戳 |
| `--severity` | debug/info/warning/error/critical |
| `--format`, `-f` | `json`（默认）或 `text` |
| `--config` | 配置文件路径 |
| `--output`, `-o` | 输出文件路径 |
| `--count` | 生成条数 |
| `--list-types` | 列出错误类型 |

## 输出示例（JSON）

```json
{
  "timestamp": "2026-08-08T19:00:00Z",
  "error_type": "runtime_error",
  "severity": "error",
  "message": "Null pointer exception in user_service",
  "stack_trace": "  File \"main.py\", line 42...",
  "context": {
    "user_id": 123,
    "request_path": "/api/users"
  },
  "custom_fields": {
    "generator": "log_generator.py",
    "schema_version": "1.0"
  }
}
```

## 项目结构

```text
error_report_generator/
├── log_generator.py          # CLI 与生成逻辑
├── requirements.txt
├── README.md
├── config/
│   └── default.json          # 默认上下文与类型覆盖
├── error_types/
│   ├── __init__.py
│   └── definitions.py        # 错误类型与样例数据
└── templates/
    ├── error_report.json.j2
    └── error_report.text.j2
```

## 配置合并优先级

从低到高：

1. 错误类型内置默认值（`error_types/definitions.py`）
2. 配置文件 `default_context` / `default_custom_fields` / `type_defaults`
3. CLI `--context` / `--custom-fields` / `--field` / `--message` 等显式参数

## 用途建议

- 构造日志管道测试数据
- 验证告警规则与字段映射
- 为 Sentry、Datadog、ELK 等系统准备可重复的错误样例