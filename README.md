# Agent Workflows

基于 Agent 编排的多智能体开发工作流集合。

## 工作流列表

### 1. repo-due-diligence（仓库技术尽调）

对 GitHub 仓库执行全方位技术评估：

```
5 个 Agent 并行协作 → 生成可决策的尽调报告
```

| Agent | 职责 |
|-------|------|
| Recon Agent | 项目侦查（README、Issues分析） |
| Code Review Agent | 代码审查（5维打分 + RLM Batch并行） |
| Health Metrics Agent | 社区健康度分析 |
| Usage Guide Agent | 提取安装和使用步骤 |
| Risk Analyst Agent | 5类风险综合判断 + 推荐结论 |

**输出**：6 章节 Markdown 报告（项目概述 → 使用指南 → 代码质量 → 社区健康度 → 风险评估 → 最终结论）

### 2. dev-workflow（全栈开发流水线）

从需求文档到交付项目，Java + Vue 全栈开发：

```
6 个 Agent 串并行 → 需求拆解 → 架构设计 → 代码生成 → 黑白盒测试 → 项目评分
```

| 阶段 | Agent | 产出 |
|------|-------|------|
| 1 | Requirement Agent | 功能点清单 + 依赖图 |
| 2 | Architecture Agent | 技术架构 + API设计 + DB模型 |
| 3 | Coding Agent ×N | Java/SpringBoot 完整代码（并行） |
| 4 | White-Box + Black-Box | 静态分析 + 功能/安全测试 |
| 5 | Review Agent | 6维评分（100分制）+ 改进路线图 |

**技术栈**：Java 8 + SpringBoot 2.7 + MyBatis-Plus + MySQL 8.0 + Redis + Vue 3 + Element Plus

### 3. universal-search（万能搜索引擎）

输入关键词 → 全网搜索 → 价值筛选 → 结构化整理 → 执行摘要：

```
5 个 Agent 串行 → 搜索 → 筛选 → 整理 → 总结 → 渲染报告
```

| 阶段 | Agent | 产出 |
|------|-------|------|
| 1 | Search Agent | 特征提取 + 多源搜索结果 |
| 2 | Judgment Agent | 4维打分筛选（相关性/权威性/时效性/信息密度）|
| 3 | Documentation Agent | 结构化 Markdown（含关键词、源地址、权重排序）|
| 4 | Summary Agent | ≤500字执行摘要 + 趋势 + 行动建议 |
| 5 | render_search_report.py | 最终研究报告 |

**输出**：完整调研报告（执行摘要 → 调研详情 → 信息来源清单）

## 目录结构

```
.
├── repo-due-diligence/
│   ├── SKILL.md                    # Orchestrator 编排脚本
│   ├── references/                 # 5 个 Agent 系统提示
│   ├── scripts/                    # 3 个辅助脚本
│   └── tests/                      # 评估用例
├── dev-workflow/
│   ├── SKILL.md                    # Orchestrator 编排脚本
│   ├── references/                 # 6 个 Agent 系统提示 + 模板
│   ├── scripts/                    # 3 个辅助脚本
│   └── tests/                      # 评估用例
├── universal-search/
│   ├── SKILL.md                    # Orchestrator 编排脚本
│   ├── references/                 # 4 个 Agent 系统提示 + 模板
│   ├── scripts/                    # 渲染脚本
│   └── tests/                      # 评估用例
└── README.md
```

## 设计原则

- **Agent 各司其职**：每个 Agent 职责边界清晰，输入输出结构化
- **能并行的并行**：Phase 1 的 4 个 Agent 全部并行，Coding Agent 按模块 RLM Batch fan-out
- **确定性逻辑交给脚本**：不在 LLM 里拼字符串、不做纯规则判断
- **小上下文 = 好表现**：每个 Agent 只拿自己需要的信息，不传递原始垃圾数据
- **输出可追溯**：报告里每个数字都标出来源 Agent
