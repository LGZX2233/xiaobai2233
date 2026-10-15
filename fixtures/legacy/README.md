# P07 脱敏合成旧库样本（fixtures/legacy）

本目录包含 P07 迁移/对账能力的**合成、脱敏**旧库样本（非真实旧 kernel 数据）。

- `legacy.sqlite` — 合成旧库（真实 SQLite，只读打开）；表：`projects`/`tasks`/
  `attempts`/`approvals`/`evidence`/`files`，列均为 TEXT（脱敏字符串）。
- `records.jsonl` — 同一批记录的 JSONL 文本形态（`raw` 保留原文），便于跨语言对账。

样本内容固定、确定性生成（`SyntheticLegacySample`），覆盖：
- 两个同名 `display_name="Alpha"` 的旧项目（`p-a`、`p-b`）→ 验证不自动合并；
- `task/attempt/approval/evidence/file` 正常记录；
- 失败/未选 attempt（`a-2`、`a-3`）、无 usage 的 attempt、带 usage 的 `a-1`；
- 孤儿 attempt（`a-orphan` → `t-not-found`）、孤儿 evidence（`e-orphan` →
  `a-missing`）、无归属 task（`t-3` → `p-missing`）。

真实旧库/旧源码（`D:/deepseekhannes/kernel`、C 盘副本）一律只读，不在此样本内，
也不被本目录引用。
