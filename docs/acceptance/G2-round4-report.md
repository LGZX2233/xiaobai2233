# G2 第四轮逐项独立验收

日期：2026-10-10（Asia/Shanghai）。工作目录为 `D:/deepseekhannes/kernel_next`，输入提交为 `aca09b044c8138389039783152d0f1e13e58dba8`，分支为 `codex/kernel-independent`。冻结范围 AC12–32、AC37–38、AC43、AC45 共25项，拆成87个条件，逐项裁决均 accepted，G2 状态为 `accepted_g2`。范围仅为独立核心的冻结 test 验收，`release_approved=false`。

每项以冻结 expect、合法公开入口、具体观察、实际产物和独立审查为依据。[checks.json](G2-round4/checks.json) 将每个条件绑定到最终 JUnit 的 exact classname/name 和归档证据；[独立裁决](../reviews/2026-10-09-round4/independent-decisions.json) 指定审查者和理由。[status.json](G2-round4/status.json) 与[当前指针](G2/current.json) 记录当前结果。实现者不独自签署自己实施的整改。

## 逐项结果

| AC | 独立裁决依据 | 结果 |
| --- | --- | --- |
| AC12 | packet版本/摘要和scope/验收/rules冻结；确认仅dispatch_ready | accepted |
| AC13 | 非法fact path/表达式拒绝；unknown阻断；固有红线不可关闭 | accepted |
| AC14 | 未执行/未检查不completed/pass；production拒绝test attempt和packet | accepted，已整改 |
| AC15 | 跨项目/任务拒绝；不同方案物理目录分离；实际directory_only记录 | accepted，已整改 |
| AC16 | 未确认取消保留unknown/pending；新attempt保留真实失败与输出 | accepted |
| AC17 | 实测版本、要求、路径和时间；missing/too_old/unknown分开；不安装 | accepted |
| AC18 | 零必需项、skipped/unknown、旧候选/验收五个反例不passed | accepted |
| AC19 | passing证据和显式选择到delivery_ready；明确申请仅pending | accepted |
| AC20 | machine/伪actor/role拒绝；verified synthetic人类动作绑定当前digest | accepted，test身份 |
| AC21 | 关键发布立即supersede pending/approved；无关名称/审计不失效 | accepted，已整改 |
| AC22 | 重算body digest一致；审批、operation、归档新增不改body | accepted |
| AC23 | 四个crash点可查回执并对账；query/replay/reconcile不重复效果 | accepted |
| AC24 | 旧epoch不结算；无fence不接管；start后撤回不宣称无效果 | accepted |
| AC25 | 真实bundle完整；异digest目标不覆盖；同digest幂等 | accepted |
| AC26 | required artifact未ready/缺失/变更均拒绝freeze | accepted |
| AC27 | 并发close仅一次CAS；repair补sink而不再执行任务 | accepted |
| AC28 | DB/file/local采集分别呈现；partial可修复；manifest不变 | accepted，已整改 |
| AC29 | 一致备份含已提交WAL；integrity/FK/hash；恢复fence及历史保留 | accepted，显式test stores |
| AC30 | 零链接需求进分母；N/A明确；多跳同名异类型图正确 | accepted |
| AC31 | as_of一致；投影落后明确；unknown费用为null；只读重建一致 | accepted |
| AC32 | 合成只读迁移源hash不变；重跑不增revision；孤儿隔离；不补pass/批准/费用 | accepted |
| AC37 | 实际stdio拆包、乱序、超大frame、非法UTF8、重复key和日志通道 | accepted，已整改 |
| AC38 | 实际丢回复timeout不取消；重启原key补查；未证实结果不成功 | accepted |
| AC43 | A/B、两方案、真实失败/修复/重验、test人审、bundle/归档/重启总览 | accepted，非DSH |
| AC45 | 显式temp、运行库只留摘要、golden与失败归档分离、保护字节不变；实际独审核对Git检出字节 | accepted |

## 整改和独立审查

AC15 使用历史execution_root引用比较实际resolved路径，拒绝跨task/strategy同目录及父子目录；running/unknown跨root新版本、对象别名和重启继续保留占用。数据组独立复验执行组实现。AC14 同时核验持久attempt和packet的production模式，防止checker重新贴标；执行组独立复验交付组实现。

AC21 在合法requirement/design/rules发布后，以单个独立CAS记录superseded、任务阶段和审计；decide/apply也检查当前decisive basis。数据组复核主审组合根接线和交付实现，最终pending/approved两路径通过。原receipt不当作当前状态，原key重放不重新批准或执行效果。已start的撤销仍返回CANCEL_PENDING并保留approved/apply_started及unknown交付事实。

