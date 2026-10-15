# 演练摘要（rehearsal outside AGH）

**rehearsal outside AGH (direct API), same plugin tools and kernel; not the AGH run.**

- 模型通过各自厂商的 chat-completions 接口直接调用 `adapters/agh-plugin` 的同一组 `createTools` 工具，连接同一个 Python 内核（`tests/p14_science_demo/agh_host.py`，stdio JSON-RPC）。
- 这不是 AGH 里的运行；AGH 里的运行见 `evidence/agh-run`（如果存在）。
- 证据模式 test；数据为合成、确定性数据；批准一步由操作员脚本调用 `tools/pk_human_approve.py` 的 `decide()` 完成，记录为 `human step performed by operator script in rehearsal`，模型本身没有批准能力。
- 提示词全文见 `prompt.md`；逐条消息、工具调用、结果、时间戳、用量见各 `*.jsonl`。

| 记录文件 | 模型（接口返回） | 状态 | 工具顺序 | 选中 | 最终 alpha | 操作状态 | 提前 apply | 总 token |
|---|---|---|---|---|---|---|---|---|
| 20261015-084342-deepseek-flash.jsonl | deepseek-flash | finished（成功） | pk_state → pk_run_strategy(s1) → pk_run_strategy(s2) → pk_run_strategy(s3) → pk_verify(s1) → pk_verify(s2) → pk_compare → pk_select(s2) → pk_request_delivery → pk_apply_delivery | s2 | 0.3728610547894271 | applied | 否 | 29727 |
| 20261015-084544-agnes-3.0-flash.jsonl | agnes-3.0-flash | finished（成功） | pk_state → pk_run_strategy(s1) → pk_run_strategy(s2) → pk_run_strategy(s3) → pk_verify(s1) → pk_verify(s2) → pk_verify(s3) → pk_compare → pk_select(s2) → pk_request_delivery → pk_apply_delivery | s2 | 0.3728610547894271 | applied | 否 | 29393 |
| 20261015-084812-deepseek-flash.jsonl | deepseek-flash | finished（成功） | pk_state → pk_run_strategy(s1) → pk_run_strategy(s2) → pk_run_strategy(s3) → pk_verify(s1) → pk_verify(s2) → pk_verify(s3) → pk_compare → pk_select(s2) → pk_request_delivery → pk_apply_delivery | s2 | 0.3728610547894271 | applied | 否 | 30515 |
| 20261015-084836-agnes-3.0-flash.jsonl | agnes-3.0-flash | finished（成功） | pk_state → pk_run_strategy(s1) → pk_run_strategy(s2) → pk_run_strategy(s3) → pk_verify(s1) → pk_verify(s2) → pk_verify(s3) → pk_compare → pk_select(s2) → pk_request_delivery → pk_apply_delivery | s2 | 0.3728610547894271 | applied | 否 | 30985 |

## 20261015-084342-deepseek-flash.jsonl

- 请求的模型 id：deepseek-flash；接口返回的模型 id：deepseek-flash；接口 /models 列出：deepseek-flash, deepseek-v4-pro
- 接口调用次数：9；用量：prompt 28345 / completion 1382 / total 29727
- s3 状态：unknown；s1 通过：false；s2 通过：true
- 选择理由（模型写的）：s2（黄金分割）alpha≈0.37286，与闭式解 0.3786 相对偏差约1.5%，在5%容差内，独立校验通过；s1 校验失败、s3 卡住。
- 申请交付后的审批状态：pending；人工步骤已执行：true；apply.applied：true；operation_id：operation-a50ca44472e607d3265a
- 工具报错：无
- 耗时：22 s

## 20261015-084544-agnes-3.0-flash.jsonl

- 请求的模型 id：agnes-3.0-flash；接口返回的模型 id：agnes-3.0-flash；接口 /models 列出：agnes-2.5-flash, agnes-3.0-flash, agnes-image-2.1-flash, agnes-image-2.5-flash, agnes-video-2.5-flash
- 接口调用次数：9；用量：prompt 28542 / completion 851 / total 29393
- s3 状态：unknown；s1 通过：false；s2 通过：true
- 选择理由（模型写的）：黄金分割法得到的 alpha≈0.3729 通过独立校验（与闭式解偏差 <5% 容差），s1 失败、s3 卡死不可用
- 申请交付后的审批状态：pending；人工步骤已执行：true；apply.applied：true；operation_id：operation-cda343b70452bfd773f8
- 工具报错：pk_verify:RPC_-32000
- 耗时：22.2 s

## 20261015-084812-deepseek-flash.jsonl

- 请求的模型 id：deepseek-flash；接口返回的模型 id：deepseek-flash；接口 /models 列出：deepseek-flash, deepseek-v4-pro
- 接口调用次数：9；用量：prompt 29172 / completion 1343 / total 30515
- s3 状态：unknown；s1 通过：false；s2 通过：true
- 选择理由（模型写的）：唯一通过独立校验的策略：golden-section 得 alpha≈0.37286，与闭式解 0.3786 偏差在 5% 容差内。
- 申请交付后的审批状态：pending；人工步骤已执行：true；apply.applied：true；operation_id：operation-8c0c45fbe1a6ab31f4f5
- 工具报错：无
- 耗时：23.2 s

## 20261015-084836-agnes-3.0-flash.jsonl

- 请求的模型 id：agnes-3.0-flash；接口返回的模型 id：agnes-3.0-flash；接口 /models 列出：agnes-2.5-flash, agnes-3.0-flash, agnes-image-2.1-flash, agnes-image-2.5-flash, agnes-video-2.5-flash
- 接口调用次数：9；用量：prompt 29872 / completion 1113 / total 30985
- s3 状态：unknown；s1 通过：false；s2 通过：true
- 选择理由（模型写的）：s2 golden-section search 是三项中唯一通过独立校验（passed=true, alpha_fit=0.37286, 在 5% 容差内），s1 校验失败, s3 卡住无法校验。
- 申请交付后的审批状态：pending；人工步骤已执行：true；apply.applied：true；operation_id：operation-c916c55921b8657cde74
- 工具报错：无
- 耗时：31.7 s

## 备注（人工整理：运行次数与改动）

运行记录（共 4 次，全部保留，没有挑选）：

- 08:43 deepseek-flash、08:45 agnes-3.0-flash：第一次运行。两个模型都走完整条流程（运行 s1/s2/s3、校验、比较、选 s2、申请交付、人工步骤、apply，operation 为 applied）。agnes 额外对 s3 调用了 pk_verify，工具返回了宿主的原始错误 `RPC_-32000 FileNotFoundError ... s3/result.json`（卡住的尝试没有结果文件），模型没有被它带偏，但这是工具的缺口。
- 改动（改的是工具，不是提示词）：`adapters/agh-plugin/index.mjs` 的 `pk_verify` 对未完成的尝试（例如 s3，状态 unknown）直接返回 `skipped: true, passed: false` 和原因“无结果可校验，作为失败样本保留，不会重跑”，不再把宿主错误抛给模型；描述里也写明了这一点；`test/tools.test.mjs` 增加了对应断言。
- 08:48 deepseek-flash、08:48 agnes-3.0-flash：改动后的第二次运行，两个模型都对 s3 调用 pk_verify 得到 skipped，其余流程相同，最终均为 s2、alpha 0.3728610547894271、operation applied。
- 提示词在四次运行中完全相同（见 prompt.md），没有为通过而修改提示词。
- 这些是单次运行（temperature=0），不是统计结论；API 侧仍可能有非确定性。

