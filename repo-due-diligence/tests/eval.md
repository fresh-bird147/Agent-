# 评估数据集

用于评估 repo-due-diligence skill 的输出质量。

## 评估维度

1. **完整性**: 五个风险类别是否都覆盖？
2. **准确性**: 每个结论是否有上游 agent 数据支撑？
3. **可用性**: 最终"推荐 / 不推荐"结论是否合理？
4. **一致性**: 同样的仓库跑两次，结论是否一致？

## 测试用例

### 1. 活跃大项目：React
- URL: https://github.com/facebook/react
- 期望结论: 强烈推荐
- 原因: star 极高、社区极度活跃、维护规范、有 Meta 背书

### 2. 个人小工具：一个只有 50 star 的 CLI 工具
- URL: https://github.com/example/small-cli
- 期望结论: 谨慎 / 不推荐
- 原因: bus factor = 1、commit 频率低、无测试

### 3. 归档项目
- URL: https://github.com/example/archived-project
- 期望结论: 不推荐
- 原因: 已归档、无维护

### 4. 中档项目：有潜力但社区小
- URL: https://github.com/example/mid-project
- 期望结论: 推荐
- 原因: 代码质量高、有活跃维护但社区偏小

### 5. License 有问题
- URL: https://github.com/example/agpl-project
- 期望结论: 谨慎
- 原因: AGPL License 对企业不友好

## 评估方法

每次改完 SKILL.md 或 sub-agent prompt 后，跑这 5 个仓库，检查：
- 结论是否与预期一致
- 若不一致，追溯到是哪个 agent 的输出出了问题
- 调整对应 agent 的 prompt
