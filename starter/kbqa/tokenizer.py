"""分词。"""

from __future__ import annotations

import unicodedata
import re

#: 分词规则变了，索引缓存必须失效。
TOKENIZER_VERSION = "tokenizer-3"

#: 中文里几乎不携带信息的字。只用在“查询覆盖率”上，索引照常保留全部词。
STOP_CHARS = frozenset("的了吗呢是在有和与及或就都也还把被给对从向于个些这那哪什么怎样如何多少几请帮我你他它可以能要想会一下少吧啊呀们么样过得着为所")
STOP_WORDS = frozenset("the a an of to in is are and or for on at it this that how what".split())


def normalise(text: str) -> str:
    """全角转半角、统一大小写，比较与分词都走这一层。"""
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text for BM25.

    Whitespace splitting treats a whole Chinese question as one impossible
    token.  Use overlapping Chinese bigrams plus Latin/numeric words while
    retaining single Chinese characters for short labels.
    """
    text = normalise(text)
    tokens: list[str] = []
    for match in re.finditer(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[-'][a-z0-9]+)*", text):
        value = match.group(0)
        if re.fullmatch(r"[\u3400-\u9fff]+", value):
            if len(value) == 1:
                tokens.append(value)
            else:
                tokens.extend(value[i : i + 2] for i in range(len(value) - 1))
        else:
            tokens.append(value)
    return tokens


def content_tokens(text: str) -> list[str]:
    """去掉虚词之后的查询词，用来算“这个问题被文档覆盖了多少”。"""
    kept = []
    for token in tokenize(text):
        if token in STOP_WORDS:
            continue
        if all(char in STOP_CHARS for char in token):
            continue
        kept.append(token)
    return kept
