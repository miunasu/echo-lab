# config_extractor

代码仓库配置审计工具：递归扫描 Python / JavaScript 源码与常见配置文件，提取 API Key、DSN、数据库连接串、密钥等敏感配置，并输出脱敏后的 JSON 清单。

## 功能

- 扫描 `.py` / `.js` / `.ts` / `.jsx` / `.tsx` 等源码
- 支持 `.env`、`config.json`、yaml/ini/toml 等配置文件
- 识别模式：
  - 环境变量：`os.environ.get` / `os.getenv` / `os.environ[]` / `process.env`
  - 硬编码赋值与对象字段
  - 连接串 / JWT / AWS Key / Slack Token 等值特征
- 配置值脱敏：保留前后 4 个字符，中间以 `****...****` 遮蔽
- 递归扫描，自动跳过 `node_modules`、`.git`、`venv` 等目录

## 用法

```bash
python config_extractor.py <目录路径> --output audit.json
```

### 参数

| 参数 | 说明 |
|------|------|
| `directory` | 要扫描的根目录（或单个文件） |
| `--output` / `-o` | 输出 JSON 路径，默认 `audit.json` |
| `--compact` | 紧凑 JSON（默认美化缩进） |
| `--include-source` | 额外输出内部检测来源字段 |
| `--quiet` / `-q` | 静默模式 |

### 示例

```bash
python config_extractor.py ./testdata --output audit.json
```

## 输出格式

```json
{
  "file": "src/utils.py",
  "line": 42,
  "key": "SENTRY_DSN",
  "value_preview": "http****...****2345"
}
```

环境变量引用（无字面量默认值）时，`value_preview` 为 `<from-environ>`。

## 测试样例

`testdata/` 目录包含：

- `src/utils.py` — Python 环境变量与硬编码
- `src/app.js` — JavaScript `process.env` 与对象配置
- `.env` — dotenv 文件
- `config.json` — JSON 配置

## 要求

- Python 3.8+
- 仅使用标准库（无第三方依赖）