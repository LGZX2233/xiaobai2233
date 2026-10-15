# 演练使用的提示词

rehearsal outside AGH (direct API), same plugin tools and kernel; not the AGH run.

## system

你是一个科研智能体，通过提供给你的工具完成任务，用中文简洁回答。

## user（一个人在 AGH 里会输入的话）

我有一个一维热传导反问题：反演扩散系数 alpha，验收容差 5%。请用 Project Kernel 的 pk_* 工具，把可用的策略都跑一遍并逐个做独立校验，失败和卡住的结果都要保留，不要删除或重跑；然后比较，选出通过校验的策略并写明理由，申请交付。交付必须由人工审批，你不能批准：申请之后请停下来告诉我，等我说“已批准”后再完成交付，并汇报最终的 alpha 和操作状态。

## 人工批准之后追加的 user 消息

已批准。请完成交付，并告诉我最终的 alpha 和操作状态。

## 工具

与 `adapters/agh-plugin/index.mjs` 的 `createTools` 完全相同（pk_state、pk_run_strategy、pk_verify、pk_compare、pk_select、pk_request_delivery、pk_apply_delivery、pk_events）；
参数 schema 去掉 TypeBox 的 Kind 符号后作为 OpenAI function tools 传给接口，`tool_choice=auto`，`temperature=0`。
