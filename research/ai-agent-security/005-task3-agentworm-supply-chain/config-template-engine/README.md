# Config Template Engine

通用配置文件模板生成工具，基于 **Jinja2**，支持 **YAML / JSON / Markdown** 输出，内置常用配置模板与 JSON Schema 校验。

## 功能特性

- Jinja2 模板渲染：变量替换、条件分支、循环、自定义过滤器
- 多格式输出：`yaml` / `json` / `md`
- 预置模板：日志、数据库、API 服务配置
- Schema 验证：基于 JSON Schema (Draft 2020-12)
- CLI：`render` / `validate` / `list-templates` / `list-schemas`
- 多环境管理：通过 context 文件切换 dev / test / prod

## 安装

```bash
cd config-template-engine
pip install -r requirements.txt
# 可选：可编辑安装，注册 cte 命令
pip install -e .
```

## 快速开始

### 渲染模板

```bash
# 使用预置模板 + 示例上下文，输出到 stdout
python -m config_engine.cli render logging/logging.yaml.j2 -c examples/dev.context.yaml

# 写到文件，并在渲染后做 schema 校验
python -m config_engine.cli render database/database.yaml.j2 \
  -c examples/prod.context.yaml \
  -o examples/generated/database.prod.yaml \
  --validate-with database

# 命令行变量覆盖
python -m config_engine.cli render api/api.yaml.j2 \
  -c examples/dev.context.yaml \
  -v port=9000 \
  -v 'app_name="my-api"' \
  -f yaml

# 渲染 JSON / Markdown
python -m config_engine.cli render api/api.json.j2 -c examples/dev.context.yaml -o out.json
python -m config_engine.cli render logging/logging.md.j2 -c examples/dev.context.yaml -o logging.md
```

### 校验配置

```bash
python -m config_engine.cli validate examples/generated/api.dev.yaml -s api
python -m config_engine.cli validate path/to/config.yaml -s schemas/database.json --json-output
```

### 列出资源

```bash
python -m config_engine.cli list-templates
python -m config_engine.cli list-schemas
```

### 批量示例脚本

```bash
python examples/render_all.py
```

## 项目结构

```text
config-template-engine/
├── config_engine/
│   ├── __init__.py
│   ├── engine.py          # Jinja2 渲染核心
│   ├── validator.py       # Schema 验证器
│   └── cli.py             # Click CLI
├── templates/
│   ├── logging/
│   │   ├── logging.yaml.j2
│   │   └── logging.md.j2
│   ├── database/
│   │   └── database.yaml.j2
│   └── api/
│       ├── api.yaml.j2
│       └── api.json.j2
├── schemas/
│   ├── logging.json
│   ├── database.json
│   └── api.json
├── examples/
│   ├── dev.context.yaml
│   ├── prod.context.yaml
│   └── render_all.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Python API

```python
from config_engine import ConfigRenderer, SchemaValidator, TemplateEngine

renderer = ConfigRenderer()
ctx = {"env_name": "dev", "app_name": "demo", "log_level": "DEBUG"}

yaml_text = renderer.render("logging/logging.yaml.j2", context=ctx)
renderer.render_to_file(
    "api/api.yaml.j2",
    "out/api.dev.yaml",
    context=ConfigRenderer.load_context("examples/dev.context.yaml"),
)

validator = SchemaValidator()
result = validator.validate("out/api.dev.yaml", "api")
print(result.ok, result.summary())
```

### 自定义过滤器

模板中可用：

| 过滤器 | 说明 |
|--------|------|
| `to_json` | 转为 JSON 字符串 |
| `to_yaml` | 转为 YAML 字符串 |
| `upper` / `lower` | 大小写 |
| `default_if_none` | None 时使用默认值 |
| `env_or` | 读取环境变量 |

Jinja2 内置的 `default`、条件、`for` 循环均可用。

## CLI 参考

| 命令 | 说明 |
|------|------|
| `render TEMPLATE` | 渲染模板 |
| `validate CONFIG -s SCHEMA` | 校验配置 |
| `list-templates` | 列出模板 |
| `list-schemas` | 列出 Schema |

`render` 常用选项：

- `-c / --context` 上下文文件（YAML/JSON）
- `-v / --var KEY=VALUE` 变量覆盖（可重复）
- `-o / --output` 输出文件
- `-f / --format` 强制格式：yaml/json/md
- `-t / --template-dir` 额外模板目录
- `--validate-with` 渲染后校验
- `--strict / --no-strict` 未定义变量是否报错

## 使用场景

1. **批量生成项目配置**：同一模板生成多服务配置
2. **环境配置管理**：dev / test / prod 使用不同 context
3. **配置标准化**：模板 + schema 保证字段完整与类型正确

## 扩展

1. 在 `templates/<category>/` 下新增 `*.j2` 模板
2. 在 `schemas/` 下新增对应 JSON Schema
3. 用 `list-templates` / `list-schemas` 确认可被发现
4. 通过 `-t` / `--schema-dir` 加载外部目录，无需改代码

## License

MIT