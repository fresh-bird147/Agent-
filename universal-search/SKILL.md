---
name: universal-search
version: "0.2.0"
description: |
  万能搜索引擎工作流：根据用户输入的查询字段自动上网搜索，并行分拣过滤高价值信息，
  整理为结构化 Markdown 文档，并生成总结摘要。
  Triggers: "搜索一下"、"帮我查查"、"调研"、"找资料"、"search for"、"look up"
allowed-tools: Bash, Read, Write, webfetch, agent_spawn
---

# universal-search

根据用户输入的查询主题，自动完成搜索 → 并行分拣 → 综合筛选 → 整理 → 总结的全流程。

## 编排流程

### 阶段 1：信息搜索（串行入口）

spawn:

1. **Search Agent**
   - 输入：用户提供的查询字段 / 关键词
   - 任务：提取查询特征（关键词、领域、时效性要求），多源搜索（搜索
     引擎、专业站点、文档库），收集相关信息的标题、摘要和 URL
   - 输出：多条原始搜索结果（JSON 数组），含标题、摘要、URL、来源类型
   - 模型：V4 Flash（网页抓取 + 结构化提取，弱模型够）
   - prompt: references/search-prompt.md

**阶段 1 产出文件**：`output/1-search-results.json`

### 阶段 2：并行分拣打分（并行 fan-out，依赖阶段 1）

阶段 1 完成后，将搜索结果按最大 10 个并行 Agent 分组分发：

2. **Parallel Scorer Agent × N**（最多 10 个，fan-out 并行）
   - 输入：各自分配到的 1-2 条搜索结果
   - 任务：逐条评估信息与查询意图的匹配度，按四维打分（相关性/权威性/
     时效性/信息密度），判断是否与查询相关。**若发现信息与查询内容无
     关，有权直接丢弃该条并跳过**，仅保留相关信息的评分
   - 输出：各自打分结果 JSON（含保留/丢弃判定）
   - 模型：V4 Flash（逐条打分，弱模型够，并行最大效率）
   - prompt: references/parallel-scorer-prompt.md

**阶段 2 产出文件**：`output/2-scorer-outputs/` 目录下每个 Agent 一份 JSON

### 阶段 3：综合判断排序（串行，依赖阶段 2）

阶段 2 全部完成后，spawn:

3. **Judgment Agent**
   - 输入：所有 Parallel Scorer Agent 的打分输出 + 原始查询意图
   - 任务：收集所有并行打分结果，去重合并，检查评分一致性，按综合
     权重全局排序，过滤残留低价值条目，输出最终筛选列表
   - 输出：全局筛选后的结果列表 + 权重排序 + 筛选总结
   - 模型：V4 Pro（全局判断去重和一致性需要较强推理）
   - prompt: references/judgment-prompt.md

**阶段 3 产出文件**：`output/3-filtered-results.json`

### 阶段 4：文档化整理（串行，依赖阶段 3）

阶段 3 完成后，spawn:

4. **Documentation Agent**
   - 输入：`output/3-filtered-results.json`
   - 任务：将筛选后的信息按相似度权重排序，组织为结构化
     Markdown 文档，必须包含关键词、源地址和权重说明
   - 输出：信息整理文档（Markdown）
   - 模型：V4 Flash（格式化和拼接，弱模型够）
   - prompt: references/doc-prompt.md

**阶段 4 产出文件**：`output/4-research-doc.md`

### 阶段 5：总结（串行，依赖阶段 4）

阶段 4 完成后，spawn:

5. **Summary Agent**
   - 输入：`output/4-research-doc.md`
   - 任务：基于整理文档写一份 ≤500 字的执行摘要，提炼核心结论、
     关键发现和行动建议
   - 输出：总结摘要
   - 模型：V4 Pro（综合判断需要较强推理）
   - prompt: references/summary-prompt.md

**阶段 5 产出文件**：`output/5-summary.json`

### 阶段 6：渲染（脚本）

跑 `python scripts/render_search_report.py` 把阶段 4+5 的输出合并渲染为
最终交付文档。

**最终产出**：`output/FINAL-search-{topic}-{date}.md`

## 并行分拣策略

- **分组规则**：N 条搜索结果 → ceil(N/2) 个并行 Agent，每组 ≤2 条，最多 10 个 Agent
- **独立判断**：每个 Scorer Agent 独立打分，不依赖其他 Agent 的结果
- **有权丢弃**：Scorer 发现某条信息与查询完全无关时，直接标记为 `discard`，
  不传递到下一阶段
- **去重合并**：Judgment Agent 收集所有得分后，检查重复（同 URL 或高度相似
  内容），保留得分最高者

## 严格约束

- 必须按阶段顺序执行，不能跳过
- Search Agent 必须提取真实字段特征再去搜索，不能无特征泛搜
- 阶段 2 并行 Scorer 必须同时 fan-out，不能串行
- 每个 Scorer Agent 必须有丢弃无关节目的权利
- Judgment Agent 必须检查所有 Scorer 输出的评分一致性
- Documentation Agent 必须包含关键词和源地址，不能遗漏
- Summary Agent 的结论必须可追溯到阶段 4 的具体条目
