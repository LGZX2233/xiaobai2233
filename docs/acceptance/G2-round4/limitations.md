# 第四轮范围限制

G2 仅裁决冻结 AC12–32、AC37–38、AC43、AC45 的独立核心。可信人类动作为显式 synthetic verified test proof，执行为固定本地 Python subprocess，实际保证为 directory_only。所有生产模式入口只作负向模式校验，不声称生产执行。

真实 DSH、Session、Jobs、工具事件、取消、沙盒与宿主 final flush 属 G3；真实工作台属 G4；生产恢复及真实试点后置。没有将这些未实施能力当作 G2 阻断条件。平台只能称可适配，不能称已兼容。

来源 source_flushed 表示 source_flush_basis=local_observation_only 的本地采集就绪；session_flush 继续 not_configured。交付未知效果保留回执与 blocker，查询、重放与显式对账不重复写入；没有后台自动对账 worker。

恢复只接受显式临时 test stores。业务 restore RPC 的成功路径为隔离副本；ControlledStoreRecovery.apply 是停止写者后的独立离线维护入口，保留原库、备份后历史及外部审计。维护 fence 只覆盖协作 Kernel Store 写者，直接 SQLite 客户端不参与。生产替换禁用。

迁移只读真实临时 SyntheticLegacySample 和可信不可变 snapshot；不导入旧项目或生产数据。读模型 rebuild 采用导出的只读 QueryService API 并比对公开 RPC 结果；冻结 catalog 没有 projection.rebuild RPC，persisted=false，不声称持久投影 checkpoint。

host-owned provider 配置、候选、目标及来源版本明确作为 fixture 登记，不充当业务命令的通过证明。当前 knowledge/corpus 可选能力的正式接受属于 G2-K；目标用户知识树只规划，不训练、不上传、不导入生产语料。

完整验收总数只读最终一次联合 JUnit；分组和独立复跑均与它重叠。运行 DB/WAL/SHM 只保存路径和摘要，不入 Git。第三轮文件、冻结契约和既有 ZIP 的字节保持不变；它们与当前源码不同的旧指纹不重写。
