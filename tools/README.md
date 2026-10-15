# 内核复验工具

[verify_g2_evidence.py](verify_g2_evidence.py) 默认通过 docs/acceptance/G2/current.json 选择当前轮次，只读检查 G2 留档的源码/产物摘要、Python 语法、JSON/XML、本轮文档本地链接及测试计数。它不运行恢复，不启动 DSH，不修改冻结合同。

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/verify_g2_evidence.py
```

该脚本是可保留的维护工具；临时补丁脚本和故障注入数据不属于知识库材料。源码变化后，旧 manifest 校验失败是预期结果，必须完成新验收再登记新指纹，不能为了通过校验直接重写旧证据。

可用 --evidence-dir 指定内核目录下的历史证据包。历史包与当前源码不同而报 hash changed 是正常审计信号，不能用重新生成历史指纹掩盖变更。当前包保存测试样本并标为 test，不作为训练数据。

[capture_validation.py](capture_validation.py) 在内核目录运行显式命令，保存合并的原始 stdout/stderr 字节、命令参数、北京时间起止时间、退出码、输出摘要及源码/测试/协议文件指纹；运行期间文件改变会使 capture 退出失败，不能作为当前代码的通过证据。它不解析 shell，不读取环境凭证，不覆盖已有 capture。新尝试使用不同 capture 名称和 JUnit 文件名；旧输出留在原位置。测试使用内核目录下 `.validation-tmp/` 的独立临时目录，不能将运行数据库纳入提交。

第四轮校验同时核对冻结 25 项的条件观察、当前通过的精确 JUnit 用例、manifest 中的证据文件和独立裁决，整体现状必须与逐项接受一致。[archive_g2_scenarios.py](archive_g2_scenarios.py) 只接受显式临时根，另存合成场景的非数据库产物及所有文件摘要，跳过数据库字节和 pytest current 链接，不覆盖已有档案。[build_g2_round4.py](build_g2_round4.py) 在最终 capture 与单独复核裁决落盘后组装第四轮元数据，同时核对冻结输入和第三轮文件与基准提交的字节；它不能代替人工逐项裁决。

```powershell
& .venv/Scripts/python.exe -X utf8 -B tools/capture_validation.py --evidence-dir docs/acceptance/G2-round3/evidence --name python-verified -- .venv/Scripts/python.exe -X utf8 -B -m pytest tests -p no:cacheprovider --tb=short --basetemp=.validation-tmp/round3-verified --junitxml=docs/acceptance/G2-round3/evidence/pytest-verified.xml
```
