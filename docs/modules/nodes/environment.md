# 环境探测与依赖事实

| 字段 | 值 |
| --- | --- |
| node_id | `K-ENVIRONMENT` |
| node_kind | `module` |
| document_version | `1.0.0` |
| updated_at | `2026-10-10 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现显式 provider 探测与本地 Python provider；本次只新增节点记录 |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

`updated_at` 使用 Asia/Shanghai 日期精度；`source_revision` 是本文静态阅读的源码提交，文档版本单独递增。

## 职责与范围

本节点记录指定 recipe 依赖的实际版本、要求、路径和检查时间，区分 `satisfied`、`too_old`、`missing`、`unknown`，保存 provider 原始观察。探测本身不安装依赖，不创建默认 provider，也不执行自动修复。

`EnvironmentService` 在探测前校验任务、execution root 与 recipe 引用以及 `attempt.execute` capability。保存 pending 操作后调用显式 provider，再以独立结果事务追加 revision；provider 异常记录 unknown 与原因，不补造 ready。

本地 `PythonEnvironmentProbe` 测量运行内核的 Python 和已安装发行包。它不进入 execution root 启动另一个解释器，不能证明任意 remote host、虚拟环境或容器内依赖已就绪。

## 节点关系

`depends_on = [K-CONTRACTS, K-STORAGE, K-LEDGER, K-IDENTITY]`。

`related_to = [K-DESIGN, K-EXECUTION, K-RULES, K-QUERIES, K-BOOTSTRAP, K-RPC, K-RECORDS]`。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| 导航归属 | `K-CORE` | 派发前的环境事实 |
| 依赖 | `K-CONTRACTS` | environment.probe schema、精确引用与 digest |
| 依赖 | `K-STORAGE`、`K-LEDGER` | pending/结果 revision、current head、独立结果幂等键 |
| 依赖 | `K-IDENTITY` | 项目/store/capability 检查，mode 从可信 scope 保存 |
| 关联 | `K-DESIGN` | packet 引用探测结果，dispatch.confirm 要求 ready 且任务相符 |
| 关联 | `K-RULES` | `environment.status` 可参与规则评价，缺事实保持 unknown |
| 关联 | `K-EXECUTION` | executor 的沙盒与启动检查独立进行，不由环境 ready 替代 |
| 关联 | `K-QUERIES` | environment.report、operation.status 展示保存事实 |
| 关联 | `K-BOOTSTRAP`、`K-RPC` | `environment_provider=` 显式装配与命令查询 handler |
| 关联 | `K-RECORDS` | 环境错误进入任务总结和学习材料，安装修复必须有单独授权与真实结果 |

## 源码与接口

| 入口 | 符号 | 用途 |
| --- | --- | --- |
| [环境服务](../../../src/project_kernel/application/environment_service.py) | `EnvironmentService.environment_probe` | 保存意图、调用 provider、追加 observation 与原始 provider_result |
| [当前内部端口](../../../src/project_kernel/internal/provider_ports.py) | `EnvironmentProbe.probe(recipes)` | 应用层实际消费的 provider 方法 |
| [本地 Python provider](../../../src/project_kernel/internal/environment_provider.py) | `PythonEnvironmentProbe.probe` | platform、sys.executable、importlib.metadata 与 packaging 版本比较 |
| [冻结服务端口](../../../src/project_kernel/ports/ports.py) | `EnvironmentPort.probe` | v1 服务声明；签名与当前内部端口不同，接入需核对消费端 |
| [组合根](../../../src/project_kernel/bootstrap.py) | `KernelServices`、`build_server` | 显式 `environment_provider=`，未配置报不可用 |
| [派发服务](../../../src/project_kernel/application/design/service.py) | `dispatch_confirm` | 校验 environment 的 ready 和任务引用 |

provider observations 仅允许一组结果字段更新内核记录；原始返回另存 `provider_result`。task/root/recipe 引用及 mode 来自原输入和可信 scope，不由 provider 返回覆盖。

## 数据与结果

| 字段或对象 | 语义 |
| --- | --- |
| `environment_probe.v1` | exact task/root/recipe 引用、mode、pending 与后续结果 revision |
| 每项 dependency fact | name、required_version、version、path、checked_at、state，必要时 reason |
| `runtime_path` | 本地 provider 的 `sys.executable` |
| `checked_at` | aware UTC 时间，记录实测时刻，不是本页 updated_at |
| probe `status` | 本地 provider 至少有一项 fact 且全部 satisfied 才为 ready；其他为 blocked，异常为 unknown |
| `provider_result` | 保存完整原始观察，与内核拥有的关联字段分开 |

`too_old` 在当前 provider 中表示实测版本不满足 SpecifierSet，包含上界或排除版本不匹配，名称不能替代具体 required_version 的判断。无依赖 fact 也不会自动 ready。

## 需求记录

| 记录 | 来源与要求 | 当前落点 |
| --- | --- | --- |
| 冻结 `AC17` | [G2 条件表](../../acceptance/G2-round4/checks.json)：实测版本/要求/path/时间 | 本地 Python provider 保存对应字段 |
| 冻结 `AC17` | 缺失、版本不满足与未知分开，不安装缺库 | dependency state 与只读 runtime/distribution 查询 |
| 冻结 `AC12` | packet 固定环境依据，确认不执行 provider | environment_ref 指向已保存结果；confirm 只检查事实 |
| 新增 `REQ-CCR-01`、`REQ-CCR-02` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：节点入口、要求、验收、版本和更新时间可定位 | 本文与模块索引 |
| 新增 `REQ-CCR-03` | 明确有向关系，允许空和多对多，本轮不关联对话 | 本文 depends_on/related_to 与 [关系索引](../registry.json) |
| 新增 `REQ-CCR-04`、`REQ-CCR-06` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：任务总结记录环境问题与未确认事实，提供术语和学习资料 | 关联 `K-RECORDS` 与 [维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)；资料说明依赖检测与修复差别 |
| 新增 `REQ-CCR-11` | 保持内核结构清晰与冻结证据 | 本次不增加自动采集、安装或学习资料运行时代码 |

## 历史验收记录

仅以下 AC17 条件由第四轮历史证据接受，签字来自 [execution-review.md](../../reviews/2026-10-09-round4/execution-review.md)，完整条件绑定见 [checks.json](../../acceptance/G2-round4/checks.json)。本次未重跑探测或测试，不声明完整平台矩阵已接受。

| 条件 | 历史观察 | 证据 |
| --- | --- | --- |
| 实测版本/要求/path/时间 | platform Python version、required_version、真实 sys.executable 与 aware UTC checked_at 存入 operation/report | [环境场景][environment-evidence] |
| 缺失/过旧/未知分开 | 正常 Python、`>=999`、不存在的发行包、非法 spec 分别 satisfied/too_old/missing/unknown；报告四类各一，整体 blocked | [环境场景][environment-evidence] |
| 不安装缺库 | 探测前后 installed distribution inventory SHA256 相同；实现只查询 metadata，无 installer 或安装 subprocess | [环境场景][environment-evidence] |

G2 是配置本地 Python provider 的 test 验收，`release_approved=false`。真实 DSH、远程执行、容器和其他模型平台的环境 provider 均需另行接入与验收。

## 当前限制与待办

当前内部 provider 只收到 recipes；冻结 `EnvironmentPort` 中的 scope/root/requirement_refs 参数没有直接用于此本地 provider。宿主若要探测指定 root 内实际运行时，需显式 provider 与对应事实记录，不能把这份本地结果泛化。

探测命令同步调用 provider，没有独立后台采集或自动刷新机制。环境和用户知识记录不能共用“熟悉程度”字段：前者是机器实测，后者是可编辑学习状态。

`REQ-CCR-04/06` 总结必须同时保留实测版本、要求与原因，再记录修复步骤；未执行安装或重验时写未执行。节点 updated_at 跟随文档事实变更，运行时 checked_at 保持原值。

## 变更记录

| 日期 | 文档版本 | 源码依据 | 变更与验证 |
| --- | --- | --- | --- |
| 2026-10-10 | `1.0.0` | `0a619766162682606ad57a9aa4c1926d54c1b891` | 建立环境节点，明确本地实测、端口差异、状态含义和 AC17；静态阅读，未运行测试 |

[environment-evidence]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac17_rpc_real_versions_pa0/execution-evidence.json
