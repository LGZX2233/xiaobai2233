# 第四轮实际命令

工作目录始终显式为 `D:/deepseekhannes/kernel_next`。开始时工作区干净，HEAD 为 aca09b044c8138389039783152d0f1e13e58dba8，候选分支与远端一致，main 为初始提交。第三轮 verify_g2_evidence.py 实际 exit 0，246 文件和555不重复Python计数，problems为空。

分组代理的实际命令和反例见[执行审查](../../reviews/2026-10-09-round4/execution-review.md)、[交付审查](../../reviews/2026-10-09-round4/delivery-review.md)、[数据证据审查](../../reviews/2026-10-09-round4/data-evidence-review.md)及[协议独审](../../reviews/2026-10-09-round4/protocol-peer-review.md)。pytest 在沙箱中遇到项目临时目录 WinError 5，Node 遇到 spawn EPERM；原命令获准宿主执行后按产品断言复验。临时fixture和接线中间失败均保留，未把沙箱失败当成功，也未绕过产品断言。

最终联合命令由 [python-acceptance-final-result.json](evidence/python-acceptance-final-result.json) 和 [node-acceptance-final-result.json](evidence/node-acceptance-final-result.json) 记录实际 argv、工作目录、北京时间、退出码、原始输出和运行前后指纹，包含 tools/fixtures 验收输入。两次运行分别开始于2026-10-10 13:04:58和13:05:33。分组、peer 与历史结果不累加。

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round4/evidence --name python-acceptance-final -- .venv/Scripts/python.exe -X utf8 -B -m pytest tests -p no:cacheprovider --tb=short --basetemp=.validation-tmp/g2-acceptance-final --junitxml=docs/acceptance/G2-round4/evidence/pytest-acceptance-final.xml
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round4/evidence --name node-acceptance-final -- node --test bridge/protocol/golden_test.mjs bridge/protocol/client_test.mjs bridge/protocol/kernel_stdio_test.mjs
& .venv/Scripts/python.exe -X utf8 -B tools/archive_g2_scenarios.py --temp-root .validation-tmp/g2-acceptance-final --temp-root .validation-tmp/g2-round4-node-final/stdio-0dks45 --destination docs/acceptance/G2-round4/evidence/scenarios-acceptance-final
& .venv/Scripts/python.exe -X utf8 -B tools/build_g2_round4.py
& .venv/Scripts/python.exe -X utf8 -B tools/verify_g2_evidence.py
```

Git 操作仅普通提交与 fast-forward 推送，实际提交及远端核对另见[交接](../../handoffs/2026-10-09-g2-independent-acceptance.md)。未安装或启动 DSH，不调用模型、不导入生产数据、不训练或上传语料。

最终Python实际620 passed（32.49秒）、Node实际19 passed（683.1957毫秒）；两份capture都exit 0、217个输入指纹稳定。普通归档进程因Windows沙箱不能读宿主pytest临时树，只列6个文件并归档2个；该结果移入evidence/scenarios-incomplete-sandbox保留。历史宿主release归档列2336文件、归档413个非DB文件。2026-10-10宿主执行上述最终archive命令列2321文件、归档408个非DB文件，作为scenarios-acceptance-final证据；Node只选13:05:35生成的stdio-0dks45子目录。最终计数只来自python-acceptance-final、node-acceptance-final和pytest-acceptance-final.xml。

实际独立终审指出旧capture依赖未提交的生成安装元数据和四份文档检出EOL不稳定；新capture已使用排除`.egg-info`并固定EOL的工具与属性。旧capture及分组观察保持历史记录，当前条件的归档路径以checks.json为准。
