#!/usr/bin/env python3
"""启发式挑出仓库里最值得 review 的核心文件。"""
import sys
from pathlib import Path

# 文件评分规则
def score_file(path: Path, repo_root: Path) -> int:
    rel = path.relative_to(repo_root).as_posix()
    score = 0

    # 主要源码目录加分
    if any(rel.startswith(p) for p in ["src/", "lib/", "internal/", "pkg/"]):
        score += 50
    # 入口文件加分
    if path.name in ("main.py", "main.rs", "main.go", "index.ts", "index.js", "app.py", "lib.rs"):
        score += 30
    # 核心模块名加分
    for kw in ("core", "engine", "kernel", "runtime", "scheduler", "orchestrator"):
        if kw in rel.lower():
            score += 20

    # 测试文件减分（不是这次的 review 对象）
    if "test" in rel.lower() or "spec" in rel.lower():
        score -= 100
    # 配置 / 构建文件减分
    if path.suffix in (".yaml", ".yml", ".toml", ".json", ".lock"):
        score -= 50
    # 文档减分
    if path.suffix in (".md", ".rst"):
        score -= 80

    # 文件大小评分（太小 / 太大都减分）
    try:
        size = path.stat().st_size
        if 500 <= size <= 30000:  # 0.5KB - 30KB 是 sweet spot
            score += 10
        elif size < 200:
            score -= 30
        elif size > 100000:
            score -= 20
    except OSError:
        return -1

    return score

def main():
    repo_root = Path(sys.argv[1])
    candidates = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        s = score_file(p, repo_root)
        if s > 0:
            candidates.append((s, str(p.relative_to(repo_root))))

    candidates.sort(reverse=True)
    for _, path in candidates[:10]:
        print(path)

if __name__ == "__main__":
    main()
