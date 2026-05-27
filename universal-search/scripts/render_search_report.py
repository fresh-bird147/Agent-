#!/usr/bin/env python3
"""将搜索流程的 Agent 输出渲染为最终交付报告。"""
import json
import sys
from datetime import datetime
from pathlib import Path


def safe_load(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def render_search_report(
    filtered_path: str,
    doc_path: str,
    summary_path: str,
    template_path: str,
    output_path: str,
):
    filtered = safe_load(filtered_path)
    summary = safe_load(summary_path)

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    with open(doc_path, "r", encoding="utf-8") as f:
        research_content = f.read()

    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    query = filtered.get("query", summary.get("query", "Unknown"))

    report = template
    report = report.replace("{query}", query)
    report = report.replace("{date}", date)

    keywords = ", ".join(
        filtered.get("results", [{}])[0].get("extracted_features", {}).get("keywords", [])
    ) if filtered.get("results") else ""
    if not keywords:
        keywords = summary.get("query", "")
    report = report.replace("{keywords}", keywords)

    # 执行摘要
    report = report.replace("{executive_summary}", summary.get("executive_summary", "无"))

    # 关键发现
    findings = summary.get("key_findings", [])
    findings_md = ""
    for i, f in enumerate(findings):
        findings_md += f"- **[{f.get('confidence', 'N/A')}]** {f.get('finding', '')}"
        if f.get("source_id"):
            findings_md += f" (来源 #{f['source_id']})"
        findings_md += "\n"
    report = report.replace("{key_findings}", findings_md if findings_md else "无")

    # 趋势分析
    report = report.replace("{trend_analysis}", summary.get("trend_analysis", "无"))

    # 知识盲区
    gaps = summary.get("knowledge_gaps", [])
    gaps_md = "\n".join([f"- {g}" for g in gaps]) if gaps else "无"
    report = report.replace("{knowledge_gaps}", gaps_md)

    # 行动建议
    actions = summary.get("action_items", [])
    actions_md = ""
    for a in actions:
        actions_md += f"- **[{a.get('priority', 'N/A')}]** {a.get('action', '')}\n"
    report = report.replace("{action_items}", actions_md if actions_md else "无")

    # 调研详情
    report = report.replace("{research_content}", research_content)

    # 信息来源
    results = filtered.get("results", [])
    source_list = ""
    for r in results:
        title = r.get("title", "N/A")
        url = r.get("url", "#")
        weight = r.get("weight", 0)
        source_list += f"- [{title}]({url}) (权重: {weight:.2f})\n"
    report = report.replace("{source_list}", source_list if source_list else "无")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已生成: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(
            "用法: python render_search_report.py <filtered.json> <doc.md> "
            "<summary.json> <template.md> <output.md>"
        )
        sys.exit(1)

    render_search_report(
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    )
