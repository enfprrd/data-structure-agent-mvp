from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]")
SPACE_PATTERN = re.compile(r"\s+")
PHRASE_ALIASES = {
    "归并算法": "归并排序",
    "合并排序": "归并排序",
}
STOP_TOKENS = {
    "的",
    "了",
    "和",
    "与",
    "是",
    "在",
    "有",
    "把",
    "这",
    "那",
    "个",
    "一",
    "二",
    "三",
    "么",
    "什",
    "怎",
    "吗",
    "呢",
    "啊",
}
DOMAIN_TERMS = [
    "数据结构",
    "抽象数据类型",
    "算法",
    "时间复杂度",
    "空间复杂度",
    "线性表",
    "顺序表",
    "顺序表与链表",
    "链表",
    "单链表",
    "循环链表",
    "双向链表",
    "头结点",
    "头指针",
    "首元结点",
    "顺序存储",
    "链式存储",
    "插入",
    "删除",
    "查找",
    "按位查找",
    "按值查找",
    "长度",
    "长度统计",
    "遍历",
    "栈",
    "顺序栈",
    "链栈",
    "入栈",
    "出栈",
    "队列",
    "循环队列",
    "链队列",
    "入队",
    "出队",
    "串",
    "字符串",
    "模式匹配",
    "KMP",
    "next数组",
    "数组",
    "广义表",
    "稀疏矩阵",
    "三元组",
    "树",
    "二叉树",
    "先序遍历",
    "中序遍历",
    "后序遍历",
    "层序遍历",
    "线索二叉树",
    "哈夫曼树",
    "图",
    "邻接矩阵",
    "邻接表",
    "DFS",
    "BFS",
    "深度优先",
    "广度优先",
    "最小生成树",
    "Prim",
    "Kruskal",
    "最短路径",
    "Dijkstra",
    "Floyd",
    "拓扑排序",
    "顺序查找",
    "折半查找",
    "二叉排序树",
    "平衡二叉树",
    "B树",
    "B+树",
    "散列表",
    "排序",
    "插入排序",
    "希尔排序",
    "冒泡排序",
    "快速排序",
    "选择排序",
    "堆排序",
    "归并排序",
    "基数排序",
    "外部排序",
    "外排",
    "多路归并",
    "败者树",
    "置换选择",
]


class MarkdownKeywordRetriever:
    def __init__(self, knowledge_dir: Path | str) -> None:
        self.knowledge_dir = Path(knowledge_dir)

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, str]]:
        query_tokens = self._tokenize(query)
        if not query_tokens and not any(term in query for term in DOMAIN_TERMS):
            return []

        query_counter = Counter(query_tokens)
        candidates: list[dict[str, str]] = []

        for markdown_file in sorted(self.knowledge_dir.glob("*.md")):
            text = markdown_file.read_text(encoding="utf-8")
            for chunk_index, chunk in enumerate(self._split_markdown(text), start=1):
                score = self._score(query, query_counter, chunk)
                if score <= 0:
                    continue

                candidates.append(
                    {
                        "source": f"{markdown_file.name}#片段{chunk_index}",
                        "content": chunk.strip(),
                        "score": str(score),
                    }
                )

        candidates.sort(key=lambda item: int(item["score"]), reverse=True)
        return candidates[:top_k]

    def _split_markdown(self, text: str) -> list[str]:
        chunks = re.split(r"\n(?=##\s+)", text)
        title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        document_title = title_match.group(0) if title_match else ""
        normalized: list[str] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            if document_title and chunk.startswith("##"):
                chunk = f"{document_title}\n\n{chunk}"
            normalized.append(chunk)
        return normalized

    def _tokenize(self, text: str) -> list[str]:
        return [
            token.lower()
            for token in TOKEN_PATTERN.findall(text)
            if token.lower() not in STOP_TOKENS
        ]

    def _score(self, query: str, query_counter: Counter[str], chunk: str) -> int:
        chunk_tokens = Counter(self._tokenize(chunk))
        score = 0
        for token, count in query_counter.items():
            score += min(count, chunk_tokens.get(token, 0)) * 3
            if token in chunk.lower():
                score += 1

        query_lower = query.lower()
        chunk_lower = chunk.lower()
        query_compact = self._compact_for_phrase_match(query_lower)
        chunk_compact = self._compact_for_phrase_match(chunk_lower)
        matched_terms: list[str] = []
        for term in self._active_domain_terms(query_compact):
            term_lower = term.lower()
            term_compact = self._compact_for_phrase_match(term_lower)
            if term_compact in query_compact and term_compact in chunk_compact:
                matched_terms.append(term_lower)
                score += len(term) * 8

        headings = re.findall(r"^#{1,6}\s+(.+)$", chunk, flags=re.MULTILINE)
        for heading in headings:
            heading_lower = heading.lower()
            heading_compact = self._compact_for_phrase_match(heading_lower)
            for term in self._active_domain_terms(query_compact):
                term_lower = term.lower()
                term_compact = self._compact_for_phrase_match(term_lower)
                if term_compact in query_compact and term_compact in heading_compact:
                    score += len(term) * 12

        if matched_terms and headings:
            first_heading = self._compact_for_phrase_match(headings[0].lower())
            if any(self._compact_for_phrase_match(term) in first_heading for term in matched_terms):
                score += 30
        return score

    def _compact_for_phrase_match(self, text: str) -> str:
        compact = SPACE_PATTERN.sub("", text).replace("和", "与")
        for alias, canonical in PHRASE_ALIASES.items():
            compact = compact.replace(alias, canonical)
        return compact

    def _active_domain_terms(self, query_compact: str) -> list[str]:
        matched = [
            term
            for term in DOMAIN_TERMS
            if self._compact_for_phrase_match(term.lower()) in query_compact
        ]
        active: list[str] = []
        for term in matched:
            term_compact = self._compact_for_phrase_match(term.lower())
            if len(term_compact) == 1 and any(
                len(other_compact := self._compact_for_phrase_match(other.lower())) > 1
                and term_compact in other_compact
                for other in matched
            ):
                continue
            active.append(term)
        return active
