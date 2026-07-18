# NOTICE

This file is part of Zest-Agent.

Zest-Agent
Copyright 2026 CLFutureX

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

## Upstream Attribution (Derivative Work Notice)

This product includes code that was derived from
[OpenHands](https://github.com/All-Hands-AI/OpenHands)
("OpenHands") by All Hands AI.

OpenHands is licensed under the MIT License. As required by the MIT
License terms, the original copyright notice and permission notice are
reproduced below:

```
MIT License

Copyright (c) 2025 All Hands AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Zest-Agent 的核心运行时（AgentRunner 调度层、Agent 启动调度模型、断点恢复、数据存储抽象、沙箱隔离机制、事件模型与状态机、多层记忆体系）均为自研设计与实现。仅复用了 OpenHands 的部分组件作为基础积木：

- 部分工具实现（如 bash 解析、文件编辑器的部分逻辑片段）
- 部分数据模型片段（消息格式、工具调用 schema 等）

我们感谢 OpenHands 团队为开源 Agent 生态做出的杰出贡献。

---

## Third-Party Dependencies

Zest-Agent 使用以下开源依赖（按模块分组）。各依赖的完整 License 文本见其仓库或本地 `site-packages` / `node_modules`。

### Backend — Python

| 依赖 | License |
|---|---|
| [FastAPI](https://github.com/tiangolo/fastapi) | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT |
| [uv](https://github.com/astral-sh/uv) | MIT OR Apache-2.0 |
| [Litellm](https://github.com/BerriAI/litellm) | MIT |
| [Langfuse](https://github.com/langfuse/langfuse) | MIT |
| [FastMCP](https://github.com/jlowin/fastmcp) | Apache-2.0 |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | MIT |
| [Alembic](https://github.com/sqlalchemy/alembic) | MIT |
| [asyncpg](https://github.com/MagicStack/asyncpg) | Apache-2.0 |
| [aiomysql](https://github.com/aio-libs/aiomysql) | MIT |
| [motor](https://github.com/mongodb/motor) | Apache-2.0 |
| [redis-py](https://github.com/redis/redis-py) | MIT |
| [Elasticsearch Python Client](https://github.com/elastic/elasticsearch-py) | Apache-2.0 |
| [websockets](https://github.com/python-websockets/websockets) | BSD-3-Clause |
| [wsproto](https://github.com/python-hyper/wsproto) | MIT |
| [Libtmux](https://github.com/tmux-python/libtmux) | BSD-3-Clause |
| [Bashlex](https://github.com/idank/bashlex) | GPL-3.0-only |
| [browser-use](https://github.com/browser-use/browser-use) | MIT |
| [cachetools](https://github.com/tkem/cachetools) | MIT |
| [filelock](https://github.com/tox-dev/filelock) | Unlicense |
| [tenacity](https://github.com/jd/tenacity) | Apache-2.0 |
| [deprecation](https://github.com/briancurtin/deprecation) | Apache-2.0 |
| [python-frontmatter](https://github.com/eyesea/python-frontmatter) | MIT |
| [python-json-logger](https://github.com/madzak/python-json-logger) | MIT |
| [jieba](https://github.com/fxsjy/jieba) | MIT |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | MIT |

> 完整依赖列表见各子包 `pyproject.toml` 与根目录 `uv.lock`。
> 注意：Bashlex 采用 GPL-3.0-only，仅作为 zest-tools 的可选依赖用于 bash 命令解析，与 Zest-Agent 主体（Apache-2.0）独立分发。如对组合分发的合规性有顾虑，可移除 Bashlex 依赖。

### Frontend — Node

| 依赖 | License |
|---|---|
| [React](https://github.com/facebook/react) | MIT |
| [Vite](https://github.com/vitejs/vite) | MIT |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 |
| [Zustand](https://github.com/pmndrs/zustand) | MIT |
| [react-markdown](https://github.com/remarkjs/react-markdown) | MIT |
| [remark-gfm](https://github.com/remarkjs/remark-gfm) | MIT |

### Tooling

| 依赖 | License |
|---|---|
| [ruff](https://github.com/astral-sh/ruff) | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | MIT |
| [pre-commit](https://github.com/pre-commit/pre-commit) | MIT |

---

## License Summary

Zest-Agent 整体采用 **Apache License 2.0**。详见 [LICENSE](LICENSE)。Zest-Agent 的核心运行时（AgentRunner、调度、断点恢复、存储抽象、沙箱隔离、事件模型）均为自研设计。

衍生自 OpenHands（MIT License）的部分（部分工具实现与数据模型片段），其原始版权与许可声明按 MIT 要求保留在本 NOTICE 文件中。

Copyright 2026 CLFutureX

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

## Contribution Licensing

向 Zest-Agent 提交的贡献（包括但不限于代码、文档、配置）在合并到本仓库后，
将统一以 Apache License 2.0 对外发布，贡献者保留其原作者署名权。

按 Apache 2.0 第 5 条规定：除非明确声明 otherwise，任何有意提交以包含在本项目中的
Contribution 均按本 License 条款授权，不附加任何额外条款。

建议（非强制）在新源文件顶部加入 Apache 2.0 标准版权头：

```
Copyright 2026 CLFutureX

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
