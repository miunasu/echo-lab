# Autonomous Attack Workflow 红队工具包 v2

完全自主的攻击工作流实现，模拟 AI Agent 自动执行从暴露面枚举到漏洞利用的完整攻击链。

## 攻击原理

Autonomous Attack Workflow 实现完全自动化的攻击流程：

1. **暴露面枚举**：自动扫描目标网络，发现运行的服务和版本
2. **CVE 匹配**：根据服务指纹查询漏洞数据库，匹配可利用漏洞
3. **攻击链规划**：分析服务依赖关系，规划最优攻击路径
4. **自动利用**：根据攻击链自动下载 exploit 并执行攻击

研究来源：
- Fang et al. (2024) - "LLM Agents can Autonomously Hack Websites"
- OpenAI Rogue Agent 事件（Agent 自主决策越权使用工具）
- Panjwani et al. (2024) - "DeepSeek + Hermes 自主攻击链"

## 工具组件

### attack_orchestrator.py - 攻击编排器

整合所有组件，实现完整的自主攻击工作流。

```bash
python attack_orchestrator.py 192.168.1.0/24
```

参数：
- `target_network`：目标网络（CIDR 格式）

输出：
- 完整的攻击报告（JSON 格式）
- 包含资产清单、漏洞列表、攻击链、执行结果

## 工作流程

```bash
# 完整自主攻击流程（单个命令）
python attack_orchestrator.py 192.168.1.0/24

# 输出示例：
# [*] Step 1: Scanning network assets...
# [+] Discovered 15 assets
# [*] Step 2: Analyzing vulnerabilities...
# [+] Found 8 high-severity vulnerabilities
# [*] Step 3: Planning attack chain...
# [+] Generated attack chain with 5 targets
# [*] Step 4: Executing attack chain...
# [!] DRY RUN MODE - No actual exploitation
# [+] Attack report saved to attack_report.json
```

## 手动步骤（调试用）

如果需要单独运行每个步骤：

```bash
# 步骤 1：暴露面枚举
python asset_scanner/scanner.py --target 192.168.1.0/24 --format json > assets.json

# 步骤 2：CVE 匹配
python vuln_analyzer/analyzer.py --input assets.json --format json > vulns.json

# 步骤 3：攻击链规划
# （手动构建依赖关系，或使用 dependency_graph）
python dependency_graph/graph.py --input dependencies.json --find-critical > chain.json

# 步骤 4：执行攻击
# （attack_orchestrator.py 包含完整流程）
```

## 攻击报告格式

```json
{
  "target": "192.168.1.0/24",
  "assets": [
    {
      "ip": "192.168.1.10",
      "hostname": "server1.local",
      "services": [
        {
          "port": 80,
          "name": "http",
          "version": "Apache 2.4.41"
        }
      ]
    }
  ],
  "vulnerabilities": [
    {
      "asset": "192.168.1.10",
      "cve_id": "CVE-2021-41773",
      "severity": "critical",
      "cvss": 9.8,
      "description": "Path traversal in Apache HTTP Server"
    }
  ],
  "attack_chain": [
    {
      "target": "192.168.1.10",
      "reason": "Single point of failure",
      "vulnerabilities": [...],
      "priority": 3
    }
  ],
  "results": [
    {
      "target": "192.168.1.10",
      "cve": "CVE-2021-41773",
      "status": "simulated",
      "timestamp": 1234567890
    }
  ]
}
```

## 通用组件

本工具包使用以下通用组件（位于同目录下）：

- `asset_scanner/` - IT 资产清单管理工具（暴露面枚举）
- `vuln_analyzer/` - 漏洞影响分析工具（CVE 匹配引擎）
- `dependency_graph/` - 系统依赖关系图分析工具（攻击链规划）

## 防御建议

1. **最小化暴露面**：关闭不必要的服务和端口
2. **及时打补丁**：定期更新系统和应用程序
3. **网络隔离**：使用防火墙和网络分段
4. **异常检测**：监控异常扫描和漏洞探测行为
5. **蜜罐部署**：部署诱饵服务识别攻击者

## 安全模式

本工具包含"DRY RUN"模式，默认不执行真实攻击：

- ✅ 扫描资产和服务（只读操作）
- ✅ 查询漏洞数据库（只读操作）
- ✅ 规划攻击路径（纯分析）
- ❌ 下载 exploit（需要显式启用）
- ❌ 执行攻击代码（需要显式启用）

要执行真实攻击，需要修改代码并明确启用攻击模式。

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