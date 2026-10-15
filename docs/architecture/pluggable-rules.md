# 可插拔约束的使用范围

文档版本：1.0.0。更新时间：2026-10-10（Asia/Shanghai）。对应 [REQ-CCR-08](../requirements/2026-10-10-continuous-records.md)。本页根据当前源码和原 AC13 记录说明已有规则接口，没有新增 Python 插件加载器、Schema 或运行验收。

## 现有可用机制

内核通过[DesignService](../../src/project_kernel/application/design/service.py)的 `rules_save`、`rules_preview`、`rules_publish` 和[纯规则求值器](../../src/project_kernel/domain/design/rules.py)管理规则版本。宿主可用已有 `rules.save` / `rules.preview` / `rules.publish` RPC，提交符合[冻结 command Schema](../../contracts/v1/command-payloads.schema.json)的规则；真实运行须由宿主提供可信上下文和能力。

规则的“插拔”是增删、启停声明式条目并发布新的 rules revision，不是在内核执行任意代码。旧版本和已有 packet 的精确 rule_refs 保留；新派发需引用预期的当前规则。发布需要当前 draft、匹配 digest 的 impact preview 和 CAS 预期 head；修改规则不重写历史执行依据。

## 条件与效果

| 部分 | 当前支持与限制 |
| --- | --- |
| 条件组合 | `all`、`any`、`not` 或一个 path/operator/value 条件；不执行代码或表达式字符串 |
| 比较 | `eq`、`ne`、`exists`、`in`、`not_in`、`gt`、`gte`、`lt`、`lte`；字段类型由当前验证/求值行为约束 |
| path | 当前只允许 `task.phase`、`task.mode`、`packet.mode`、`mode`、`scope.required_sandbox_level`、`environment.status`、`provider.supported_sandbox_level`、`provider.can_cancel` |
| deny | 条件命中或未知时阻断；不能以另外一条规则覆盖 |
| require_human | 条件命中或未知时产生需人审结果；当前 dispatch.confirm 将此结果阻断，没有人审后自动续跑机制 |
| warn | 条件命中时求值结果包含 reason；当前 dispatch 路径没有把警告作为独立记录/通知完整输出 |
| allow | 不支持；规则不能提升权限或覆盖核心禁止条件 |

未知事实不等于 false。`rules_preview` 当前只传入 task 和 mode，dispatch 求值传入 task、packet、scope、environment、mode；允许 path 不保证该入口提供对应事实。尤其 `provider.*` 在这些现有调用未提供，不能因为预览未知就推断部署能力已满足。扩展 fact source 需要单独源码变更与接受范围。

## 添加或移除规则

1. 写明规则 ID、目的、适用节点、所需事实、效果、reason、版本与需求来源。事实须来自现有允许字段；不能在 skill 里把人工假设当运行事实。
2. 保存为新 draft，按源水位生成影响预览，阅读命中和 unknown。预览不是每个执行场景的全事实模拟。
3. 使用匹配 draft 的预览发布新 current，给后续 packet 使用；删除或关闭条目也发布新 revision，保留旧依据。
4. 在[K-RULES 节点](../modules/nodes/rules.md)和任务记录记录新规则引用、范围、实际操作结果与尚未核对部分。本轮没有执行上述 RPC，不将这段使用流程记成成功调用证据。

## 不可关闭的约束

项目/store 范围、可信上下文与人审、精确不可变引用、必需验收、真实制品和 test/production 区分由核心用例校验，不是可关闭的 data_rule 条目。任意规则或 skill 都不能授予 `approval.decide`、跳过权限、把未知效果改成成功，或改变历史签字范围。

需要新的事实路径、代码插件、用户画像规则或人工解除后的续跑时，应单独记录需求和运行设计。学习记录可以建议技术路线，不能充当授权证据；本轮的文档 workflow 不进入 dispatch facts。

## 验收与变更

既有 [AC13](../acceptance/G2-round4/checks.json)独立接受仅涵盖冻结的非法路径/表达式、unknown 与红线条件；本页没有扩大为任意插件平台接受。实现入口、需求和具体历史证据可从 [K-RULES](../modules/nodes/rules.md)继续读取。

| 日期 | 文档版本 | 内容 | 验证 |
| --- | --- | --- | --- |
| 2026-10-10 | 1.0.0 | 明确现有声明式规则扩展方法和事实/人审/警告限制 | 源码阅读、文档静态核对；未运行规则测试或 RPC |
