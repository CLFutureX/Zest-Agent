# 贡献指南 (Contributing)

感谢你对 Zest-Agent 的兴趣！本文档说明如何参与本项目。无论是 Issue 反馈、PR 修正、文档完善、场景分享，还是只是提问，都是宝贵的贡献。

> 在开始之前，请先阅读 [Code of Conduct](CODE_OF_CONDUCT.md)。参与本项目即视为遵守该准则。

---

## 一、快速上手

1. Fork 本仓库并克隆到本地：
   ```bash
   git clone https://github.com/<your-username>/Zest-Agent.git
   cd Zest-Agent
   ```
2. 按 [docs/quickstart.md](docs/quickstart.md) 完成本地开发环境搭建。
3. 安装 pre-commit 钩子：
   ```bash
   pip install pre-commit
   pre-commit install
   ```
4. 创建一个分支开始你的工作：
   ```bash
   git checkout -b feat/<short-description>
   ```

---

## 二、分支模型

| 分支 | 用途 |
|---|---|
| `main` | 稳定主干，所有发布基于此打 tag |
| `feat/*` | 新功能开发分支 |
| `fix/*` | Bug 修复分支 |
| `docs/*` | 仅文档变更 |
| `chore/*` | 构建、依赖、CI 等杂项 |

**分支命名**：`<type>/<short-kebab-case-description>`，例如 `feat/multi-agent-router`、`fix/websocket-reconnect`。

---

## 三、Commit 规范

本项目采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**type** 取值：
- `feat`：新功能
- `fix`：Bug 修复
- `docs`：文档变更
- `style`：代码风格调整（不改逻辑）
- `refactor`：重构
- `perf`：性能优化
- `test`：测试相关
- `build`：构建系统或依赖
- `ci`：CI 配置
- `chore`：杂项

**示例**：
```
feat(sdk): add multi-agent sub-agent dispatch skeleton
fix(app-server): correct session affinity key collision
docs(quickstart): add Windows PowerShell commands
```

**注意**：
- subject 用祈使句、小写、不超过 72 字符。
- body 说明 **为什么** 这样做，而非 **做了什么**（diff 已经说明）。
- 涉及 Issue 时在 footer 写 `Closes #123` 或 `Refs #456`。

---

## 四、Pull Request 流程

1. 在本地完成开发，确保：
   - 代码通过 `pre-commit run --all-files`
   - 测试通过 `make test`（或 `uv run pytest -q`）
   - 前端可构建 `make web-build`
2. 把你的分支 rebase 到最新 `main`：
   ```bash
   git fetch origin
   git rebase origin/main
   ```
3. 推送并创建 PR：
   ```bash
   git push origin feat/<your-branch>
   ```
4. 在 PR 描述中说明：
   - **变更摘要**
   - **关联 Issue**（如有）
   - **测试方式**（如何验证本次改动有效）
   - **Breaking changes**（如有，需显式标注）
   - **Checklist** 完成情况
5. 等待 Code Review，根据反馈迭代。

**PR 模板**（仓库 `.github/PULL_REQUEST_TEMPLATE.md` 已配置）：

```markdown
## 变更摘要
<一句话说清本 PR 做了什么>

## 关联 Issue
Closes #

## 变更类型
- [ ] feat 新功能
- [ ] fix Bug 修复
- [ ] docs 文档
- [ ] refactor 重构
- [ ] test 测试
- [ ] chore 杂项

## 测试方式
<如何验证本次改动有效>

## Breaking changes
- [ ] 无
- [ ] 有：<说明>

## Checklist
- [ ] pre-commit 已通过
- [ ] 测试已通过
- [ ] 文档已更新（如涉及）
- [ ] CHANGELOG 已补充（如涉及用户可见变更）
```

---

## 五、代码风格

### Python（后端）

- **Linter / Formatter**：`ruff`（已配置在 `.pre-commit-config.yaml`）
- **类型检查**：`mypy`（核心模块建议添加类型注解）
- **Import 顺序**：标准库 → 第三方 → 本项目，按字母序
- **行宽**：100 字符
- **命名**：
  - 模块、变量：`snake_case`
  - 类：`PascalCase`
  - 常量：`UPPER_SNAKE_CASE`
  - 私有：前缀 `_`

### TypeScript（前端）

- **Linter**：eslint（如已配置）
- **Formatter**：prettier
- **命名**：
  - 变量、函数：`camelCase`
  - 类型、接口、组件：`PascalCase`
  - 常量：`UPPER_SNAKE_CASE`

### 通用原则

- 优先可读性而非简短。
- 注释只写 **为什么**，不写 **做什么**。
- 不引入与任务无关的重构。
- 不为假想需求预留抽象。

---

## 六、测试

- **后端**：`uv run pytest -q`
- **前端**：暂未引入单元测试框架，鼓励新增
- **集成测试**：见 `zest-agent-server/test/` 目录示例

新增功能或修复 Bug 时，**强烈建议**补充对应测试用例。

---

## 七、Issue 与 Bug 报告

提交 Issue 前请：

1. 搜索现有 Issue，避免重复。
2. 使用对应模板（bug 报告 / feature 请求）。
3. Bug 报告请包含：
   - 复现步骤
   - 期望行为与实际行为
   - 环境信息（OS、Python 版本、Node 版本、Docker 版本、相关 `.env` 配置脱敏后内容）
   - 日志或截图

**安全漏洞请勿在公开 Issue 中报告**，请按 [SECURITY.md](SECURITY.md) 流程私下披露。

---

## 八、文档贡献

文档是开源项目的门面，我们重视文档贡献：

- 错别字、语法修正：直接小 PR
- 章节补充、新文档：先开 Issue 讨论结构与定位
- 翻译：欢迎补充其他语言版本，先开 Issue 对齐术语

---

## 九、开发流程小贴士

- **小步提交**：单个 PR 聚焦一件事，便于 Review。
- **保持线性历史**：项目启用 "Require linear history"，请用 `rebase` 而非 `merge`。
- **不要**在 PR 中混合无关改动（如格式化整个文件）。
- **不要** force-push 到 `main`。
- **不要**在 commit 中提交密钥、`.env`、构建产物。

---

## 十、署名与许可

本项目采用以下署名规则：
- 提交者保留 git commit author 信息。
- 显著贡献者将列入 `CONTRIBUTORS.md`（如未来添加）。
- 不强制要求 DCO sign-off，但鼓励使用 GPG 签名 commit。

**贡献许可**：向 Zest-Agent 提交的贡献（包括但不限于代码、文档、配置）在合并到本仓库后，将按 [Apache License 2.0](LICENSE) 第 5 条统一对外授权——除非你明确声明 otherwise，任何有意提交以包含在本项目中的 Contribution 均按本 License 条款授权，不附加任何额外条款。详见 [NOTICE.md](NOTICE.md) 的 "Contribution Licensing" 段。

**版权头建议**：新增源文件建议（非强制）在顶部加入 Apache 2.0 标准版权头，模板见 [NOTICE.md](NOTICE.md)。未来会通过 pre-commit 钩子批量校验。

---

## 十一、行为准则

参与本项目即视为同意遵守 [Code of Conduct](CODE_OF_CONDUCT.md)。不当行为请发邮件至维护者邮箱（见 SECURITY.md / CODEOWNERS）。

---

再次感谢你的贡献！每一个 Issue、PR、Star 都是支持。
