---
name: dev-workflow
version: "0.1.0"
description: |
  完整的软件开发流水线：从需求文档拆解 → 技术架构设计 → 代码生成 → 黑白盒测试 → 项目评分总结。
  用户提供需求文档（.md / .txt / .docx），系统自动完成全流程。
  Triggers: "开发这个需求"、"从这个需求文档生成代码"、"全流程开发"、"build this spec"
allowed-tools: Bash, Read, Write, agent_spawn, rlm_query
---

# dev-workflow

从一份需求文档到交付项目，完整的五阶段 Agent 编排。

## 技术栈约束

本项目默认技术栈为 **Java + Vue**，所有 Agent 必须遵循以下约定：

| 层次 | 技术 | 版本 |
|------|------|------|
| 后端语言 | Java | 8+ |
| 后端框架 | SpringBoot | 2.7+ |
| ORM | MyBatis / MyBatis-Plus | 3.x |
| 缓存 | Redis | 6+ |
| 数据库 | MySQL | 8.0 |
| 安全框架 | Spring Security | 5.x |
| 前端框架 | Vue | 3.x |
| UI 库 | Element Plus | 2.x |
| 构建工具 | Maven | 3.6+ |
| 测试框架 | JUnit 5 | 5.x |
| 部署 | Docker + Docker Compose | — |

> 仅当需求文档明确指定其他技术栈时，Architecture Agent 才可变更选型。

## 编排流程

### 阶段 1：需求拆解（串行入口）

spawn:

1. **Requirement Agent**
   - 输入：用户提供的需求文档路径
   - 任务：阅读需求书，拆解为独立功能点，标注优先级和依赖关系
   - 输出：结构化的功能点清单（JSON）
   - 模型：DeepSeek V4 Pro（需要准确理解需求）
   - prompt: references/requirement-prompt.md

**阶段 1 产出文件**：`output/1-requirements.json`

### 阶段 2：架构设计（串行，依赖阶段 1）

阶段 1 完成后，spawn:

2. **Architecture Agent**
   - 输入：`output/1-requirements.json`
   - 任务：根据功能点设计技术架构（技术选型、模块划分、数据流、API 设计）
   - 输出：架构设计文档（JSON + Markdown）
   - 模型：DeepSeek V4 Pro（架构设计需要强推理）
   - prompt: references/architecture-prompt.md

**阶段 2 产出文件**：`output/2-architecture.json`、`output/2-architecture.md`

### 阶段 3：代码生成（并行 fan-out）

阶段 2 完成后，**按模块并行** spawn 多个 Coding Agent（RLM Batch）：

3. **Coding Agent × N**
   - 输入：架构设计中每个模块的定义
   - 任务：为各自模块生成完整可运行代码（含注释、单测框架）
   - 输出：每个模块的代码文件 + 模块级单测
   - 模型：每个模块任务用 V4 Flash，代码审查自己的输出用 V4 Pro 自检
   - prompt: references/coding-prompt.md

**阶段 3 产出目录**：`output/3-code/`

### 阶段 4：测试（并行）

阶段 3 完成后，spawn 两个测试 Agent（一个做白盒，一个做黑盒）：

4a. **White-Box Testing Agent**
   - 输入：所有生成的源码文件
   - 任务：静态分析、代码审查、逻辑覆盖测试、边界值测试
   - 输出：白盒测试报告
   - 模型：V4 Pro（需要深入理解代码逻辑）
   - prompt: references/testing-prompt.md (white-box 部分)

4b. **Black-Box Testing Agent**
   - 输入：架构设计文档 + 需求文档
   - 任务：功能测试、集成测试、边界测试、用户场景测试
   - 输出：黑盒测试报告 + 测试用例清单
   - 模型：V4 Flash（关注输入输出，不需要深入代码）
   - prompt: references/testing-prompt.md (black-box 部分)

**阶段 4 产出文件**：`output/4-whitebox-report.json`、`output/4-blackbox-report.json`

### 阶段 5：项目评分总结（串行，依赖阶段 1-4）

所有上游完成后，spawn:

5. **Review Agent**
   - 输入：需求 + 架构 + 代码 + 两份测试报告
   - 任务：综合评分（需求匹配度、架构合理性、代码质量、测试覆盖、可维护性）
   - 输出：项目评分报告 + 改进建议
   - 模型：DeepSeek V4 Pro（综合判断需要强推理）
   - prompt: references/review-prompt.md

**阶段 5 产出文件**：`output/5-review-report.md`

### 阶段 6：渲染（脚本）

跑 `python scripts/render_dev_report.py` 把阶段 5 的输出渲染成最终交付文档。

**最终产出**：`output/FINAL-{project}-{date}.md`

## 严格约束

- 必须按阶段顺序执行，不能跳过
- 阶段 3 代码生成必须按模块并行（RLM batch）
- 阶段 4 白盒+黑盒必须并行
- 每个 Agent 的产出必须是严格 JSON 格式
- 最终报告里每个评分必须可追溯到上游 agent 输出
