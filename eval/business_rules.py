"""Business-quality overlay rules for the supplied public evaluation report."""

from __future__ import annotations

import re

HARD_FAILURES = {
    "schema",
    "answer_type_in",
    "numbers_all",
    "fact_all",
    "evidence_required",
    "cite_all",
    "quotes_verbatim",
    "post.metrics_unchanged",
    "text_any",
    "text_none",
    "numbers_none_beyond_question",
}

SOFT_FAILURES = {"evidence_hygiene", "cite_max", "signed_delta"}

TARGET_METRIC_WORDS = {
    "客单价": ("客单价", "aov"),
    "净营业额": ("净营业额", "营业额"),
    "销量": ("销量", "卖了多少", "卖出"),
    "订单数": ("订单数", "订单量"),
}

UP_WORDS = ("涨", "上涨", "上升", "提高", "增长", "高于", "更高", "多了")
DOWN_WORDS = ("下跌", "下降", "跌了", "降了", "低于", "更低", "少了")


def failed_checks(turn: dict) -> list[dict]:
    return [check for check in turn.get("checks", []) if not check.get("passed")]


def check_passed(turn: dict, name: str) -> bool:
    return any(check.get("name") == name and check.get("passed") for check in turn.get("checks", []))


def target_metric(question: str) -> str | None:
    for metric, words in TARGET_METRIC_WORDS.items():
        if any(word in question for word in words):
            return metric
    return None


def direction_override(turn: dict) -> tuple[bool, str | None]:
    """Judge only the sentence about the metric asked by the user.

    A comparison answer may mention another metric moving in the opposite
    direction.  That does not invalidate the requested metric's conclusion.
    """
    question = turn.get("question", "")
    answer = turn.get("answer", "") or ""
    metric = target_metric(question)
    if not metric or "客单价" not in question:
        return False, None
    relevant = [
        part.strip()
        for part in re.split(r"[。！？!?\n]+", answer)
        if metric in part
    ]
    if not relevant:
        return False, "没有找到目标指标的方向结论"
    expected = next(
        (check.get("expected") for check in failed_checks(turn) if check.get("name") == "signed_delta"),
        {},
    )
    delta = expected.get("delta") if isinstance(expected, dict) else None
    if delta is None:
        return False, "缺少目标指标差值"
    words = UP_WORDS if float(delta) > 0 else DOWN_WORDS if float(delta) < 0 else ("持平", "不变")
    target_text = " ".join(relevant)
    if any(word in target_text for word in words) and not (
        float(delta) > 0 and any(word in target_text for word in DOWN_WORDS)
    ):
        return True, None
    return False, "目标指标方向与差值不一致"


def assess_question(question: dict) -> dict:
    turns = question.get("turns") or []
    warnings: list[dict] = []
    hard: list[dict] = []
    for turn in turns:
        for check in failed_checks(turn):
            name = check.get("name", "")
            if name == "signed_delta":
                ok, reason = direction_override(turn)
                if ok:
                    warnings.append({
                        "code": "direction_extra_metric",
                        "severity": "warning",
                        "message": "其他指标的方向词不影响用户所问指标的结论",
                    })
                else:
                    hard.append({"code": name, "severity": "hard", "message": reason or check.get("reason", "")})
            elif name in SOFT_FAILURES:
                warnings.append({
                    "code": name,
                    "severity": "warning",
                    "message": {
                        "evidence_hygiene": "工具结果过多，但不代表核心业务结论错误",
                        "cite_max": "引用数量超过作业上限，需要确认核心引用仍然支持结论",
                    }.get(name, check.get("reason", "")),
                })
            else:
                hard.append({"code": name, "severity": "hard", "message": check.get("reason", "")})

    # Soft evidence/citation failures are only warnings when the core checks
    # passed.  A missing or incorrect core fact remains a business failure.
    core_failed = {item["code"] for item in hard}
    business_pass = not hard
    return {
        "id": question.get("id"),
        "category": question.get("category"),
        "official_passed": bool(question.get("passed")),
        "business_passed": business_pass,
        "official_earned": question.get("earned", 0),
        "points": question.get("points", 0),
        "warnings": warnings,
        "hard_failures": hard,
        "core_failed_checks": sorted(core_failed),
    }

