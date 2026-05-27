#!/usr/bin/env python3
"""解析需求文档，提取纯文本内容供 Requirement Agent 分析。"""
import sys
import re
from pathlib import Path


def extract_text(filepath: str) -> str:
    """从不同格式文件提取纯文本。"""
    path = Path(filepath)
    suffix = path.suffix.lower()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if suffix == ".md":
        return content

    elif suffix == ".json":
        import json
        return json.dumps(json.loads(content), ensure_ascii=False, indent=2)

    elif suffix == ".html" or suffix == ".htm":
        # 简单去标签
        text = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    elif suffix == ".txt":
        return content

    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(path)
            return "\n".join([p.text for p in doc.paragraphs])
        except ImportError:
            return f"[ERROR: 需要安装 python-docx 来解析 .docx 文件]\n{content[:500]}"

    else:
        return content


def main():
    if len(sys.argv) < 2:
        print("用法: python parse_requirement.py <需求文档路径>")
        print("输出: 纯文本内容（stdout）")
        sys.exit(1)

    text = extract_text(sys.argv[1])
    print(text)


if __name__ == "__main__":
    main()
