# CR-003：P08 四项 ChangeRequest 处置

1. **知识专用 DDL**：已合入（CR-002，use_event/outcome/promotion_task 三张 UNIQUE 表）。
2. **shared.sqlite 共享知识域 + SharedKnowledgeRef 跨库复制**：表结构已合入（identity 0002）；
   跨库复制逻辑与 SharedKnowledgeRef 持久化**后置**（依赖 P11 宿主 shared store 语义，
   记入 G2 报告为后置缺口，不静默丢弃）。
3. **Store/P06 类型化 list_revisions 读 API**：P08 暂以只读 SELECT 于自有 type 范围；
   本轮在 P06 QueryService 增加 `list_revisions(type, after_seq)`（见 P06 更新），
   P08 可后续切换（不强制本轮）。
4. **ContextPort/KnowledgePort 到 bootstrap 适配**：P13 在 composition root 按 Protocol
   骨架装配 ContextResolver/KnowledgeService；本轮 bootstrap 先接主链路（design/attempt/
   delivery/query），知识适配为后置（P08 能力已 owner 验收，装配随 P09/P11 收口）。