AC28 区分原采集请求与暂时本地gap，repair在来源连续后重算完成；close/callback显式false两条反例均不提升。查询明确source incomplete，manifest不变，session_flush仍not_configured。交付组和主审独立复核数据实现。协议整改按解码key判重、完整frame字节限额和解析后非有限数拒绝，执行组独立复核主审实现。

分组报告见[执行](../reviews/2026-10-09-round4/execution-review.md)、[交付](../reviews/2026-10-09-round4/delivery-review.md)、[数据证据](../reviews/2026-10-09-round4/data-evidence-review.md)、[目录独审](../reviews/2026-10-09-round4/root-isolation-peer-review.md)、[审批独审](../reviews/2026-10-09-round4/approval-peer-review.md)、[来源独审](../reviews/2026-10-09-round4/source-flush-peer-review.md)和[协议闭环独审](../reviews/2026-10-09-round4/protocol-peer-review.md)。

## 最终验证与产物

最终一次联合pytest为620 passed，0 failed/error/skipped，32.49秒；最终Node为19 passed，0 failed/cancelled/skipped，683.1957毫秒。[Python capture](G2-round4/evidence/python-acceptance-final-result.json)和[Node capture](G2-round4/evidence/node-acceptance-final-result.json)都exit 0，217个验证输入运行前后指纹一致。两次运行分别开始于2026-10-10 13:04:58和13:05:33。最终[JUnit](G2-round4/evidence/pytest-acceptance-final.xml)是唯一Python计数来源，分组、peer及历史结果均不累加。

显式临时树[索引](G2-round4/evidence/scenarios-acceptance-final/index.json)保存2321个文件路径/摘要，归档408个合成非数据库文件，909个DB/WAL/SHM条目只留路径与hash。Python根为`.validation-tmp/g2-acceptance-final`；Node仅归档此次运行生成的`stdio-0dks45`子目录。真实执行output/stderr、ready artifacts、manifest和bundle可检查。历史capture和release归档保留，不增加最终计数。

沙箱pytest的WinError 5和Node spawn EPERM有实际失败证据，宿主重跑只解除宿主限制，不改变产品断言。普通归档进程也读不到宿主pytest临时树，早期不完整归档和中间归档均单独保留；最终宿主命令完成2321/408归档。中间fixture错误、接线顺序错误和产品反例分别保留在第四轮evidence，未覆盖第三轮或当作最终通过结果。实际命令见[commands.md](G2-round4/commands.md)。

2026-10-10的实际独立终审发现历史capture/manifest包含五个未提交的`.egg-info`文件，四份文档的Windows检出换行与摘要不一致。现已排除生成安装元数据并固定这些文档的LF规则，217个输入的新capture使用整改后的工具。先前AC45候选稿不代表独立签字，当前以[g2_final_audit终审](../reviews/2026-10-09-round4/ac45-final-peer-review.md)为准。该代理复核全部217输入与1280项候选manifest的Git index检出字节、408项归档、53项保护输入及25项87条件绑定后，独立签署accepted；此报告登记其真实结论。

分组及peer报告保留审查当时的观察。其历史`scenarios/`路径没有纳入当前证据包，最终对应关系由[checks.json](G2-round4/checks.json)逐条件绑定到最新归档和JUnit；这些最终引用由协调者补充，不追认原审查者观察了新产物。

[protected-inputs.json](G2-round4/protected-inputs.json)逐文件核对输入提交的冻结contracts、fixtures、第三轮目录/报告和既有ZIP字节。冻结bundle digest仍为`d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`。[artifact-manifest.json](G2-round4/artifact-manifest.json)覆盖当前源码、测试、工具、报告和归档；manifest与verification-result自身排除，避免自引用摘要。

## 范围与交接

实际host是独立Python，执行保证为directory_only，人类身份为verified synthetic test proof。真实DSH属G3，工作台属G4，生产恢复后置；平台仅可适配，目标用户知识树只规划。没有安装/启动DSH、付费模型、生产数据导入、训练或语料上传。[限制](G2-round4/limitations.md)明确只读rebuild与离线test-store维护的合法入口及未配置host final flush。

第三轮555 Python/14 Node及246文件验证保持历史原始资料，530/545/547等历史或中间值不作为当前计数。普通提交和实际远端核对见[同步记录](../handoffs/2026-10-10-g2-acceptance-remote-sync.md)，后续范围见[交接](../handoffs/2026-10-09-g2-independent-acceptance.md)；不重写历史，main保持初始提交。
