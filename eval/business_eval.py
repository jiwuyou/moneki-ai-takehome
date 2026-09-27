"""Re-score an official report using business-quality severity rules.

The supplied evaluator is never modified.  This command reads its report and
adds a second, business-oriented view where excessive but correct evidence is
a warning instead of a failed business answer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_rules import assess_question


def build_business_report(report: dict, metadata: dict | None = None) -> dict:
    questions = [assess_question(question) for question in report.get("questions", [])]
    metadata = metadata or {}
    for question in questions:
        question["business_rule"] = metadata.get(question["id"])
    points = sum(float(question.get("points", 0) or 0) for question in report.get("questions", []))
    earned = sum(
        float(question["points"] or 0)
        for question in questions
        if question["business_passed"]
    )
    return {
        "source_report": report.get("generated_at"),
        "official": report.get("total", {}),
        "business": {
            "points": points,
            "earned": earned,
            "ratio": earned / points if points else 0.0,
            "questions": len(questions),
            "passed": sum(1 for question in questions if question["business_passed"]),
        },
        "questions": questions,
    }


def render_markdown(result: dict) -> str:
    official = result["official"]
    business = result["business"]
    lines = [
        "# 业务质量评估报告",
        "",
        "官方分数：**%.2f / %.2f**" % (official.get("earned", 0), official.get("points", 0)),
        "业务质量分：**%.2f / %.2f**" % (business["earned"], business["points"]),
        "",
        "业务覆盖层不修改官方评测逻辑；证据过多、引用过多和其他指标的方向词只作为 warning。",
        "",
        "| 题目 | 官方 | 业务 | 警告 | 硬失败 |",
        "|---|---:|---:|---|---|",
    ]
    for question in result["questions"]:
        warnings = "；".join(item["code"] for item in question["warnings"]) or "—"
        hard = "；".join(item["code"] for item in question["hard_failures"]) or "—"
        lines.append(
            "| %s | %s | %s | %s | %s |"
            % (
                question["id"],
                "通过" if question["official_passed"] else "失败",
                "通过" if question["business_passed"] else "失败",
                warnings,
                hard,
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="report.json")
    parser.add_argument("--out", default="business_report")
    parser.add_argument("--rules", default=str(Path(__file__).with_name("business_questions.jsonl")))
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    metadata = {}
    rules_path = Path(args.rules)
    if rules_path.exists():
        for line in rules_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                metadata[item["id"]] = item.get("business")
    result = build_business_report(report, metadata)
    output = Path(args.out)
    json_path = output.with_suffix(".json")
    md_path = output.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print("官方分数：%.2f / %.2f" % (result["official"].get("earned", 0), result["official"].get("points", 0)))
    print("业务质量分：%.2f / %.2f" % (result["business"]["earned"], result["business"]["points"]))
    print("报告：%s、%s" % (md_path, json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
