# CR-008：G2 权限、执行事实与交付入口整改

日期：2026-10-09。状态：实现和自验完成，等待独立复验。范围：T02–T08、R01–R12；T01 见 [CR-007](CR-007-uow-replay.md)。协调者在子代理额度错误后接管未完成事项；此记录不构成独立 owner 批准。

## 接口与行为

bootstrap 要求受信 InvocationContextRegistry，显式空权限不扩张。selector、project、store、principal 与 human proof 在业务调用和回执重放之前校验。查询保留调用上下文、水位和分页信息；identity 域未装配即返回不可用。语料功能默认不声明。

需求确认保留验收项和假设；packet 保留完整冻结输入。执行先持久化 intent/claim 再调用 provider，同 key/restart 不重复启动。取消请求和确认分开；输出、错误、handle、epoch 与来源引用保留，provider 字段不能改写任务归属。来源 ingest 到 attempt.settle 的真实 RPC 测试覆盖错误 epoch 和迟到结果。

验收器在事务外执行，异常保留可查询 unknown；重复调用不再检查。重新验收改变候选会使旧批准 superseded。delivery.request 明确创建申请，delivery.apply 先 claim，在 apply-start 复核审批、候选和制品；同 key不再次导出，效果落地而回执丢失可只读对账。归档、备份、来源、规则和环境命令已装配；环境记录版本/path、missing/too_old/unknown。

## 持久化与恢复

项目 schema/DDL、公共 DTO、wire receipt 和 contracts/v1 未变。新增内部 revision 类型仍使用现有账本。每个文件项目 Store 写连接持有生命周期共享锁；受控维护持有跨进程排他锁。协调锁使用独立 .access.sqlite，不改变项目数据库迁移。内存库无文件替换路径。

受控恢复只在 test 模式的显式维护入口可用，在线 RPC 不替换自身活库。恢复读取人工决策和固定备份，保存 intent、一致历史备份和原始文件，校验替换后解锁；异常回退原库，未知状态只对账。该锁只覆盖遵守 Store.open_project 的内核写者，不能代替生产宿主停机。

## 消费者迁移

内部调用者必须传入受信项目句柄和所需权限；执行、验收、制品、归档和备份 provider 必须显式配置。旧伪造引用夹具改用真实业务服务生成基础数据。旧“空 payload 到 handler”的断言改为 schema smoke，增加合法输入、移除 handler 后失败的反向接线测试。

此独立内核尚未发布为 DSH 包；不改变 DSH 的 profile、Session 或包 API。当前库启用前需关闭旧内核写进程，保证全部新连接使用锁协议；历史 unknown 操作不能自动重放。

## 验证与限制

联合回归 424 passed，新增来源结算与并发收尾各 1 passed，Node 协议 14 passed；冻结摘要保持不变。AC29 受控恢复、AC43 全流程的输入和产物见 [G2 证据](../acceptance/G2-report.md)。未实现部分与独立复核要求见 [限制](../acceptance/G2/limitations.md)；不自行发布 G2 通过或进入 P11。
