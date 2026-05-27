#!/usr/bin/env python3
"""从 GitHub API 获取仓库元数据，输出结构化 JSON。"""
import json
import sys
import urllib.request
import os
import re


def github_api(url: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "repo-due-diligence/0.4.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def parse_repo_url(url: str) -> tuple:
    m = re.search(r"github\.com/([^/]+)/([^/\s#]+)", url)
    if not m:
        print(json.dumps({"error": "无法解析 GitHub URL"}))
        sys.exit(1)
    return m.group(1).rstrip(".git"), m.group(2).rstrip(".git")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "需要 GitHub URL 参数"}))
        sys.exit(1)

    owner, repo = parse_repo_url(sys.argv[1])
    base = f"https://api.github.com/repos/{owner}/{repo}"

    # 1. 仓库基本信息
    repo_data = github_api(base)
    if "error" in repo_data:
        print(json.dumps(repo_data))
        sys.exit(1)

    # 2. 最近 100 条 commits
    commits_data = github_api(f"{base}/commits?per_page=100")

    # 3. 最近 release
    releases_data = github_api(f"{base}/releases?per_page=10")

    # 4. Issues 统计
    issues_data = github_api(f"{base}/issues?state=all&per_page=100")

    # 5. Contributors
    contributors_data = github_api(f"{base}/contributors?per_page=30")

    # 6. 获取最近 6 个月的 star 趋势（简化版，用 stargazers 总数近似）
    # 实际项目应使用 star-history API

    output = {
        "repo": f"{owner}/{repo}",
        "full_name": repo_data.get("full_name", ""),
        "description": repo_data.get("description", ""),
        "language": repo_data.get("language", ""),
        "license": repo_data.get("license", {}).get("spdx_id", "Unknown") if repo_data.get("license") else "Unknown",
        "stars": repo_data.get("stargazers_count", 0),
        "forks": repo_data.get("forks_count", 0),
        "open_issues": repo_data.get("open_issues_count", 0),
        "watchers": repo_data.get("watchers_count", 0),
        "created_at": repo_data.get("created_at", ""),
        "updated_at": repo_data.get("updated_at", ""),
        "pushed_at": repo_data.get("pushed_at", ""),
        "default_branch": repo_data.get("default_branch", ""),
        "topics": repo_data.get("topics", []),
        "commits_count": len(commits_data) if isinstance(commits_data, list) else 0,
        "releases": [
            {
                "tag": r.get("tag_name", ""),
                "date": r.get("published_at", ""),
                "prerelease": r.get("prerelease", False)
            }
            for r in (releases_data if isinstance(releases_data, list) else [])
        ][:10],
        "contributors": [
            {
                "login": c.get("login", ""),
                "contributions": c.get("contributions", 0)
            }
            for c in (contributors_data if isinstance(contributors_data, list) else [])
        ][:30],
        "raw": {
            "repo": repo_data,
            "commits_sample": len(commits_data) if isinstance(commits_data, list) else 0,
            "issues_sample": len(issues_data) if isinstance(issues_data, list) else 0,
            "contributors_count": len(contributors_data) if isinstance(contributors_data, list) else 0
        }
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
