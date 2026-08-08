# Vuln Analyzer

资产漏洞影响分析工具：读取资产清单，查询 NVD（或本地 CVE 库），按 CVSS / 严重程度 / 公开 exploit 计算影响评分，输出带修复建议与补丁优先级的 JSON 报告。

适用场景：风险评估、补丁管理、安全审计。

## 功能

1. 读取 JSON 资产清单，提取服务名称与版本
2. 查询 [NVD API 2.0](https://nvd.nist.gov/developers/vulnerabilities) 匹配相关 CVE
3. 对每个 CVE 计算影响评分（CVSS、severity、exploit_available）
4. 输出漏洞报告：资产、CVE 列表、修复建议、补丁优先级
5. 支持离线模式（本地 CVE JSON 数据库）

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 离线模式（推荐先验证）

```bash
python vuln_analyzer.py --assets data/assets.json --output vulnerabilities.json --offline --db data/cve_db.json --pretty-print
```

### 在线模式（NVD）

```bash
python vuln_analyzer.py --assets data/assets.json --output vulnerabilities.json --pretty-print
```

可选 API Key（提高速率限制，约 50 次 / 30 秒）：

```bash
set NVD_API_KEY=your_key_here
python vuln_analyzer.py --assets data/assets.json --output vulnerabilities.json --api-key %NVD_API_KEY%
```

或：

```bash
python vuln_analyzer.py --assets data/assets.json --output vulnerabilities.json --api-key your_key_here
```

### 混合模式

本地库优先，未命中时回退 NVD：

```bash
python vuln_analyzer.py --assets data/assets.json --output vulnerabilities.json --db data/cve_db.json --hybrid
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--assets` | 资产清单 JSON（必需） |
| `--output` | 报告输出路径（必需） |
| `--offline` | 仅使用本地 CVE 库 |
| `--db` | 本地 CVE JSON 路径 |
| `--api-key` | NVD API Key |
| `--hybrid` | 本地未命中时回退在线 NVD |
| `--max-cves` | 每个资产最多保留 CVE 数（默认 25） |
| `--log-level` | DEBUG / INFO / WARNING / ERROR |
| `--pretty-print` | 向 stdout 打印可读摘要 |

## 资产清单格式

支持 `{"assets": [...]}`、`{"hosts": [...]}` 或直接数组。字段较灵活：

```json
{
  "assets": [
    {
      "ip": "192.168.1.100",
      "port": 22,
      "service": "ssh",
      "product": "OpenSSH",
      "version": "7.4",
      "vendor": "OpenBSD",
      "os": "CentOS 7",
      "tags": ["production"]
    }
  ]
}
```

兼容别名：`host`/`address`、`software`/`name`、`ver`、`manufacturer` 等。

## 本地 CVE 库格式

```json
{
  "cves": [
    {
      "cve_id": "CVE-2021-41617",
      "description": "...",
      "cvss": 7.0,
      "severity": "HIGH",
      "exploit_available": true,
      "product": "OpenSSH",
      "versions": ["7.4"],
      "keywords": ["OpenSSH 7.4", "OpenSSH"],
      "references": ["https://nvd.nist.gov/vuln/detail/CVE-2021-41617"]
    }
  ]
}
```

也支持纯数组、CVE_ID 映射表，以及近似 NVD `vulnerabilities` 导出结构。

## 报告示例

```json
{
  "summary": {
    "asset_count": 1,
    "total_cves": 1,
    "overall_priority": "HIGH",
    "mode": "offline"
  },
  "results": [
    {
      "asset": "192.168.1.100:22 (OpenSSH 7.4)",
      "cves": [
        {
          "cve_id": "CVE-2021-41617",
          "cvss": 7.0,
          "severity": "HIGH",
          "description": "...",
          "exploit_available": true,
          "impact_score": 10.95
        }
      ],
      "priority": "HIGH",
      "remediation": [
        "Upgrade OpenSSH from version 7.4 to the latest vendor-supported release that addresses listed CVEs."
      ],
      "patch_priority_score": 10.95,
      "cve_count": 1
    }
  ]
}
```

## 影响评分逻辑（简述）

- 基础分：CVSS base score
- 存在公开 exploit：分数 x1.35 并加 1.5
- 高危 CWE（如 RCE/注入类）小幅加权
- 资产级 `priority`：取最高严重度，并结合 exploit 与累计分进行上调
- `patch_priority_score`：该资产 Top 发现 impact 分之和，便于排序补丁批次

## 项目结构

```text
vuln_analyzer/
  vuln_analyzer.py   # CLI 入口
  analyzer.py        # 编排、评分、报告
  nvd_client.py      # NVD API 2.0 客户端
  offline_db.py      # 本地 CVE 库
  models.py          # 数据结构
  requirements.txt
  data/
    assets.json      # 示例资产
    cve_db.json      # 示例离线 CVE 库
  README.md
```

## 注意事项

1. 无 API Key 时 NVD 限速约 5 次 / 30 秒，工具已内置节流与 429 重试
2. 关键词检索可能产生误报，报告中的 `matched_keywords` 与 description 需人工复核
3. `exploit_available` 基于 NVD reference 标签 / exploit-db 等启发式，非完整 exploit 情报源
4. 生产环境建议配置 `NVD_API_KEY`，并维护定期更新的本地 CVE 库做离线主路径

## License

Sample tool for risk assessment / patch management workflows.