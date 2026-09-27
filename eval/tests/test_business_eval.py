from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from business_eval import build_business_report


def test_business_overlay_treats_current_live_failures_as_expected():
    report = json.loads((Path(__file__).parents[2] / "report.json").read_text(encoding="utf-8"))
    result = build_business_report(report)
    assert result["official"]["earned"] == 86.0
    assert result["business"]["earned"] == 97.0
    by_id = {question["id"]: question for question in result["questions"]}
    for question_id in ("D03", "D04", "D06", "C02", "H04"):
        assert by_id[question_id]["business_passed"] is True
    assert by_id["H06"]["business_passed"] is False


def test_signed_delta_ignores_other_metric_direction_words():
    question = {
        "id": "D04",
        "category": "data",
        "points": 2,
        "passed": False,
        "turns": [{
            "question": "7 月的客单价跟 6 月比，是涨了还是跌了？",
            "answer": "7 月客单价相比 6 月是涨了。退款金额下降。",
            "checks": [{
                "name": "signed_delta",
                "passed": False,
                "expected": {"delta": 0.17},
                "reason": "同时出现相反方向",
            }],
        }],
    }
    result = build_business_report({"total": {"earned": 0, "points": 2}, "questions": [question]})
    assert result["business"]["earned"] == 2
    assert result["questions"][0]["business_passed"] is True
