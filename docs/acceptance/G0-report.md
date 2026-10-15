# G0 阶段验收报告（契约落地）

- 阶段门槛：G0 = contracts
- 日期：2026-10-08
- 设计版本：1.0.0
- 冻结 contract bundle digest：**`d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`**
- 状态：**G0 达成**（P00 owner 自检 + P13 集成检查均通过）

## 验收矩阵对照（AC01–AC03）

| AC | 场景 | 结果 |
| --- | --- | --- |
| AC01 | 跨语言 schema/金样：44 命令 + 14 查询严格类型，额外字段/非法数据拒绝 | 通过：三方 cross-check + examples 两例拒绝 + additionalProperties=false 全量断言 |
| AC02 | JCS/ID/sequence：Python/TS digest 金样一致，64 位水位/金额不丢精度 | 部分通过：Python 金样全 MATCH；金额/seq 为字符串（DTO 断言）；**TS 金样待 P10** 编译验证 |
| AC03 | 依赖扫描：领域不导 DB/CLI/DSH | 通过：AST 扫描 contracts/ports 无 sqlite3/subprocess/DSH 前缀导入 |

## 实际检查命令与结果

```
python D:\deepseekhannes\kernel\design-v1-20261008\tools\verify_design_package.py   # 0 errors
.venv\Scripts\python.exe -m pytest tests\p00_contracts -q                          # 29 passed
```

## G0 移交

- `pyproject.toml`、`tests/conftest.py` 自 P00 移交 P13（见 docs/integration/ownership.md）。
- 下一阶段：G1（P01 数据底座）。
