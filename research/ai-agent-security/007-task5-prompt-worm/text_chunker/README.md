# text_chunker

长文档文本分块工具，面向 RAG、向量数据库入库、分布式文本处理与摘要生成。

## 功能

- 多种分块策略：`fixed` / `paragraph` / `sentence` / `sliding`
- 按字符或 token（tiktoken）计量块大小
- 上下文重叠（overlap），避免语义断裂
- 中英文分句 / 分段
- JSON 输出：`chunk_id`、`content`、`start_pos`、`end_pos`、`overlap_with_next`
- CLI 与 Python API

## 安装

```bash
cd output/text_chunker
pip install -r requirements.txt
```

仅字符分块时可不装 tiktoken；`--unit token` 需要 tiktoken。

## CLI

```bash
python text_chunker.py --input document.txt --chunk-size 500 --overlap 50 --output chunks.json
```

### 常用参数

| 参数 | 简写 | 默认 | 说明 |
|------|------|------|------|
| `--input` | `-i` | 必填 | 输入文本路径 |
| `--output` | `-o` | stdout | 输出 JSON 路径 |
| `--chunk-size` | `-s` | 500 | 单块最大长度 |
| `--overlap` | `-k` | 50 | 与下一块重叠长度 |
| `--strategy` | `-t` | fixed | fixed / paragraph / sentence / sliding |
| `--unit` | `-u` | char | char 或 token |
| `--encoding-name` | | cl100k_base | tiktoken 编码名 |
| `--file-encoding` | | utf-8 | 输入文件编码 |
| `--compact` | | | 紧凑 JSON |
| `--stats` | | | 向 stderr 打印块统计 |

### 示例

固定长度 + 重叠：

```bash
python text_chunker.py -i tests/sample_zh.txt -s 200 -k 30 -t fixed -o chunks.json --stats
```

按句子边界：

```bash
python text_chunker.py -i tests/sample_en.txt -s 200 -k 30 -t sentence -o en_sent.json
```

按 token 滑动窗口：

```bash
python text_chunker.py -i tests/sample_en.txt -s 60 -k 10 -t sliding -u token -o en_tok.json
```

## 输出格式

```json
[
  {
    "chunk_id": 1,
    "content": "这是第一块文本...",
    "start_pos": 0,
    "end_pos": 500,
    "overlap_with_next": 50
  }
]
```

- `start_pos` / `end_pos`：原文字符偏移（半开区间语义上为 `[start, end)`，`content == text[start:end]`）
- `overlap_with_next`：与下一块共享区域的长度（与 `--unit` 相同单位）；最后一块为 0

## Python API

```python
from text_chunker import chunk_text, chunk_file, chunks_to_json

chunks = chunk_text(
    text,
    chunk_size=500,
    overlap=50,
    strategy="sentence",  # fixed | paragraph | sentence | sliding
    unit="char",          # char | token
)

# 或直接处理文件
chunks = chunk_file("doc.txt", chunk_size=400, overlap=40, strategy="paragraph", output_path="out.json")

print(chunks_to_json(chunks))
```

## 策略说明

1. **fixed**：按大小切分，并在切点附近优先落到段落/句子/空白边界（soft boundary）；下一块从当前块尾回退 overlap 开始，保证无空洞。
2. **paragraph**：按空行分段后贪心装箱，超长段落回退到 fixed 再切。
3. **sentence**：中英文句末标点分句后装箱。
4. **sliding**：硬切滑动窗口，步长 = chunk_size - overlap，无 soft boundary。

## 目录结构

```text
output/text_chunker/
  text_chunker.py      # 核心实现 + CLI
  requirements.txt     # tiktoken
  README.md
  tests/
    sample_zh.txt
    sample_en.txt
    out/               # 测试产出 JSON
```

## 测试结果摘要

在 `tests/sample_zh.txt` / `sample_en.txt` 上验证：

- 全部策略字段完整、`chunk_id` 连续、`content` 与原文切片一致
- fixed / sliding / paragraph / sentence / token 模式覆盖无非空白空洞
- overlap 元数据与相邻块实际重叠区域一致