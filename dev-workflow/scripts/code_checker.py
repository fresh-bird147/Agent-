#!/usr/bin/env python3
"""对生成的代码进行基础语法/规范检查，辅助白盒测试。"""
import sys
import re
from collections import defaultdict
from pathlib import Path


JAVA_KEYWORDS = {
    "naming": ["Controller", "Service", "ServiceImpl", "Mapper", "Repository", "Entity", "Config", "Util", "DTO", "VO"],
    "annotations": ["@RestController", "@Service", "@Repository", "@Transactional", "@Valid",
                    "@Override", "@Autowired", "@Slf4j", "@Data", "@Builder"],
    "security": ["PreparedStatement", "@Param", "#{", "${"],
    "suspicious": ["RuntimeException", "printStackTrace", "System.out.println", "e.printStackTrace"]
}


def check_java_file(filepath: Path) -> dict:
    """检查 Java 文件的基础规范。"""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    issues = []
    lines = content.split("\n")

    # 1. 检查是否有 class 定义
    if not re.search(r"class\s+\w+", content):
        issues.append({"severity": "CRITICAL", "category": "结构", "line": 0, "description": "未找到 class 定义"})

    # 2. 检查是否有裸的 SQL 拼接（防注入）
    sql_patterns = re.findall(r'"SELECT.*\+|"INSERT.*\+|"UPDATE.*\+|"DELETE.*\+', content)
    if sql_patterns and "PreparedStatement" not in content:
        issues.append({"severity": "CRITICAL", "category": "安全", "line": 0, "description": "疑似 SQL 拼接，存在注入风险"})

    # 3. 检查 MyBatis ${} vs #{}
    dollar_brace = re.findall(r'\$\{', content)
    if dollar_brace and "like" not in content.lower():
        issues.append({"severity": "WARNING", "category": "安全", "line": 0, "description": "发现 {} 处 ${{}} ，可能导致 SQL 注入".format(len(dollar_brace))})

    # 4. 检查 Controller 是否有 @Valid
    if "Controller" in filepath.name or "@RestController" in content:
        if "@Valid" not in content and "@Validated" not in content:
            issues.append({"severity": "WARNING", "category": "规范", "line": 0, "description": "Controller 缺少 @Valid 参数校验注解"})

    # 5. 检查 Service 是否有 @Transactional
    if "ServiceImpl" in filepath.name and "@Transactional" not in content:
        issues.append({"severity": "WARNING", "category": "规范", "line": 0, "description": "Service 缺少 @Transactional 事务注解"})

    # 6. 检查是否有 printStackTrace
    pstack_count = content.count("printStackTrace")
    if pstack_count > 0:
        issues.append({"severity": "WARNING", "category": "规范", "line": 0, "description": f"发现 {pstack_count} 处 printStackTrace()，应使用日志框架"})

    # 7. 检查 hardcoded 密码/密钥
    hardcoded = re.findall(r'(password|secret|api_key|apikey|token)\s*[=:]\s*"', content, re.IGNORECASE)
    if hardcoded:
        issues.append({"severity": "CRITICAL", "category": "安全", "line": 0, "description": f"疑似硬编码敏感信息: {hardcoded}"})

    # 8. 检查是否使用 @Slf4j 而非 System.out
    if "System.out.println" in content:
        issues.append({"severity": "WARNING", "category": "规范", "line": 0, "description": "发现 System.out.println()，应使用 @Slf4j + log.info()"})

    # 9. 检查 Controller 是否包含业务逻辑（new XxxService/调用 Mapper）
    if "Controller" in filepath.name:
        if re.search(r'(new\s+\w+Service|Mapper\s+\w+\s*;)', content):
            issues.append({"severity": "CRITICAL", "category": "架构", "line": 0, "description": "Controller 不应直接实例化 Service 或持有 Mapper 引用"})

    # 10. 检查是否使用 @Data 而非手写 getter/setter
    if "Entity" in filepath.name or filepath.parent.name == "entity":
        if "@Data" not in content and "get" in content and "set" in content:
            issues.append({"severity": "SUGGESTION", "category": "规范", "line": 0, "description": "Entity 建议使用 @Data(Lombok) 替代手写 getter/setter"})

    # 11. 检查 @Transactional 是否有 rollbackFor
    transactional_lines = re.findall(r'@Transactional(?!\(.*rollbackFor)', content)
    if transactional_lines and "ServiceImpl" in filepath.name:
        # 检查是否只写了 @Transactional 没有 rollbackFor
        bare_tx = [l for l in content.split('\n') if '@Transactional' in l and 'rollbackFor' not in l]
        if bare_tx:
            issues.append({"severity": "SUGGESTION", "category": "规范", "line": 0, "description": "@Transactional 建议显式声明 rollbackFor = Exception.class"})

    # 12. 检查 @Autowired vs @RequiredArgsConstructor
    if "@Autowired" in content and "Field injection" not in content:
        issues.append({"severity": "SUGGESTION", "category": "规范", "line": 0, "description": "建议使用 @RequiredArgsConstructor + final 替代 @Autowired 字段注入"})

    # 13. 检查 Mapper XML 中的 ${} 
    if filepath.suffix == ".xml":
        xml_dollar = re.findall(r'\$\{', content)
        if xml_dollar:
            issues.append({"severity": "CRITICAL", "category": "安全", "line": 0, "description": f"Mapper XML 中发现 {len(xml_dollar)} 处 ${{}} ，存在 SQL 注入风险"})

    # 14. 统计行数
    loc = len([l for l in lines if l.strip() and not l.strip().startswith("//") and not l.strip().startswith("*")])

    return {
        "file": str(filepath),
        "lines_of_code": loc,
        "issues": issues,
        "issues_count": len(issues),
        "score": max(0, 100 - len(issues) * 10)
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python code_checker.py <source_directory>")
        sys.exit(1)

    src_dir = Path(sys.argv[1])
    java_files = list(src_dir.rglob("*.java"))
    xml_files = list(src_dir.rglob("*.xml"))
    vue_files = list(src_dir.rglob("*.vue"))

    results = []
    all_issues = []

    for f in java_files:
        r = check_java_file(f)
        results.append(r)
        all_issues.extend(r["issues"])

    for f in xml_files:
        # 检查 Mapper XML
        if "mapper" in str(f).lower() or "Mapper" in str(f):
            r = check_java_file(f)
            results.append(r)
            all_issues.extend(r["issues"])

    total_issues = len(all_issues)
    critical = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    warnings = sum(1 for i in all_issues if i["severity"] == "WARNING")
    avg_score = sum(r["score"] for r in results) / len(results) if results else 100

    import json
    output = {
        "total_files": len(java_files) + len(xml_files) + len(vue_files),
        "java_files_checked": len(java_files),
        "xml_files_checked": len(xml_files),
        "vue_files_found": len(vue_files),
        "total_issues": total_issues,
        "critical_issues": critical,
        "warnings": warnings,
        "average_score": round(avg_score, 1),
        "per_file": results
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
