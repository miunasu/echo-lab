# IT Asset Scanner

内网 IT 资产清单管理工具：主机发现、端口扫描、Banner/服务识别、基础操作系统猜测，并导出 JSON/CSV 资产清单。

适用于 IT 资产盘点、配置管理、合规审计。仅使用 Python 标准库（`socket` 等），无需强制安装第三方依赖。

## 功能

1. 扫描内网 IP 段（CIDR），发现活跃主机（ICMP + TCP 探测）
2. 多线程端口扫描（支持端口列表与区间）
3. Banner grabbing 与常见服务/版本识别
4. 基于开放端口与 Banner 的基础 OS 猜测
5. 导出 JSON / CSV 资产清单

## 快速开始

```bash
cd output/asset_scanner
python asset_scanner.py --network 192.168.1.0/24 --ports 22,80,443,3306 --output assets.json
```

扫描本机并输出 CSV：

```bash
python asset_scanner.py --hosts 127.0.0.1 --ports 22,80,135,443,445,3306,3389 --skip-discovery --output assets.csv
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--network, -n` | 目标网段，如 `192.168.1.0/24` |
| `--hosts` | 逗号分隔主机列表（与 `--network` 二选一） |
| `--ports, -p` | 端口：`22,80,443` 或 `1-1024` 或混合 |
| `--output, -o` | 输出文件（`.json` / `.csv`） |
| `--format` | `auto` / `json` / `csv` |
| `--workers, -w` | 主机并发数（默认 64） |
| `--port-workers` | 单主机端口并发数（默认 50） |
| `--timeout, -t` | 连接超时秒数（默认 0.8） |
| `--banner-timeout` | Banner 抓取超时（默认 1.5） |
| `--skip-discovery` | 跳过存活探测，直接扫全部目标 |
| `--no-icmp` | 禁用 ICMP，仅 TCP 探测存活 |
| `--no-banner` | 跳过 Banner/版本识别 |
| `--include-closed-hosts` | 保留无开放端口的存活主机 |
| `--quiet, -q` | 减少日志输出 |

## 输出示例（JSON）

```json
[
  {
    "ip": "192.168.1.100",
    "ports": [
      {"port": 22, "service": "ssh", "version": "OpenSSH 7.4", "banner": "SSH-2.0-OpenSSH_7.4"},
      {"port": 80, "service": "http", "version": "nginx/1.18.0", "banner": "HTTP/1.1 200 OK | Server: nginx/1.18.0"}
    ],
    "os": "Linux"
  }
]
```

## 输出示例（CSV）

```text
ip,port,service,version,os,banner
192.168.1.100,22,ssh,OpenSSH 7.4,Linux,SSH-2.0-OpenSSH_7.4
192.168.1.100,80,http,nginx/1.18.0,Linux,HTTP/1.1 200 OK | Server: nginx/1.18.0
```

## 项目结构

```text
asset_scanner/
  asset_scanner.py          # CLI 入口
  requirements.txt          # 依赖说明（标准库即可）
  README.md
  scanner/
    __init__.py
    host_discovery.py       # CIDR 展开与主机发现
    port_scanner.py         # 多线程端口扫描
    service_detect.py       # Banner、服务识别、OS 猜测
    exporter.py             # JSON/CSV 导出
```

## 技术说明

- **主机发现**：ICMP ping + 常见端口 TCP connect 探测
- **端口扫描**：`socket.connect_ex` 多线程并发
- **服务识别**：端口映射 + Banner 正则指纹（SSH/HTTP/FTP/SMTP/MySQL/Redis 等）
- **OS 猜测**：启发式（开放端口组合 + Banner 关键字），非精确指纹

## 注意

1. 仅在授权网络中使用；未经授权扫描可能违法
2. Windows 下 ICMP 可能受防火墙/权限影响，可用 `--no-icmp` 或依赖 TCP 探测
3. 大规模网段请合理设置 `--workers` 与 `--timeout`，避免对网络造成压力
4. HTTPS 等 TLS 服务的版本识别受明文 Banner 限制，主要依赖端口与 HTTP 明文头

## License

MIT