# AGH 只读前端接入要求

日期：2026-10-13（Asia/Shanghai）。用户交付 [前端执行规格](../../adapters/agh-plugin/docs/frontend-design.md)，并要求分发代理执行。范围为阶段 0 的真实响应校对与阶段 1 的只读多视图；不进入第二阶段的写入、宿主需求录入或新增知识 RPC。

| ID | 要求 |
| --- | --- |
| REQ-AGH-01 | 实测查询信封，保留读取水位、完整度、缺口、分页与历史水位 |
| REQ-AGH-02 | 提供总览及九个指定视图；审批队列读取 queue，阶段推断读取 verification_result |
| REQ-AGH-03 | 实时、文档声明、派生、设计预览明确标注；不把示例、未知成本或人审准许当执行完成 |
| REQ-AGH-04 | 不增加浏览器写入或审批按钮；保留独立人工入口 |
| REQ-AGH-05 | 宿主 React ESM、单入口打包、中英文、主题订阅、可见性轮询、退避、无内联样式及减弱动效 |
| REQ-AGH-06 | 执行服务、工具、渲染与浏览器检查；隔离安装失败必须记录，不改日常实例或 AGH 源码 |

影响节点为 K-BRIDGE，消费 K-QUERIES 的现有只读 RPC，导航依赖不变。成果和未验证事项见 [任务记录](../records/tasks/2026-10-13-agh-frontend.md)。历史 G2、冻结原始证据及 `release_approved=false` 不受本次工作影响。
