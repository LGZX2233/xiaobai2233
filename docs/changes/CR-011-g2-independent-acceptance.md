# G2 逐项独立验收整改

日期：2026-10-09，Asia/Shanghai。范围为未发布的 `kernel_next` 内部实现；冻结 wire schema、公共 DTO、错误码、项目 DDL、既有 ZIP 和第三轮证据保持原字节。

不同 task 或 strategy 的执行目录不能相同或互为父子目录，即使已有 attempt 已结束。活动或 unknown attempt 继续保留实际目录；更换 execution_root object ID 不解除目录占用。终态同策略重试仍产生新 attempt，保留失败版本。

正式交付同时核验快照证据模式与已持久化 attempt、execution packet 的 production 模式，provider 的生产检查报告不能把测试执行升级为生产事实。需求、方案与规则的关键版本发布后，失效批准记录为 superseded；无关名称与审计变化不改变批准。查询继续只读，原命令回执保持幂等。

归档保存 `source_collection_requested` 与当前本地采集状态，来源 gap 补齐后显式修复可重算本地完成状态；显式 false 不提升。来源未完成同时影响公开 archive.status 的 partial 与 gap。`source_flush_basis=local_observation_only` 和未配置 host final flush 的声明保持明确。

协议两端拒绝解析后非有限数值；Node 客户端按解码后的 key 检查重复，并对完整帧和未完成帧执行字节限额。公开 stdio test fixture 验证实际 Python 组合根与 Node 客户端的拆包、日志通道、丢失回执、进程重启和原 key 补查。

第四轮把冻结 25 项逐条条件、合法入口、实际合成产物、独立裁决与当前 JUnit 对齐。校验工具拒绝不完整条件、未留档证据、未运行用例或缺失独立裁决；当前总数只从最终一次联合 JUnit 读取。新证据见[第四轮报告](../acceptance/G2-round4-report.md)，旧轮次只保留历史记录。
