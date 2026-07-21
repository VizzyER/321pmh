# 持久化必填字符串字段

`novel_state.json` 顶层必须包含以下五个 JSON 字符串字段：

- `title`
- `genre`
- `premise`
- `style_guide`
- `world_bible`

通过 `NovelState.from_dict` 加载持久化状态（含 `NovelGenerator.load_state`）时，上述字段必须存在且值为 JSON 字符串。缺失时抛出 `ValueError`，消息为 `<field> is required`。字段存在但值不是字符串（如 `null`、布尔值、数字、数组、对象）时抛出 `ValueError`，消息包含字段名与加载后的实际 Python 类型名（由 `type(...).__name__` 给出，例如 `NoneType`、`bool`、`int`、`list`、`dict`）。

合法字符串按原样保留：不 trim、不转换、不补默认值。空字符串（`""`）目前仍允许。
