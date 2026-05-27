# 技术尽调报告：{repo_name}

**评估日期**：{date}
**结论**：{recommendation}

---

## 一句话总结

{recommendation_reason}

---

## 一、项目概述

{recon.summary}

### 基本信息

| 指标 | 值 |
|------|-----|
| 安装复杂度 | {recon.setup_complexity} |
| 第一印象 | {recon.first_impression} |
| License | {license_type} |

### 值得关注的 Issues

{recon.notable_issues}

---

## 二、使用指南

### 前置依赖

{usage.prerequisites}

### 安装步骤

{usage.installation_steps}

#### 快速安装（一行命令）

```
{usage.one_liner}
```

### 快速开始

**配置文件**：`{usage.config_file}`

```
{usage.config_content}
```

**环境变量**：

{usage.env_vars}

**启动命令**：

```
{usage.start_command}
```

访问地址：`{usage.default_port}`

### 常用命令

{usage.common_commands}

### 使用场景

{usage.usage_scenarios}

### 关键配置

{usage.configuration_reference}

### 支持平台

{usage.platforms}

### 使用提示

{usage.tips}

---

## 三、代码质量评估

### 综合评分

| 维度 | 分数 |
|------|------|
| 架构清晰度 | {code_review.overall_scores.architecture}/5 |
| 命名质量 | {code_review.overall_scores.naming}/5 |
| 测试覆盖 | {code_review.overall_scores.testing}/5 |
| 文档完整性 | {code_review.overall_scores.documentation}/5 |
| 复杂度控制 | {code_review.overall_scores.complexity}/5 |

### 关键风险

{code_review.key_risks}

### 关键亮点

{code_review.key_strengths}

---

## 四、社区健康度

| 指标 | 数据 |
|------|------|
| 近 3 个月 commits | {health.metrics.commits_last_3m} |
| 近 6 个月 commits | {health.metrics.commits_last_6m} |
| PR 合并中位数 | {health.metrics.pr_merge_median_hours} 小时 |
| Issue 响应中位数 | {health.metrics.issue_response_median_hours} 小时 |
| 近 6 月 star 增长 | {health.metrics.star_growth_6m_pct}% |
| 近 12 月 star 增长 | {health.metrics.star_growth_12m_pct}% |
| 总贡献者 | {health.metrics.total_contributors} |
| 核心贡献者 | {health.metrics.core_contributors} |
| Bus Factor | {health.metrics.bus_factor} |
| 最近 Release | {health.metrics.last_release_date} |
| Release 频率 | {health.metrics.release_frequency} |

**活跃趋势**：{health.activity_trend}
**社区健康度**：{health.community_health}

### 风险标记

{health.risk_flags}

---

## 五、风险评估

### 风险总览

| 类别 | 等级 |
|------|------|
| 技术债 | {risk.tech_debt.level} |
| 维护 | {risk.maintenance.level} |
| 社区 | {risk.community.level} |
| License | {risk.license.level} |
| 安全 | {risk.security.level} |

### 详细分析

#### 技术债风险
- **等级**：{risk.tech_debt.level}
- **详情**：{risk.tech_debt.detail}
- **缓解措施**：{risk.tech_debt.mitigation}

#### 维护风险
- **等级**：{risk.maintenance.level}
- **详情**：{risk.maintenance.detail}
- **缓解措施**：{risk.maintenance.mitigation}

#### 社区风险
- **等级**：{risk.community.level}
- **详情**：{risk.community.detail}
- **缓解措施**：{risk.community.mitigation}

#### License 风险
- **等级**：{risk.license.level}
- **详情**：{risk.license.detail}
- **缓解措施**：{risk.license.mitigation}

#### 安全风险
- **等级**：{risk.security.level}
- **详情**：{risk.security.detail}
- **缓解措施**：{risk.security.mitigation}

---

## 六、最终结论

### 推荐等级：{recommendation}

{recommendation_reason}

### 适用场景

| 场景 | 是否推荐 |
|------|----------|
| 生产关键系统 | {risk.use_cases.production_critical} |
| 个人项目 | {risk.use_cases.side_project} |
| 学习参考 | {risk.use_cases.learning_reference} |

### 替代方案

{risk.alternatives}

### 综合评估

{risk.overall_assessment}

---

*报告由 repo-due-diligence skill v0.4.0 自动生成*
*{date}*
