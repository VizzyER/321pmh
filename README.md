# 长篇小说生成器（连续性增强版）

这个程序用于批量生成超长篇小说（支持数百万字规模），核心不是一次性吐出全部文本，而是通过 **章节迭代 + 连续性记忆** 来保持：

- 前后文逻辑一致
- 人物设定一致
- 时间线可追踪
- 伏笔可回收

## 特性

- 使用 OpenAI 兼容 API (`/v1/chat/completions`)
- 每章生成后自动提炼：摘要、时间线、人物变化
- 每章文件头部自动写入“细纲摘要”（剧情摘要/关键事件/人物变化），便于快速核对前后逻辑
- 把最近章节摘要+关键事件+角色设定拼成“连续性上下文包”输入下一章
- 断点续跑：章节文件存在则自动跳过

## 快速开始

```bash
python3 novel_generator.py init \
  --api-key "$OPENAI_API_KEY" \
  --title "群星黯淡时" \
  --genre "科幻史诗" \
  --premise "文明在热寂阴影下争夺最后的恒星火种" \
  --total-chapters 300 \
  --words-per-chapter 3500 \
  --world-bible "银河被九大环带分割，超光航道由古代引力井维持..." \
  --characters $'林策|年轻航道测绘师|寻找失踪父亲,守住人类火种|苏岚:同盟且互相隐瞒\n苏岚|环带议会特使|维持秩序,隐瞒真相|林策:互相信任又猜疑'
```

```bash
python3 novel_generator.py run --api-key "$OPENAI_API_KEY" --start 1
```

## 输出结构

- `novel_state.json`: 全局状态（角色圣经、章节摘要、时间线）
- `novel_output/chapter_0001.md` ... `chapter_NNNN.md`: 每章细纲摘要 + 正文

章节文件会先完整写入同目录临时文件并同步到磁盘，再原子替换目标文件，避免写入失败留下半写章节。章节文件与 `novel_state.json` 仍是分别保存，不提供两者之间的跨文件事务保证。

## 规模建议（百万字）

- 章节数：250~400
- 每章字数：3000~4500
- 推荐启用人工审校节点（每 10~20 章）

## 注意

- 大规模生成成本较高，请控制模型、温度和章节长度。
- 若你使用不同供应商，只要兼容 OpenAI chat completions 即可。


## Web UI（浏览小说与章节详情）

你可以启动一个本地 Web 界面查看已生成小说：

```bash
python3 novel_webui.py --library-root . --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000` 后可：

- 查看每一部小说
- 点击进入章节列表
- 在章节列表中查看每章摘要
- 点击“详细”进入本章完整内容

> `--library-root` 下每个小说项目目录应包含 `novel_state.json` 和 `novel_output/chapter_XXXX.md`。
