运行记录（共 4 次，全部保留，没有挑选）：

- 08:43 deepseek-flash、08:45 agnes-3.0-flash：第一次运行。两个模型都走完整条流程（运行 s1/s2/s3、校验、比较、选 s2、申请交付、人工步骤、apply，operation 为 applied）。agnes 额外对 s3 调用了 pk_verify，工具返回了宿主的原始错误 `RPC_-32000 FileNotFoundError ... s3/result.json`（卡住的尝试没有结果文件），模型没有被它带偏，但这是工具的缺口。
- 改动（改的是工具，不是提示词）：`adapters/agh-plugin/index.mjs` 的 `pk_verify` 对未完成的尝试（例如 s3，状态 unknown）直接返回 `skipped: true, passed: false` 和原因“无结果可校验，作为失败样本保留，不会重跑”，不再把宿主错误抛给模型；描述里也写明了这一点；`test/tools.test.mjs` 增加了对应断言。
- 08:48 deepseek-flash、08:48 agnes-3.0-flash：改动后的第二次运行，两个模型都对 s3 调用 pk_verify 得到 skipped，其余流程相同，最终均为 s2、alpha 0.3728610547894271、operation applied。
- 提示词在四次运行中完全相同（见 prompt.md），没有为通过而修改提示词。
- 这些是单次运行（temperature=0），不是统计结论；API 侧仍可能有非确定性。
