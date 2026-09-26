"""重建命令：python -m kbqa.rebuild，或者 make rebuild。"""

from __future__ import annotations

import json
import sys
import time

from .cleaning import build_clean_db
from .config import load_settings
from .index import load_index
from .policy_resolver import resolve_metric_policy


def main() -> int:
    settings = load_settings()
    started = time.perf_counter()
    print("数据目录：%s" % settings.data_dir)
    print("知识库目录：%s" % settings.kb_dir)
    policy = resolve_metric_policy(settings.kb_dir, settings.today)
    print("指标口径：%s %s（生效 %s）" % (
        policy.document.doc_id,
        policy.document.title,
        policy.document.effective_from.isoformat() if policy.document.effective_from else "未知",
    ))
    report = build_clean_db(settings.source_db, settings.clean_db, policy.as_dict())
    print("清洗完成：%s" % json.dumps(report.as_dict(), ensure_ascii=False))
    # 缓存还有效就不用重算，省几秒。
    index = load_index(settings.kb_dir, settings.index_path)
    print("索引完成：%d 篇文档，%d 个片段，缓存键 %s" % (
        len(index.docs_meta), len(index.chunks), index.key[:12]
    ))
    for warning in index.warnings:
        print("告警：%s" % warning)
    print("产物：%s、%s（%.1f 秒）" % (
        settings.clean_db, settings.index_path, time.perf_counter() - started
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
