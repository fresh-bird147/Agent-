---
name: repo-due-diligence
version: "0.5.0"
description: |
  Generate a technical due-diligence report for a GitHub repository.
  Use this skill whenever the user asks to: 评估这个仓库、做技术尽调、看看这个开源项目
  值不值得用、analyze this repo、due diligence on github.com/...、给我一份评估报告.
  Triggers when the user pastes a GitHub URL with words like "评估"/"尽调"/"评测"/
  "review"/"analyze". Do NOT trigger for code generation tasks or PR reviews.
allowed-tools: Bash, Read, Write, fetch_webpage, github_repo, rlm_query, agent_spawn
---

# repo-due-diligence

针对一个 GitHub 仓库，生成可决策的技术尽调报告。

## 编排流程

### 阶段 1：信息采集（并行）

并行 spawn 四个 sub-agent：

1. **Recon Agent**
   - 输入：仓库 URL
   - 任务：读 README、最近 20 个 open issues、最近 20 个 closed issues
   - 输出：一段 ≤ 500 字的「项目意图与现状」摘要 + 3-5 条值得关注的 issue
   - 模型：DeepSeek V4 Flash（足够）
   - prompt: references/recon-prompt.md

2. **Code Review Agent**
   - 输入：仓库 URL
   - 任务：用 `scripts/pick_core_files.py` 挑出 10 个核心文件，
     **每个文件 fan-out 一个 RLM child** 独立 review
   - 输出：一份「代码质量报告」，含 5 项打分（架构 / 命名 / 测试 / 文档 / 复杂度）+ 风险点
   - 模型：Code Review Agent 本身用 V4 Pro，每个 child 用 V4 Flash
   - prompt: references/code-review-prompt.md

3. **Health Metrics Agent**
   - 输入：仓库 URL
   - 任务：跑 `scripts/github_meta.py` 拿元数据，分析活跃度趋势
   - 输出：「健康度报告」，含 commit 频率、PR 周转中位数、issue 响应中位数、
     近 6 个月 star 增长率、bus factor 估算
   - 模型：V4 Flash（纯结构化分析，弱模型够）
   - prompt: references/health-prompt.md

4. **Usage Guide Agent**
   - 输入：仓库 URL + Recon Agent 的 README 分析结果
   - 任务：提取安装步骤、使用教程、常用场景、配置说明
   - 输出：「使用指南」，含安装命令、快速开始步骤、常用命令、配置模板
   - 模型：V4 Flash（从 README 提取结构化信息，弱模型够）
   - prompt: references/usage-guide-prompt.md

### 阶段 2：综合判断（串行）

阶段 1 全部完成后，spawn:

5. **Risk Analyst Agent**
   - 输入：上面四个 agent 的结构化输出
   - 任务：识别 5 大类风险（技术债 / 维护风险 / 社区风险 / license / security）
   - 输出：「风险评估报告」+ 一句话「是否推荐引入」结论
   - 模型：DeepSeek V4 Pro（综合判断需要强推理）
   - prompt: references/risk-prompt.md

### 阶段 3：渲染（脚本）

跑 `python scripts/render_report.py` 把上面五个 agent 的结构化输出
渲染成 references/report-template.md 模板的 markdown 报告。

输出到 `./due-diligence-{repo}-{date}.md`。

## 严格约束

- 必须按阶段执行，不能跳过任何 sub-agent
- Code Review Agent 必须使用 RLM batch，不能串行
- Usage Guide Agent 必须从 README/docs 提取实际内容，不能编造
- Risk Analyst 输出的「是否推荐引入」必须是 强烈推荐 / 推荐 / 谨慎 / 不推荐 之一
- 最终报告里每个数字都必须可追溯到上游 agent 的输出
