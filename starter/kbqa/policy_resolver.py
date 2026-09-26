"""Resolve the authoritative metric policy from the knowledge base.

The data pipeline must not guess between old manuals, estimates, and current
rules.  This module keeps that decision explicit and records the source used
for every rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .loader import Document, load_knowledge_base


@dataclass(frozen=True)
class PolicyResolution:
    document: Document
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "doc_id": self.document.doc_id,
            "title": self.document.title,
            "type": self.document.doc_type,
            "status": self.document.status,
            "effective_from": (
                self.document.effective_from.isoformat()
                if self.document.effective_from
                else None
            ),
            "updated_at": self.document.updated_at.isoformat()
            if self.document.updated_at
            else None,
            "superseded_by": self.document.superseded_by,
            "filename": self.document.path.name,
        }


def resolve_metric_policy(kb_dir: Path, as_of: date) -> PolicyResolution:
    """Choose the latest effective, current metric manual.

    A missing or ambiguous policy is an error: silently falling back to an old
    manual would make every metric untrustworthy.
    """

    documents, warnings = load_knowledge_base(kb_dir)
    manuals = [
        document
        for document in documents
        if document.doc_type == "手册"
        and document.status == "现行"
        and document.effective_from is not None
        and document.effective_from <= as_of
        and not document.superseded_by
    ]
    if not manuals:
        raise RuntimeError("知识库中没有找到截至 %s 生效的现行指标手册" % as_of.isoformat())

    manuals.sort(
        key=lambda document: (
            document.effective_from or date.min,
            document.updated_at or date.min,
            document.doc_id,
        ),
        reverse=True,
    )
    chosen = manuals[0]
    same_date = [
        document
        for document in manuals
        if document.effective_from == chosen.effective_from
    ]
    if len(same_date) > 1:
        warnings.append(
            "现行指标手册存在相同生效日期的候选：%s；已按 updated_at/doc_id 选择 %s"
            % ("、".join(document.doc_id for document in same_date), chosen.doc_id)
        )
    return PolicyResolution(chosen, warnings)

