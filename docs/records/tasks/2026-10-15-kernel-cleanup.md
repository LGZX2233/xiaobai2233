# 内核目录整理记录

日期：2026-10-15（Asia/Shanghai）
范围：`kernel_next` 内核目录；不含前端实现，不改 `.git`。

## 结论

- `src/project_kernel/` 的现有边界清晰：`domain` 保存纯规则，`application` 负责用例与授权，`data` 负责项目与身份存储，`evidence` 负责制品和外部效果，`interfaces/rpc` 负责协议入口，`ports`/`internal` 负责端口声明。未搬迁源码，避免破坏导入边界和历史验收路径。
- `tools/` 中的脚本逐一有当前测试、验收记录、AGH 录制流程或发布流程引用。没有发现可以在不破坏文档和复验命令的情况下删除的过时脚本，因此保留并在目录说明中写明依据。
- `project_kernel_r1/` 是有独立任务记录和 280 项测试结果的参考成长轨道，不是 v1 的重复运行时；保持与 `src/project_kernel/` 隔离。
- 删除空的顶层 `scripts/` 目录和源码树中生成的 `__pycache__`/`.pyc` 缓存。缓存不属于版本内容，运行时使用 `-B` 可避免重新生成。

## 后续设计边界

内核当前实现仍不足以覆盖完整的 R1 目标，尤其是宿主调度、模型上下文装配、表单暂态和真实 provider 效果需要继续补齐。后续应沿模块边界增加能力，保持低耦合、显式端口、可替换 provider 和可追溯事实，不把宿主或前端逻辑塞入领域层。

无可视化插件的路线作为后续计划：把非可视化能力标准化为 agent framework skills，通过宿主调用内核的版本化 RPC/ports；skill 只负责发现、参数校验、上下文选择和结果呈现，授权、事实、效果观察和审计仍由内核持有。该路线是设计计划，不代表当前已经接入。

## 设计文档整合

本次同步新增[内核设计、问题治理与无界面接入计划](../../architecture/kernel-design-and-growth.md)，把原始设计来源汇总为稳定入口：

- 内核与工作台整体优化讨论稿（本地原始稿：内核与工作台整体优化-讨论稿-20261008.md）、流程评价与插件拆分讨论稿（本地原始稿：流程评价与插件拆分-讨论稿-20261008.md）、内核重建两大模块计划（本地原始稿：内核重建-两大模块架构与实施计划-20261008.md）；
- [R1 从零复现规格](../../architecture/reproduction-blueprint.md)、[双层存储](../../architecture/dual-layer-storage.md)、[并行分支](../../architecture/parallel-branches.md)、[模型交换与表单](../../architecture/agent-exchange-and-live-forms.md)及[技能成长](../../architecture/skill-growth.md)。

整合页完整描述内核与宿主的职责、八阶段流程、L0/L1、上下文工厂、候选收敛和四类事实；将长对话遗忘、重复执行、模型自报、黑箱、输出垃圾和模块耦合分别映射到机制与限制；规定模型输出先进入受控 staging，归属制品、校验、隔离、审批后才可能进入交付目标。当前 output kind/路径预算、quarantine 扫描、自动引用检查及 OS 级沙盒仍未形成完整闭环。

文档明确以事实所有权和副作用划分 contracts/domain/application/data/provider/bridge/records，强调稳定核心、显式端口、可替换 provider、事务原子边界与可选能力声明。无可视化接入被记录为计划：以标准 skills 暴露 headless 能力，由宿主调用版本化 RPC，可信人审和审计仍由内核控制；KnowledgeService RPC 接线、`model_exchange`、实时表单、宿主 lifecycle 等缺口没有写成已实现能力。

README 已重写为内核设计、实现轨道、问题映射、治理限制及接入计划主入口，列出 19 张设计图；不展开前端实现。中文/英文 README、项目总结、current-state、kernel architecture、模块树/根节点、记录索引及文档入口已相互链接。AGH 仅作为一个宿主案例。该说明不新增运行能力或历史验收。

## 整理清单与新增交付

- README 聚焦内核职责并收录 19 图；设计事实由 docs/architecture/kernel-design-and-growth.md 拥有。
- docs/plans/kernel-hygiene-and-headless.md 记录输出预算、quarantine、引用/保留期、清理 dry-run、模块耦合整改和 headless H0–H5，均为 planned。
- 视频仅保留 v5 剪辑、合并后的当前旁白、构建器、依赖清单、终端原始证据及当前回放。旧剪辑/旁白草稿、生成器、旁路、重复旧成片和可重建缓存清除；原始 AGH 录屏、截图及历史验收证据保留。
- docs/development/demo-build.md 与源目录 README 固定 v5 构建入口；网页和提交材料更新到 3分53秒。
- 外层新增工作区导航与整理清单。外层 DSH scripts 仍有 package/CI/spec 引用，没有可证明过时的脚本可删。
- .venv-redo 是本轮临时视频环境；成片和脚本就绪后删除，主项目 .venv 保留。

## 检查

- `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider tests/p00_contracts/test_import_boundaries.py -q`：3 passed。
- 使用 `compile(..., "exec")` 在内存编译 `src/`、`tests/`、`bridge/`、`adapters/` 和 `project_kernel_r1/` 下 278 个 Python 文件：通过；按 UTF-8 BOM 读取，不生成 bytecode。
- 扩展运行 `tests/p00_contracts/test_import_boundaries.py project_kernel_r1/tests` 时有 16 项失败，失败来自沙箱禁止写入系统临时目录/`project_kernel_r1/tests/acceptance/acceptance_registry.md`。该运行不能作为 R1 全套行为验收结论。
- 三个目录（内核、下载包、发布克隆）共 801 个当前变更文档的本地目标解析通过；各 README 有 19 张图片，23 节点 registry 单根、ID 唯一、关系可解析。
- 本次未修改 v1 运行源码，也未重写历史 acceptance evidence；历史脚本路径保持可复验。

- 当前成片 ffprobe：233.223 秒、1920×1080、30fps、H.264/AAC；四个副本 SHA-256 全部为 CAFF233FDFCA46015A98D126EC3E2325BD596A7164DBDE8F92641D64A72F9631。
- v5 的20条旁白与剪辑引用集合一致，真实素材/终端输入均存在，cards/assemble 内存编译通过。补齐发布导航引用的34份历史材料，复制前后摘要一致。
- 本次有明确依据的视频草稿/缓存/环境清理为 2043 文件、595162100 字节；逐文件清单在外层备份与整理记录/整理清单/2026-10-15.json。更早的 Python 缓存清理由前文检查点记录，不混入这个计数。

## 发布范围与授权

用户最新消息明确要求完成后推送版本，覆盖先前交接中只给命令的范围。发布目标沿用提交包的 LGZX2233/xiaobai2233 main；kernel_next 自身 origin 为另一个仓库，本轮不修改其索引、分支或远端。发布在隔离克隆准备，只包含本轮文档/媒体及导航所需的原始历史资料，不包含未提交的前端、R1 或 v1 运行时代码。实际提交与推送结果由 Git 历史和本轮远端回执定位，不预填成功。
