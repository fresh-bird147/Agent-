#!/usr/bin/env python3
"""将五个 agent 的结构化 JSON 渲染成 markdown 报告。"""
import json
import sys
from datetime import datetime
from pathlib import Path


def safe_load(path: str) -> dict:
    """安全加载 JSON，路径不存在时返回空字典。"""
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def render_report(recon_path: str, code_review_path: str, health_path: str,
                  risk_path: str, template_path: str, output_path: str,
                  usage_guide_path: str = ""):
    recon = safe_load(recon_path)
    code_review = safe_load(code_review_path)
    health = safe_load(health_path)
    risk = safe_load(risk_path)
    usage = safe_load(usage_guide_path) if usage_guide_path else {}

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    date = datetime.now().strftime("%Y-%m-%d")
    repo_name = recon.get("repo_name", "Unknown")

    report = template
    report = report.replace("{repo_name}", repo_name)
    report = report.replace("{date}", date)
    report = report.replace("{recommendation}", "**" + risk.get("recommendation", "N/A") + "**")
    report = report.replace("{recommendation_reason}", risk.get("recommendation_reason", ""))

    # 项目概述
    report = report.replace("{recon.summary}", recon.get("summary", ""))
    report = report.replace("{recon.setup_complexity}", recon.get("setup_complexity", "N/A"))
    report = report.replace("{recon.first_impression}", recon.get("first_impression", ""))
    report = report.replace("{license_type}", risk.get("risks", {}).get("license", {}).get("detail", "Unknown"))

    # Notable issues
    issues = recon.get("notable_issues", [])
    issues_md = ""
    for issue in issues:
        issues_md += f"- **{issue.get('title', '')}** (#{issue.get('id', '')}) [{issue.get('importance', '')}]\n"
        issues_md += f"  {issue.get('reason', '')}\n"
    report = report.replace("{recon.notable_issues}", issues_md if issues_md else "无")

    # ============ 使用指南 (NEW) ============
    # 前置依赖
    prereqs = usage.get("prerequisites", [])
    prereq_md = ""
    for p in prereqs:
        prereq_md += f"- **{p.get('name', '')}** — 检查：`{p.get('how_to_check', '')}`\n"
    report = report.replace("{usage.prerequisites}", prereq_md if prereq_md else "无")

    # 安装步骤
    install = usage.get("installation", {})
    steps = install.get("steps", [])
    steps_md = ""
    for s in steps:
        steps_md += f"**{s.get('step', '')}.** {s.get('description', '')}\n```bash\n{s.get('command', '')}\n```\n"
    report = report.replace("{usage.installation_steps}", steps_md if steps_md else "详见仓库 README")

    report = report.replace("{usage.one_liner}", install.get("one_liner", "详见仓库 README"))

    # 快速开始
    qs = usage.get("quick_start", {})
    report = report.replace("{usage.config_file}", qs.get("config_file", "详见仓库配置文档"))
    report = report.replace("{usage.config_content}", qs.get("config_content", "详见仓库配置文档"))
    envs = qs.get("env_vars", [])
    envs_md = ""
    for e in envs:
        required = "（必填）" if e.get("required") else "（可选）"
        envs_md += f"- `{e.get('name', '')}={e.get('example', '')}` {required} — {e.get('description', '')}\n"
    report = report.replace("{usage.env_vars}", envs_md if envs_md else "无")
    report = report.replace("{usage.start_command}", qs.get("start_command", "详见仓库 README"))
    report = report.replace("{usage.default_port}", qs.get("default_port", "N/A"))

    # 常用命令
    cmds = usage.get("common_commands", [])
    cmds_md = ""
    for c in cmds:
        cmds_md += f"**{c.get('command', '')}** — {c.get('description', '')}\n"
        flags = c.get("flags", [])
        if flags:
            cmds_md += "\n| 参数 | 类型 | 必填 | 说明 |\n|------|------|------|------|\n"
            for fl in flags:
                cmds_md += f"| `{fl.get('flag', '')}` | {fl.get('type', '')} | {'是' if fl.get('required') else '否'} | {fl.get('description', '')} |\n"
            cmds_md += "\n"
    report = report.replace("{usage.common_commands}", cmds_md if cmds_md else "无")

    # 使用场景
    scenarios = usage.get("usage_scenarios", [])
    scen_md = ""
    for s in scenarios:
        scen_md += f"**{s.get('name', '')}**\n- 场景：{s.get('description', '')}\n- 示例：`{s.get('example', '')}`\n\n"
    report = report.replace("{usage.usage_scenarios}", scen_md if scen_md else "无")

    # 关键配置
    cfg_ref = usage.get("configuration_reference", {})
    key_cfgs = cfg_ref.get("key_settings", [])
    cfg_md = ""
    for k in key_cfgs:
        cfg_md += f"- `{k.get('key', '')}`（默认：`{k.get('default', '')}`）— {k.get('description', '')}\n"
    report = report.replace("{usage.configuration_reference}", cfg_md if cfg_md else "无")

    # 支持平台
    platforms = usage.get("platforms", [])
    report = report.replace("{usage.platforms}", ", ".join(platforms) if platforms else "未明确说明")

    # 使用提示
    tips = usage.get("tips", [])
    tips_md = ""
    for t in tips:
        tips_md += f"- {t}\n"
    report = report.replace("{usage.tips}", tips_md if tips_md else "无")

    # 代码质量
    scores = code_review.get("overall_scores", {})
    report = report.replace("{code_review.overall_scores.architecture}", str(scores.get("architecture", "N/A")))
    report = report.replace("{code_review.overall_scores.naming}", str(scores.get("naming", "N/A")))
    report = report.replace("{code_review.overall_scores.testing}", str(scores.get("testing", "N/A")))
    report = report.replace("{code_review.overall_scores.documentation}", str(scores.get("documentation", "N/A")))
    report = report.replace("{code_review.overall_scores.complexity}", str(scores.get("complexity", "N/A")))

    # Code review risks
    cr_risks = code_review.get("key_risks", [])
    risks_md = ""
    for r in cr_risks:
        risks_md += f"- {r}\n"
    report = report.replace("{code_review.key_risks}", risks_md if risks_md else "无")

    # Code review strengths
    strengths = code_review.get("key_strengths", [])
    strengths_md = ""
    for s in strengths:
        strengths_md += f"- {s}\n"
    report = report.replace("{code_review.key_strengths}", strengths_md if strengths_md else "无")

    # 健康度指标
    metrics = health.get("metrics", {})
    for key in ["commits_last_3m", "commits_last_6m", "pr_merge_median_hours",
                 "issue_response_median_hours", "star_growth_6m_pct", "star_growth_12m_pct",
                 "total_contributors", "core_contributors", "bus_factor"]:
        report = report.replace(f"{{health.metrics.{key}}}", str(metrics.get(key, "N/A")))
    report = report.replace("{health.metrics.last_release_date}", metrics.get("last_release_date", "N/A"))
    report = report.replace("{health.metrics.release_frequency}", metrics.get("release_frequency", "N/A"))
    report = report.replace("{health.activity_trend}", health.get("activity_trend", "N/A"))
    report = report.replace("{health.community_health}", health.get("community_health", "N/A"))

    # Health risk flags
    health_flags = health.get("risk_flags", [])
    flags_md = ""
    for fl in health_flags:
        flags_md += f"- **{fl.get('type', '')}** [{fl.get('severity', '')}]: {fl.get('detail', '')}\n"
    report = report.replace("{health.risk_flags}", flags_md if flags_md else "无")

    # 风险详情
    risk_data = risk.get("risks", {})
    for category in ["tech_debt", "maintenance", "community", "license", "security"]:
        r = risk_data.get(category, {})
        report = report.replace(f"{{risk.{category}.level}}", r.get("level", "N/A"))
        report = report.replace(f"{{risk.{category}.detail}}", r.get("detail", ""))
        report = report.replace(f"{{risk.{category}.mitigation}}", r.get("mitigation", ""))

    # Use cases
    use_cases = risk.get("use_cases", {})
    for key in ["production_critical", "side_project", "learning_reference"]:
        report = report.replace(f"{{risk.use_cases.{key}}}", use_cases.get(key, "N/A"))

    # Alternatives
    alts = risk.get("alternatives", [])
    alts_md = ""
    for a in alts:
        alts_md += f"- **{a.get('name', '')}**: {a.get('reason', '')}\n"
    report = report.replace("{risk.alternatives}", alts_md if alts_md else "无")

    # Overall assessment
    report = report.replace("{risk.overall_assessment}", risk.get("overall_assessment", ""))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已生成: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("用法: python render_report.py <recon.json> <code_review.json> <health.json> <risk.json> <template.md> <output.md> [usage_guide.json]")
        sys.exit(1)

    usage_guide = sys.argv[7] if len(sys.argv) > 7 else ""
    render_report(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], usage_guide)
