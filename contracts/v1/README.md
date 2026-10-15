# v1公共schema

版本1.0.0。所有schema使用JSON Schema 2020-12。https://project-kernel.invalid/design/v1/只是稳定标识，不可发起网络获取；resolver必须将这些ID映射到本目录本地文件。

命令校验分两层：command-envelope.schema.json检查JSON-RPC信封，再从params取{command,payload}用command-payloads.schema.json检查领域字段；查询同理。全部additionalProperties=false，通用payload只在第二层检查，不允许跳过。schema能检查字段与类型，actor、FK、scope、状态、required证据、digest和权限仍由服务执行。

Snapshot schema包含evidence_mode；test对象仅用于隔离测试，production freeze必须拒test证据。枚举中只提供bundle方法，Git未接。金额/split总和、同项目ref、set类数组排序/去重、旧批准失效是业务校验，不能声称schema自动保证。

ObjectRef精确引用revision；safe_details只放可公开键值，不放可信上下文句柄。源payload使用artifact引用，外部大输出不塞入RPC信封。command_receipt.result_refs取代不受约束result字典；具体返回视图由query typed DTO提供。

P00实现生成DTO/验证器及ports，保持本包字段和语义。P10与P00共同运行goldens，只有P00能改变schema。生成类型不允许手工复制两份演化。

examples.json定义有效和无效结构样例；它不证明权限/状态或实际执行成功。golden-digests.json包含独立可重算的规范文本与SHA-256，实际JCS库要逐项验证。
