# 演示视频用图(仅含已实现并测过的部分)

## 1. 分层与信任边界

```mermaid
flowchart LR
  subgraph AGH[Agnes Harness]
    LLM[模型 / 会话] --> TOOLS[pk_* 工具]
    PANEL[工作台面板 只读]
  end
  subgraph PLUGIN[agh-plugin 适配层]
    TOOLS --> SESSION[KernelSession<br/>幂等键 + 超时后按原键补查]
    PANEL -->|pk.* 查询服务| SESSION
  end
  SESSION -->|stdio JSON-RPC<br/>机器句柄| HOST[Python 宿主 agh_host]
  HOST --> KERNEL[Project Kernel<br/>UnitOfWork / 不可变 revision]
  HOST --> EXEC[HeatInverseExecutor<br/>start / poll]
  EXEC --> SOLVER[外部求解器子进程<br/>FTCS 有限差分 + 参数反演]
  HOST --> CHECK[HeatCheckProvider<br/>闭式解独立重算]
  HUMAN[独立人工入口] -.->|approval.decide<br/>机器通道不可达| KERNEL
```

## 2. 一次任务的执行流

```mermaid
flowchart TB
  A[任务与验收标准<br/>真值 alpha=0.37 容差 5%] --> B[dispatch.confirm 冻结执行包]
  B --> C1[s1 粗网格]
  B --> C2[s2 黄金分割]
  B --> C3[s3 故意停滞]
  C1 --> V1[verification.run<br/>未通过]
  C2 --> V2[verification.run<br/>通过]
  C3 --> U[attempt = unknown<br/>不重跑 不当作成功]
  V2 --> S[attempt.select 保留比较理由]
  S --> R[delivery.request 冻结快照]
  R --> H{人工审批}
  H -->|批准| AP[delivery.apply]
  AP --> O[效果观察 applied]
```

## 3. 三类测试样本与对应机制

| 样本 | 输入 | 预期 | 机制 |
| --- | --- | --- | --- |
| 正常 | 黄金分割 | 验收通过,交付 applied | 独立校验器 + 人工审批 |
| 边界 | 伪造 alpha_fit=0.9 | 验收不通过 | 校验器自行重算,不信求解器自报 |
| 边界 | 机器通道 approval.decide | UNSUPPORTED_COMMAND | 人工专属命令 |
| 失败 | s3 停滞超时 | attempt=unknown,启动次数不增加 | 未知结果不自动重放 |

## 说明
- 证据模式为 test,求解器是真实子进程,隔离级别 directory_only,不是操作系统沙盒。
- 内核自测通过,验收状态为 accepted_g2,release_approved=false。
- 本文件不含:attempt 级对账、AGH 内的真实运行结果、人工审批的 AGH 侧入口,这些尚未实现或未验证。
