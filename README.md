# 长篇小说生成器（设定工坊 + 总纲卷纲 + 连续性生成 + WebUI）

## 四步流程

1. **小说名称设定**：可手动输入、AI生成、随机生成。  
2. **总纲（简介）生成**：可手动提供、AI生成、随机生成。  
3. **卷名与卷纲生成**：可手动提供、AI生成、随机生成（并自动分配章节范围）。  
4. **章节生成**：逐章生成正文并维护连续性摘要/时间线。

---

## 1）设定阶段（setup）

```bash
python3 novel_generator.py setup \
  --title-mode ai \
  --title "" \
  --genre 科幻 \
  --premise "文明在热寂阴影下争夺最后的恒星火种" \
  --world-bible "银河被九大环带分割，超光航道由古代引力井维持..." \
  --synopsis-mode ai \
  --volumes-mode random \
  --volume-count 4 \
  --character-count 4 \
  --random-level partial
```

### 关键参数

- 名称：`--title-mode manual|ai|random` + `--title`
- 总纲：`--synopsis-mode manual|ai|random` + `--synopsis`
- 卷纲：`--volumes-mode manual|ai|random` + `--volumes`（每行 `卷名|卷纲`）+ `--volume-count`
- 人物：`--characters`（每行 `name|role|gender|height|weight|outfit|personality|mot1,mot2`）+ `--random-level`

### 设定输出

- `novel_state.json`：主状态（含 title/synopsis/volumes）
- `novel_setup.json`：设定策略（含 mode）
- `assets/character_images/*.svg`：人物形象图

---

## 2）章节生成（run）

```bash
python3 novel_generator.py run --api-key "$OPENAI_API_KEY" --start 1
# 也支持把 --api-key 放在 run 前：python3 novel_generator.py --api-key "$OPENAI_API_KEY" run --start 1
```

每章文件包含：

- 细纲摘要（剧情摘要 / 关键事件 / 人物变化）
- 正文

并将摘要持续写回状态以保持长篇连续性。

另外支持“每 N 章审阅”机制：

- 默认每 10 章生成一次审阅建议（`review_after_chapter_XXXX.md`）
- AI 会返回“接下来剧情建议”，供用户决定是否继续
- 默认会暂停，审阅后手动继续：`run --start 下一章号`

可通过参数控制：

```bash
python3 novel_generator.py run --api-key "$OPENAI_API_KEY" --start 1 --review-interval 10
# 也支持把 --api-key 放在 run 前：python3 novel_generator.py --api-key "$OPENAI_API_KEY" run --start 1 --review-interval 10
```

若你希望不中断自动继续：

```bash
python3 novel_generator.py run --api-key "$OPENAI_API_KEY" --start 1 --review-interval 10 --auto-continue-after-review
# 也支持把 --api-key 放在 run 前：python3 novel_generator.py --api-key "$OPENAI_API_KEY" run --start 1 --review-interval 10 --auto-continue-after-review
```

---

## 3）WebUI

```bash
python3 novel_webui.py --library-root . --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000`：

- **设定页**：可直接配置“名称模式、总纲模式、卷纲模式、角色模板”等
  - 同页可直接填写 `API Base URL`、`API Key`、`Model`（无需环境变量）
  - 可填写“参考文档路径（txt/docx）”用于学习风格
  - 可配置“审阅间隔（每N章）”与是否自动继续
- **小说详情页**：可查看
  - 小说总纲
  - 参考文档提炼结果（用于风格控制）
  - 卷名与卷纲（含章节区间）
  - Token 监控（Prompt / Completion / Total + 分阶段统计）
  - 审阅建议（每10章自动产生）
  - 章节摘要
  - 人物图
- **章节详情页**：点击“详细”查看完整正文
  - 支持在正文中选中片段，一键生成“片段配图”（可选风格）
  - 生成结果会保存在当前项目中，并在页面下方长期展示；不满意可重复生成

> 设定页提交后会生成 `setup_draft.json`、`setup_command.sh`、`run_command.sh`，且命令中已带 `--api-key` 等参数。

---

## 兼容性

- 生成能力依赖 OpenAI 兼容 `/v1/chat/completions`
- 人物图默认本地 SVG 生成，不依赖外部图片服务
- 章节片段配图默认本地 SVG 生成并保存在 `generated_images/` 目录
