# CR-006：组合根接线、decision.record 与 AC26 冻结门（跨 owner，P13 代行）

- 提出者：P13（集成验收）
- 涉及 owner：P13（`bootstrap.py`）、P04（`application/delivery/service.py`）、P05（freeze 门调用点）、
  P09（`corpus/service.py` 导出授权形状）、P10（协议装配面）
- 结论：**已由 P13 实施并验证**；未改 `contracts/`、schema/DDL、公共 DTO、错误码、`data/store/`

各 owner 在并行实施结束后已离线，以下三项属于「集成方可直接完成且不做则声明面与实际能力不一致」
的接线/收尾工作，故由 P13 按冻结契约代行，并在此备案。

## 1. 组合根接线（`bootstrap.py` 重写）

原先 `build_server` 只接了 6 条命令、4 条查询，其余命令在协议面回 `UNSUPPORTED_COMMAND`，
即「声明面远小于 allowlist」。现改为**服务容器 `KernelServices` + 两个入口**：

- `build_server(...)`：机器入口。`supported_commands` = `MACHINE_COMMANDS`（16 条），
  `supported_queries` = `QUERY_NAMES`（12 条）；传 `allowlist=MACHINE_COMMAND_ALLOWLIST`，
  由 P10 的 `CommandSurface` 在**装配期**校验「声明面 ⊆ allowlist」且「声明面 ∩ human-only = ∅」，
  矛盾即抛 `ProtocolSurfaceError`（fail-fast，不静默降级）。
- `build_human_server(...)`：人类入口。`supported_commands` = 冻结的 5 条 human-only，
  `human_only_commands` 置空（它是这些命令唯一的合法出口），查询面为空。
- 命令上下文（principal/能力）**只取自已解析的句柄**（`current_machine_context()`），
  不做 payload 反序列化；`invocation_context_id` 由协议层 `strip_invocation_context` 剥离。
- `compute_input_hash` 复用 P10 实现（与 `bridge/protocol` 金样同源）。

## 2. `decision.record`（设计 04 §9 / 09）

按目录它属 P04；P04 handoff 未实现该方法，而 `dataset.export` 的授权对象就是它，缺它则
P09 的导出链不可完成。实现要点：

- human-only（`_require_human`），`action → (subject_kind, capability)` 严格映射：
  `restore.apply→(restore_plan, project.admin)`、`knowledge.promote→(knowledge_promotion,
  knowledge.share)`、`dataset.export→(dataset_export, dataset.export)`；
  **没有「human 全能免检」权限**，且 delivery approval 不可替代这三类授权。
- `subject_digest` 必须等于库内该 revision 的真实 digest（否则 `ARTIFACT_DIGEST_MISMATCH`）；
  subject/action/target_scope 不匹配、`target_ref` 非本项目内不可变描述即拒。
- 落 `type=decision` revision（schema `p04.decision.v1`）并审计 `decision.recorded`。

## 3. `dataset.export` 定位修正（P09）

设计 04 §9 说明它由「相同目标的 `human_decision_ref`」授权，与 `delivery.apply` 由 approval
授权同构，因此 `dataset.export` 是**机器命令**、authorization 来自 decision revision。
`CorpusService.export` 相应不再要求调用方自称 human，改为核验 decision
（`action=dataset.export`、`is_human`、subject/target 之一为 reviewed revision、digest 对齐），
并保持「样本须全部 accepted」「manifest 必须 complete」「已发布 version 不覆盖」三条不变。

## 4. AC26 冻结门（P05 CR-A 闭环）

`DeliveryService` 新增可选 `artifact_storage`；`freeze_snapshot` 在存在该依赖时对 body 中
`required=true` 的 artifacts 调 `ArtifactStorage.require_ready`，缺失/未 ready/digest 变化即拒。
`KernelServices` 在配置了 artifact 根时自动注入。未注入 storage 的部署仍以 verification 证据门把关。

## 5. 证据

```
pytest tests -p no:cacheprovider                     → 362 passed
node --test bridge\protocol\golden_test.mjs          → 3 pass / 0 fail
node --test bridge\protocol\client_test.mjs          → 11 pass / 0 fail
compute_bundle_digest()                              → d5fe5816…c97cc（零漂移）
```
新增 `tests/p13_integration/test_wiring.py`（7 项）：逐条声明命令都到达 handler（空 payload 得
`INVALID_INPUT` 而非 "no handler"）、human-only 只在人类入口、人类入口拒收机器句柄 / 验证人句柄可
完成真实批准、空库 12 条查询真实作答、`dataset.build`→`dataset.preview` 走真实 RPC、freeze 门、
以及 human→machine 导出链（含 subject_kind / digest 不符被拒）。

## 6. 未变的边界与遗留

未改契约/schema/DDL/公共 DTO/错误码/`data/store/`；未接 DSH/Git/付费模型。
仍未接线命令逐条列在 `docs/handoffs/P13.md` §10，协议面如实回 `UNSUPPORTED_COMMAND`。
