# AGH 只读多视图实施记录

日期：2026-10-13（Asia/Shanghai）；状态：只读阶段已实施并自测通过。要求由 [REQ-AGH-01 至 06](../../requirements/2026-10-13-agh-frontend.md) 和 [执行规格](../../../adapters/agh-plugin/docs/frontend-design.md) 拥有。

用户要求分发代理，实施分为后端服务、视图与文案、前端骨架与构建测试三个代理；根代理独立校对真实 RPC、执行集成测试并做浏览器检查。原仓库已有未提交和未跟踪文件，本次不提交或推送。因当前文件沙箱仅允许写 `D:\bisai`，先在 `D:\bisai\kernel-agh-work` 暂存可审查成果；回写原目录需要主机文件授权，并以基线摘要保护已有工作。

选择上下文为仓库 AGENTS、内核现状、模块目录、K-QUERIES、K-BRIDGE、适配器、QueryService、bootstrap RPC 装配与 AGH 客户端服务接口。项目维护使用 kernel-maintain-records 2.0.0，记录项目事实，不评价用户，不改试用 skill 评分或冻结证据。

真实响应探针在系统临时目录启动 Python 演示宿主，以 `-I -B -X utf8` 保护源码缓存。校对八个查询及 events.read；operation.status 使用一次 test s2 attempt 的真实操作。实测修正：events.read 也有 RPC 信封，其 data 才是数组；project.timeline RPC 不接受 limit；信封另含 projection_version、computed_at、source_watermarks。历史水位 0 可读，不用当前事实补造历史。

后端完成十一项只读浏览器服务、输入校验、白名单、queryEnvelope、历史水位及分页透传；旧 query 保持返回 data。文档服务不启动 Python，读不到或损坏时明确失败。并发调用复用启动，启动期间卸载清理子进程。

已执行后端真实服务及原工具集成检查，九项自测通过、无跳过，覆盖未知尝试保留、s2 验证、历史读取与文档服务。前端 SSR 与轮询测试 29/29 通过；独立 Chromium 检查十个视图、真实待审批弹层、历史水位、主题、语言、隐藏暂停轮询和移动端布局，`style` 属性为 0 且控制台无错误。证据见 `D:\bisai\kernel-agh-work\evidence\browser-results.json`。

隔离 AGH 检查只读取 `D:\agnes\runtime` 的既有可执行文件，AGH_HOME 指向新隔离目录，未启动或更改日常实例。隔离实例已完成 package inspect/install、精确 integrity/capability hash 信任、enable 和 status；状态为 `desired=enabled actual=running trusted=true`。真实 Web shell 已加载插件并显示一个面板和十个标签页；因未配置模型和活动会话，页面服务调用提示需先选择会话并启用 services，独立浏览器 harness 已用真实内核服务完成调用验证。

p15 展示测试在项目虚拟环境中修改断言后重新运行，命令为：
`D:\deepseekhannes\kernel_next\.venv\Scripts\python.exe -B -m pytest D:\deepseekhannes\kernel_next\tests\p15_innovation_showcase D:\deepseekhannes\kernel_next\tests\p14_science_demo -p no:cacheprovider -q`。
结果 `..... [100%]`，p15 三项与 p14 两项全部通过；JUnit 证据见 `D:\bisai\kernel-agh-work\evidence\p15-p14-final-results.xml`。

核心历史状态仍为 `accepted_g2`，`release_approved=false`。本次使用 test 证据及 `directory_only`，不代表操作系统沙盒、生产试点或新宿主接受；阶段 2 未实施。
