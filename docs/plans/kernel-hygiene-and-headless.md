# 持续任务：项目整洁、低耦合与无界面接入

任务 ID：KERNEL-GROWTH-20261015；状态：planned；更新：2026-10-15。来源为用户本轮要求；事实主人是本计划，实际检查与删除清单归[整理记录](../records/tasks/2026-10-15-kernel-cleanup.md)。以下项目不等于已实现。

| ID | 工作与验收 | 状态 |
| --- | --- | --- |
| CLEAN-01 | 派发声明 output kind、相对路径、数量/大小预算和保留期；证明越界/超额输出被阻断或隔离 | planned |
| CLEAN-02 | 输出绑定 attempt、来源版本、真实摘要；无主文件进入 quarantine；验收拒绝把草稿当正式记录 | planned |
| CLEAN-03 | 关闭任务生成采用/未采用/失败/临时清单；引用扫描与保留期保护证据；dry-run 展示删除及可恢复位置，再按授权执行 | planned |
| CLEAN-04 | 将路径约束接到宿主沙箱/provider，测试写越界、符号链接、取消和 unknown；文档约定不能代替强制控制 | planned |
| MOD-01 | 对齐调用方 ports、组合根 capability 与禁用行为；新增模块声明所有者/依赖/错误语义，导入边界检查持续通过 | planned |
| MOD-02 | 按用例抽取 application SQL 至拥有数据的模块，保持 UoW、幂等及并发语义；切片行为验证后再迁移下一项 | planned |
| HEADLESS-H0 | skill/command/capability 矩阵，列出覆盖、禁用与可信人审路径 | planned |
| HEADLESS-H1 | 状态、ContextManifest、事件和追溯的只读 skills；验证重启、水位、scope、版本引用 | planned |
| HEADLESS-H2 | 设计/派发/attempt/verify skills；验证取消、幂等、超时补查、来源 flush 和 unknown | planned |
| HEADLESS-H3-H5 | 审阅与交付、逐框架桥接、skill 真实复用评价；机器不可批准，禁止把单宿主通过外推全部宿主 | planned |

每个实现切片先选择模块及验收输入，再更新源码、模块节点、记录和实际检查。不自动创建后台清理器，不因文件旧或一次失败而删除原始证据，不自动重试 unknown。当前详细设计与边界见[设计与成长](../architecture/kernel-design-and-growth.md)。
