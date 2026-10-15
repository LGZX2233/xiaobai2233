# CR-010 交付效果 provider 收口

日期：2026-10-09。范围：未发布的 `kernel_next` 内部 API。该变更不修改 `contracts/v1`、Session API 或历史验收包。

## 变更

`DeliveryService` 通过 `DeliveryProvider` 接收交付写入和效果观察。`KernelServices`、`build_server` 与 `build_human_server` 接受 `delivery_provider=`；文件部署可传 `bundle_exporter=`，组合根把它包装成 `BundleDeliveryProvider`。两个参数同时配置会抛出 `ValueError`，两个参数都缺省时不创建默认 provider，交付能力在公开入口表现为 `CAPABILITY_UNAVAILABLE`。

provider 公开 `sink_ids`、`target_matches()`、`apply()` 和 `observe()`。应用层继续拥有项目授权、冻结目标、快照摘要、claim、apply-start、epoch、事务和结算；provider 只拥有外部 sink 的写入、目标定位和效果读取。自定义交付 provider 不隐式提供 archive、backup 或 restore。

## 效果语义

`apply()` 的异常不能证明写入没有发生；应用层调用只读 `observe()`，将无法确认的结果结算为 `unknown`，保留原 command receipt 和 provider receipt。`observe()` 不得写入 sink。重放、查询和 `delivery.reconcile` 只读取效果，不再次调用 `apply()`；成功状态还必须匹配操作身份及预期 manifest digest。没有 provider 时不得凭文件路径推测效果。

## 消费者与验证

当前消费者是 [`application/delivery/service.py`](../../src/project_kernel/application/delivery/service.py) 和 [`bootstrap.py`](../../src/project_kernel/bootstrap.py)。文件实现位于 [`evidence/delivery_provider.py`](../../src/project_kernel/evidence/delivery_provider.py)，端口位于 [`internal/delivery_provider_ports.py`](../../src/project_kernel/internal/delivery_provider_ports.py)。当前 provider 版本通过 555 项 Python 联合回归；独立 provider/RPC 子集为 17 项，计数不与联合结果叠加。命令、指纹和限制见[第三轮报告](../acceptance/G2-round3-report.md)。第二轮测试数量不证明本变更已通过。
