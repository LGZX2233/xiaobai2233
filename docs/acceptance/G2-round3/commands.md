# 第三轮实际验证命令

所有命令在 `D:/deepseekhannes/kernel_next` 执行，Python 使用项目已有 `.venv`，不安装依赖或启动 DSH。capture 保存原始 stdout/stderr、参数、退出码、北京时间和验证文件摘要。

## 最终联合回归

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round3/evidence --name python-verified -- .venv/Scripts/python.exe -X utf8 -B -m pytest tests -p no:cacheprovider --tb=short --basetemp=.validation-tmp/round3-verified --junitxml=docs/acceptance/G2-round3/evidence/pytest-verified.xml
```

实际 exit 0，555 passed in 23.95s，0 failed/errors/skipped；运行前后的源码、测试、协议和契约文件摘要一致。原始 capture 是[python-verified-result.json](evidence/python-verified-result.json)。临时根全部位于已忽略的 `.validation-tmp/round3-verified/`。

## 恢复目标回归

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round3/evidence --name recovery-target -- .venv/Scripts/python.exe -X utf8 -B -m pytest tests/p04_delivery/test_provider_recovery.py -p no:cacheprovider --tb=short --basetemp=.validation-tmp/recovery-target --junitxml=docs/acceptance/G2-round3/evidence/pytest-recovery-target.xml
```

首次 sandbox exit 1，pytest 私有临时目录访问被拒绝，未作为产品通过或失败结论；[原始失败](failures/recovery-target-sandbox/recovery-target-output.txt)与结果保留后，原命令以 host escalation 运行，exit 0，15 passed in 1.72s。该子集已包含在 555 项中。

## Node 协议

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round3/evidence --name node-verified -- node --test bridge/protocol/client_test.mjs bridge/protocol/golden_test.mjs
```

实际 exit 0，14 passed、0 failed；[原始 capture](evidence/node-verified-result.json)及输出保留。此前 sandbox 的直接 Node 测试因 `spawn EPERM` 无法创建测试子进程，已获准在宿主执行。本次记录最终 LF 文件字节的指纹，与当前源码一致。

## 历史与独立复验

[python-all-result.json](evidence/python-all-result.json) 与 [pytest-final.xml](evidence/pytest-final.xml) 是 545 项通过的中间快照，早于最后的恢复目标校验；[python-final-result.json](evidence/python-final-result.json) 与 [pytest-current.xml](evidence/pytest-current.xml) 是 547 项中间快照，尚未包含 8 项证据校验测试。两者不作为当前总数。第二轮只读校验的 9 项 hash mismatch 在[历史校验记录](failures/round2-manifest-recheck.json)保留，第二轮 manifest 不重写。

独立审查者运行 provider 恢复和非文件 RPC 用例，17 passed in 1.95s；精确命令和审查范围见[独立报告](../../reviews/2026-10-09-round3/provider-independent-review.md)。这些是联合测试的重叠子集。

## 只读证据校验

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/verify_g2_evidence.py
```

默认根据 `docs/acceptance/G2/current.json` 选择第三轮，核对当前文件摘要、冻结 contract digest、JUnit 唯一计数、capture 的退出码/输出摘要/当前源码指纹以及文档链接。实际结果归档于[verification-result.json](verification-result.json)。未运行 DSH 的 pnpm gates；这是独立 Python 项目，其检查不需要 DSH 安装或构建。
