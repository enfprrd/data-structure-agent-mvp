from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]")
DOMAIN_TERMS = [
    "数据结构",
    "抽象数据类型",
    "算法",
    "时间复杂度",
    "空间复杂度",
    "线性表",
    "顺序表",
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
        normalized = [chunk.strip() for chunk in chunks if chunk.strip()]
        return normalized

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(text)]

    def _score(self, query: str, query_counter: Counter[str], chunk: str) -> int:
        chunk_tokens = Counter(self._tokenize(chunk))
        score = 0
        for token, count in query_counter.items():
            score += min(count, chunk_tokens.get(token, 0)) * 3
            if token in chunk.lower():
                score += 1

        query_lower = query.lower()
        chunk_lower = chunk.lower()
        for term in DOMAIN_TERMS:
            term_lower = term.lower()
            if term_lower in query_lower and term_lower in chunk_lower:
                score += len(term) * 8

        headings = re.findall(r"^#{1,6}\s+(.+)$", chunk, flags=re.MULTILINE)
        for heading in headings:
            heading_lower = heading.lower()
            for term in DOMAIN_TERMS:
                term_lower = term.lower()
                if term_lower in query_lower and term_lower in heading_lower:
                    score += len(term) * 12
        return score
