#!/usr/bin/env python3
"""将全流程 Agent 输出渲染为最终交付报告。"""
import json
import sys
from datetime import datetime
from pathlib import Path


SCORE_COLOR = {
    (90, 100): "🟢",
    (75, 89): "🔵",
    (60, 74): "🟡",
    (40, 59): "🟠",
    (0, 39): "🔴"
}

def score_emoji(score: int) -> str:
    for (lo, hi), emoji in SCORE_COLOR.items():
        if lo <= score <= hi:
            return emoji
    return "⚪"


def render(review_path: str, arch_path: str, req_path: str,
           whitebox_path: str, blackbox_path: str,
           output_path: str):
    # 读取所有输入
    def load_json(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    review = load_json(review_path)
    arch = load_json(arch_path)
    req = load_json(req_path)

    whitebox = None
    if Path(whitebox_path).exists():
        whitebox = load_json(whitebox_path)

    blackbox = None
    if Path(blackbox_path).exists():
        blackbox = load_json(blackbox_path)

    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    project = review.get("project_name", req.get("project_name", "未命名项目"))
    total = review.get("total_score", 0)
    grade = review.get("grade", "N/A")
    scores = review.get("scores", {})

    # 渲染报告
    lines = []
    lines.append(f"# 项目交付报告：{project}")
    lines.append(f"")
    lines.append(f"**生成时间**：{date}")
    lines.append(f"**综合评分**：{score_emoji(total)} **{total}/100**（{grade}）")
    lines.append(f"**交付结论**：`{review.get('verdict', 'N/A')}`")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 执行摘要
    lines.append(f"## 执行摘要")
    lines.append(f"")
    lines.append(review.get("executive_summary", ""))
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 评分明细
    lines.append(f"## 评分明细")
    lines.append(f"")
    lines.append(f"| 维度 | 得分 | 满分 | 占比 | 评语 |")
    lines.append(f"|------|------|------|------|------|")
    for key, label in [
        ("requirement_fit", "需求匹配度"),
        ("architecture", "架构合理性"),
        ("code_quality", "代码质量"),
        ("test_coverage", "测试覆盖度"),
        ("maintainability", "可维护性"),
        ("security", "安全性"),
    ]:
        s = scores.get(key, {})
        sc = s.get("score", 0)
        mx = s.get("max", 0)
        pct = f"{sc/mx*100:.0f}%" if mx > 0 else "N/A"
        comment = s.get("comment", "")
        lines.append(f"| {label} | {sc} | {mx} | {pct} | {comment} |")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 雷达图（ASCII）
    dims = ["需求匹配", "架构", "代码质量", "测试覆盖", "可维护", "安全性"]
    lines.append(f"## 能力雷达图")
    lines.append(f"")
    for i, (key, label) in enumerate(zip(scores.keys(), dims)):
        s = scores.get(key, {})
        sc = s.get("score", 0)
        mx = s.get("max", 1)
        pct = sc / mx if mx > 0 else 0
        bar_len = int(pct * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"  {label:8s} [{bar}] {pct*100:.0f}%")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 测试总结
    lines.append(f"## 测试结果")
    lines.append(f"")

    if whitebox:
        wb_sum = whitebox.get("summary", {})
        lines.append(f"### 白盒测试")
        lines.append(f"- 审查文件：{wb_sum.get('total_files_reviewed', 0)} 个")
        lines.append(f"- 发现问题：{wb_sum.get('issues_found', 0)} 个（其中严重 {wb_sum.get('critical_issues', 0)} 个）")
        lines.append(f"- 代码质量评级：{whitebox.get('overall_code_quality', 'N/A')}")
        lines.append(f"")

    if blackbox:
        bb_sum = blackbox.get("summary", {})
        lines.append(f"### 黑盒测试")
        lines.append(f"- 测试用例：{bb_sum.get('total_test_cases', 0)} 个")
        lines.append(f"- 覆盖功能：{bb_sum.get('features_covered', 0)} 个")
        lines.append(f"- 覆盖接口：{bb_sum.get('apis_covered', 0)} 个")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # 阻塞项
    blockers = review.get("blockers", [])
    if blockers:
        lines.append(f"## 阻塞项")
        lines.append(f"")
        for b in blockers:
            lines.append(f"- **[{b.get('severity', '')}]** {b.get('issue', '')}")
            lines.append(f"  - 来源：{b.get('source', '')}")
            lines.append(f"  - 解决：{b.get('resolution', '')}")
        lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 优势 / 劣势
    lines.append(f"## 优势与不足")
    lines.append(f"")
    lines.append(f"### 优势")
    for s in review.get("strengths", []):
        lines.append(f"- {s}")
    lines.append(f"")
    lines.append(f"### 不足")
    for w in review.get("weaknesses", []):
        lines.append(f"- {w}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 改进路线图
    roadmap = review.get("improvement_roadmap", [])
    if roadmap:
        lines.append(f"## 改进路线图")
        lines.append(f"")
        for r in roadmap:
            lines.append(f"- **{r.get('priority', '')}**：{r.get('action', '')} → {r.get('expected_gain', '')}")
        lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 技术栈总览
    lines.append(f"## 技术栈")
    stack = arch.get("tech_stack", {})
    backend = stack.get("backend", {})
    frontend = stack.get("frontend", {})
    devops = stack.get("devops", {})
    lines.append(f"")
    lines.append(f"| 层次 | 技术选型 |")
    lines.append(f"|------|----------|")
    for k, v in backend.items():
        if v:
            lines.append(f"| 后端-{k} | {v} |")
    for k, v in frontend.items():
        if v:
            lines.append(f"| 前端-{k} | {v} |")
    for k, v in devops.items():
        if v:
            lines.append(f"| DevOps-{k} | {v} |")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*报告由 dev-workflow skill v0.1.0 自动生成*")
    lines.append(f"*{date}*")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"报告已生成: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("用法: python render_dev_report.py <review.json> <architecture.json> <requirements.json> <whitebox.json> <blackbox.json> <output.md>")
        sys.exit(1)
    render(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
