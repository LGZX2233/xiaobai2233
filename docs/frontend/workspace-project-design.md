# 工作区与项目导入设计

文档版本：1.0.0；更新日期：2026-10-14（Asia/Shanghai）

## 核心概念

### 工作区 (Workspace)
用户本地环境的一个目录，管理若干关联的项目库。

### 项目 (Project)
一个独立的工程单位：
- `project.sqlite` — 项目库（版本化记录）
- `docs/modules/registry.json` — 模块树
- `docs/` — 架构、需求、任务记录

**访问边界**：
- 内核**只读取** `project.sqlite` 和 `docs/modules/registry.json`
- 其他文件由前端按需加载

### 导入 (Import)
把现有项目加载到工作区。源头可以是：
- 本地文件系统路径
- Git 仓库
- S3 或其他远程存储

---

## 场景

### 场景 1：新建工作区

用户：AGH 前端 → "新建工作区" → 选择本地目录

内核：调用 `project.provision` 初始化空数据库和目录结构

### 场景 2：导入现有项目

用户：AGH 前端 → "导入项目" → 选择源和名称

内核：调用 `project.import`
- 验证源的完整性
- 复制或链接到工作区
- 注册到元数据

### 场景 3：切换工作区/项目

用户：前端侧边栏切换

内核：调用 `project.select`，更新全局上下文

---

## 限制读取范围

**问题**：内核不能无限制读取工作区

**解决**：
1. 内核通过 `PROJECT_STORE_ROOT` 环境变量限制范围
2. 只允许读取白名单文件（project.sqlite、registry.json、架构文档）
3. 前端代理所有其他文件访问

---

## RPC 接口

| 命令 | 功能 |
| --- | --- |
| `workspace.list` | 列出所有工作区 |
| `workspace.create` | 创建新工作区 |
| `project.import` | 导入项目 |
| `project.select` | 切换项目 |

---

## 待实现

- [ ] RPC 实现
- [ ] 前端 UI（工作区选择器、项目导入对话框）
- [ ] 缓存策略
- [ ] 安全和权限隔离
