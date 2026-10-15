# G2 最终验收远端同步记录

日期：2026-10-10（Asia/Shanghai）。所有命令显式使用`D:/deepseekhannes/kernel_next`，仓库为`https://github.com/LGZX2233/xiaobai.git`，分支为`codex/kernel-independent`。本记录保存验收整改提交的实际推送与独立远端读取结果；记录本身随后以普通文档提交归档。

验收整改提交为`c60910394c764029f2f2af246b5db6210d74002e`，父提交为`124f2d6dc85ea707be3ec3b9e40ca51642ba696d`。普通推送成功输出为`124f2d6..c609103 HEAD -> codex/kernel-independent`。未重写历史，没有推送main。

推送后实际远端读取结果：

```text
c60910394c764029f2f2af246b5db6210d74002e refs/heads/codex/kernel-independent
1d9e82bae2b740e884c2ecc5639d124bb829f47f refs/heads/main
```

实际成功命令为：

```powershell
git -c http.version=HTTP/1.1 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 push origin HEAD:refs/heads/codex/kernel-independent
git -c http.version=HTTP/1.1 ls-remote origin refs/heads/codex/kernel-independent refs/heads/main
```

沙箱Git代理无法连接，宿主首次推送连接被重置，随后HTTP/1.1普通重试成功。推送后远端读取也出现临时连接失败；未认证GitHub refs API返回404，没有作为核对依据。上面的最终值来自使用已有Git凭据的成功ls-remote，不是本地origin缓存。

冻结25项、87条件均accepted，G2状态为accepted_g2，release_approved=false。实际独立审查者g2_final_audit签署AC45，协调者只登记该结论并重建清单。最终620项不重复Python与19项Node通过，217个验证输入指纹稳定；分组和peer子集包含在全量中，不累加。[报告](../acceptance/G2-round4-report.md)、[独立签字](../reviews/2026-10-09-round4/ac45-final-peer-review.md)与[逐项裁决](../reviews/2026-10-09-round4/independent-decisions.json)可直接检查。

验收提交的1280项manifest文件逐项通过当前字节与Git index检出字节比较，53项保护输入与基准Git blob一致；暂存检查无问题，git diff --cached --check通过。新场景归档索引2321文件，保存408个非数据库文件，909个DB/WAL/SHM条目仅保留路径及摘要。[验证回执](../acceptance/G2-round4/verification-result.json)记录当前包的校验结果；同步文档归档后清单会增加该文档，测试输入与计数保持一致。

冻结契约、fixtures、第三轮原始资料和既有ZIP未修改，没有提交运行数据库或缓存。仅修改kernel_next；没有安装或启动DSH、调用付费模型、导入生产数据、训练或上传语料。真实DSH属G3，工作台属G4，生产恢复后置；平台仅可适配，目标用户知识树只规划。G2接受范围保持为独立核心的合成test验收。

文档归档完成后的最终HEAD以最后一次成功远端核对为准。后续工作需选择新授权范围，当前验收任务不延伸到G3/G4或生产发布。
