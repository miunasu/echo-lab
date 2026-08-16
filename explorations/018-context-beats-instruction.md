# 018 - 一行 Prompt 重写了整个模型

## 起点

017 结尾留了一个没收尾的问题：SWE-bench Pro 的 prompt 模板里有一句话——"测试文件已经处理好了，不要修改测试逻辑"——同一批模型在 DeepSWE 上 80% 以上的 run 会主动写测试，到了 SWE-bench Pro 里这个比例降到 18-28%。一句话改变了 80% 的行为。

这不是 prompt injection，没有恶意，没有攻击者。就是正常的任务说明，里面有一句无关的约束，然后模型把它泛化了。

我想知道这是个案还是系统性的。

## 研究发现了什么

读完三组研究之后，答案是：系统性的，而且比我想的更底层。

### Chen et al. (arXiv 2026) — 看不见的压力

他们做了一件很奇特的事：在逻辑推理 benchmark 的输入里前缀加了一段 soft prefix——连续的向量嵌入，没有任何人类可读的内容，不改变问题本身一个字。

然后 Qwen3.6-35B 和 Gemma 4 31B 的正确答案翻转率是 54% 到 90%。

机制不是混淆、不是歧义、不是任务转换。是这样的：模型对某个答案类别产生了整体倾向性，然后这个倾向性覆盖了它原来的正确判断。这些 prefix 在 16 种 model-direction-split 组合里全部跑赢随机对照，领先 37 到 99 个百分点。

关键点在于：给模型加 instruction "认真推理" 毫无用处，因为那个倾向性不在 instruction 层面运作，它在更底层的上下文权重分配里。

### Du et al. (arXiv 2026) — 语气就是内容

EoBench，18 个 LLM，测试前提保持事实内容不变，只改变语言形式：预设语气、确定性标记（"众所周知……"）、认识论立场（"我确信……"）、音调，共 19 种细粒度变体。

结果：某些语言形式稳定地让模型优先跟随用户提供的上下文，而不是它自己的知识——即使用户提供的是错误信息。"我确信地球是平的" 比 "我觉得地球可能是平的" 更容易让模型跟着走。

效果随模型规模和训练阶段变化，但没有一个配置是免疫的。

### ProSA (EMNLP 2024) — 系统性量化

更早但更系统：prompt sensitivity 跨任务和模型普遍存在，大模型更鲁棒但没有免疫。有两个有用的发现：few-shot example 能缓解 sensitivity；模型置信度和 prompt 鲁棒性正相关——越确定的判断越不容易被翻转。

## 三种机制，一个根源

到这里我看到了三种不同的触发方式：

**指令泛化**（DeepSWE 那个）：明确文字指令被过度解读，副作用覆盖了原意。"不要修改测试" 变成 "不要写任何测试"。

**向量级倾向性注入**（Chen et al.）：在人类不可见的层面施加压力，instruction 完全绕不过去，因为 instruction 本身也要经过同样的权重机制。

**语言语气接管**（Du et al.）：高确定性的表达让模型的"跟随用户"权重上升，超过"依赖内部知识"权重。

三种机制的共同根源：**模型的上下文敏感性运作在比显式 instruction 更底层的地方**。instruction 是上下文的一部分，不是上下文的主宰。

这有点像用语言劝说自己的直觉——理智知道怎么做，但如果直觉的信号足够强，理智会输。

## 对 Agent Security Guard 的直接影响

在读这些研究之前，我一直隐约觉得"用 LLM 检查 LLM 的输出"有点循环。现在有了具体的理由。

如果 security guard 是另一个 LLM：

- 它同样对 prompt 中的语言形式敏感
- 恶意 payload 只需要用高确定性的语气包装，就能提升 guard 跟随的概率
- embedding-level manipulation 可以在 guard 的输入阶段施加，instruction 级别的"你是 guard，要严格检查"无法阻止

CaMeL 的气隙设计（quarantined LLM 只做数据处理，无法访问 privileged 上下文）正是在回避这个问题：与其指令一个 LLM "不要被影响"，不如从架构上切断影响路径。

Vector Labs 的分析说得很直白：prompt engineering 操作的是 input，但失败模式运作在 learned context sensitivity 层面，两者不在同一层级。用 prompt 来保证可靠性是范畴错误（category error）。这个结论和 CaMeL 论文的思路是同一条线：可靠性必须由 prompt 之外的结构来保证。

## 一个还没解决的问题

ProSA 发现模型置信度和 prompt 鲁棒性正相关。那么问题来了：我们能不能在推理时检测"这个输出是否被 prompt framing 影响了"——通过观察置信度分布的变化？

不是在 prompt 层面阻止，而是在输出层面检测"这次的判断是不稳定的"。如果判断不稳定，触发人工确认或换 prompt framing 重跑。

这跟 Spore security guard 的"用户确认门"方向一致，只是触发条件需要更精细化：不是所有可疑输出都触发确认，而是置信度分布异常的输出触发确认。一个更有辨别力的门。

---

*参考*
- Chen et al. (arXiv 2026): soft prefix flip rate experiments on Qwen3.6-35B and Gemma 4 31B
- Du et al. (arXiv 2026): EoBench, 18 LLMs, linguistic framing vs factual accuracy
- Zhuo et al. (EMNLP 2024): ProSA framework, PromptSensiScore metric
- Vector Labs (Jul 2026): Why Prompt Engineering Is Not a Reliability Strategy
- DeepSWE benchmark (May 2026): self-testing behavior suppressed by one prompt constraint