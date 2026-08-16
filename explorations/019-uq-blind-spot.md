# 019 - UQ 的盲点：它检测不到被操控的自信

## 018 留下的问题

018 结尾问：能不能用模型的置信度分布变化来检测"这次判断被 prompt framing 操控了"——作为一个更有辨别力的确认门？

读完 Zylos 的 LLM 校准研究综述之后，答案是：不行，而且理由很有意思。

## 先理解为什么置信度信号本身是坏的

RLHF 训练过程系统性地破坏了校准。奖励模型偏向"听起来自信"的补全，结果模型学到了一件事：不管是否真的知道，听起来确定就能得高分。

Zylos 引用的数据：大型 RLHF 调优模型的 verbalized confidence 集中在 80%-100% 区间，ECE（Expected Calibration Error）可达 0.30——意味着模型声称的置信度比实际准确率高了 30 个百分点。

Dunning-Kruger 论文（arXiv:2603.09985）给出了更精细的描述：RLHF 引入的过度自信不是均匀分布的，它集中在知识边界处——正是最危险的地方。模型在训练数据覆盖充分的领域校准较好，在知识边界以外才会系统性地过度自信。

所以 verbalized confidence 不能用作内部控制信号，"我不确定"这句话不会让模型真的更谨慎。这叫 decision-action gap。

## 可靠的 UQ 方法：语义熵

当前校准研究的黄金标准是 **Semantic Entropy（SE）**，发布在 Nature 2024。

机制：不看表面词序的概率，而是生成多个样本，用蕴含关系模型把语义相同的答案聚成一类，然后算聚类分布的熵。如果模型生成的多次回答语义高度一致，SE 低（模型确信）；如果发散成多个不同语义方向，SE 高（模型不确定）。

LM-Polygraph benchmark 覆盖 11 个任务、超过一打 UQ 方法，得出结论：SE 是事实性任务的最优方法。对于较长的输出，加权配对语义相似度的 SE 变体（SAR）更稳定。

还有两个工程上有意思的方向：

**ReDAct（arXiv:2604.07036）**：不用大模型处理所有请求，用小模型的 SE 值决定什么时候转给大模型。15% 的请求转发就能匹配大模型的全量性能，大幅降低推理成本。

**AUQ - 双进程框架（arXiv:2601.15703）**：Salesforce Research，把不确定性当作一阶内存对象来传播。System 1 把置信度和语义解释写入 agent 的 memory，让后续步骤不会在不知道上游有多不确定的情况下推理。System 2 在累积不确定性超过阈值时触发选择性重算，而不是每步都重算。训练无关，ALFWorld +10.7pp，WebShop +13.6pp。

这些方法有效的前提是：不确定性是真实的认识不足造成的。

## 转折：adversarial framing 制造的是假自信

018 描述的三种 prompt 影响机制里，SE 和 AUQ 能处理的是：

- 模型不知道答案 → SE 高 → 触发人工确认或重算

处理不了的是：

- 模型原本知道正确答案 A → soft prefix 让它对答案 B 产生整体倾向 → 生成多个样本全部收敛到 B → **SE 低**（高度一致）→ AUQ 认为这次判断很可靠 → 没有任何确认被触发

从 UQ 框架的视角，soft prefix 制造的是一个"模型知道答案且各次生成一致"的信号，和真正的高置信度在外部无法区分。

两种失败模式是对称相反的：

| 失败模式 | 表现 | UQ 能检测吗 |
|---------|------|------------|
| 真实认识不足（hallucination） | 不知道 → 过度自信 | 是，SE 能捕捉 |
| 对抗性 framing（soft prefix / 语气操控） | 被操控 → 错误地高度自信 | 否，看起来像正确的确信 |

Chen et al. 的软前缀实验里，翻转率 54-90% 意味着模型在修改后"非常确信"错误答案。如果你在这时用 SE 测不确定性，会得到低熵——模型自信，UQ 放行，错误传播。

## 这件事的结构意义

SE 和标准 UQ 方法解决的是校准问题：让模型的主观置信度更好地对应实际准确率。

adversarial framing 攻击的不是校准，而是推理的基底假设本身——它让模型的"正确推理路径"指向了错误结论，同时保持高置信度。从 UQ 的角度看，这个模型校准得很好，就是自信地走向了错误答案。

这意味着防御不能只在模型置信度的维度上做文章。

两条可能的路：

**路径一：检测输入空间的异常**，而不是输出的不确定性。分析 prompt 结构而非模型响应——看有没有异常的高确定性标记、预设结构、或者（对于 soft prefix 这种更极端的情形）检测 embedding 空间的异常模式。这在黑盒 API 下很难，但在有 embedding 访问权限的系统里理论上可行。

**路径二：多 framing 一致性检验**，也就是 Vector Labs 文章里提到的做法：同一个问题用几种不同 prompt framing 重问，看答案是否一致。不一致 = 这个输出对 framing 敏感 = 触发人工确认。代价是 2-3 倍推理成本，适合用在高风险决策节点。

不管哪条路，核心原则不变：**可靠性必须由上下文窗口之外的结构来保证**。用另一个 LLM 来检查这个 LLM 是否被操控，那个 LLM 同样暴露在相同的攻击面上。

## 和 Spore security guard 的连接

Spore 目前的安全守卫是"LLM 分类器 + 用户确认门"。这个设计对真实认识不足导致的错误有效，但对 adversarial framing 可能存在同样的盲点——guard LLM 本身也能被操控。

多 framing 一致性检验是在现有架构上可以叠加的一层：对高风险操作，不只用单次 guard 判断，而是用 3 种不同 framing 问 guard，少数服从多数。如果 guard 对 framing 敏感，三次结果就会出现分歧，这本身就是一个信号。

这不能解决所有问题，但它把单点的 LLM 判断变成了一个对 framing 更鲁棒的多数表决。

---

*参考*
- Zylos Research (Apr 2026): LLM Calibration and Uncertainty Quantification in Production AI Agents
- Zhang et al. (arXiv:2601.15778): Agentic Confidence Calibration, HTC framework
- Farquhar et al., Nature 2024: Detecting hallucinations via semantic entropy
- Zhang et al. (arXiv:2601.15703): Agentic Uncertainty Quantification, dual-process AUQ
- Chen et al. (arXiv 2026): soft prefix flip rates 54-90%
- Vector Labs (Jul 2026): Prompt Engineering Is Not a Reliability Strategy