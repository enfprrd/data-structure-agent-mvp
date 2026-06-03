from __future__ import annotations

from collections import deque
from typing import Any

from visualizer.protocol import Action, Highlights, NodeHighlight, OperationRequest, Step, Summary, VisualizationTrace


def simulate_graph(request: OperationRequest) -> VisualizationTrace:
    graph = _parse_graph(request.initial_state.data, request.initial_state.metadata)
    if request.operation == "bfs":
        return _bfs(request, graph)
    if request.operation == "dijkstra":
        return _dijkstra(request, graph)
    if request.operation == "build":
        return _build(request, graph)
    return _dfs(request, graph)


def _build(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    partial = {"vertices": [], "edges": [], "adj": {}}
    steps = [_step(1, "空图", "从空图开始，根据输入数据逐步建立图。", partial, None, [], "current")]
    for vertex in graph["vertices"]:
        partial["vertices"].append(vertex)
        partial["adj"][vertex] = []
        steps.append(_step(len(steps) + 1, f"添加顶点 {vertex}", f"添加顶点 {vertex}。", partial, vertex, list(partial["vertices"]), "new"))
    for edge in graph["edges"]:
        partial["edges"].append(edge)
        src = str(edge["from"])
        dst = str(edge["to"])
        weight = float(edge.get("weight", 1))
        partial["adj"].setdefault(src, []).append((dst, weight))
        steps.append(_step(len(steps) + 1, f"添加边 {src} -> {dst}", f"添加边 {src} -> {dst}。", partial, dst, [f"{item['from']}->{item['to']}" for item in partial["edges"]], "changed"))
    return VisualizationTrace(
        title="图结构建立演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=str(request.initial_state.data), result=f"{len(graph['vertices'])} 个顶点，{len(graph['edges'])} 条边", time_complexity="O(n+e)", space_complexity="O(n+e)"),
        steps=steps,
    )


def _dfs(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    start = _start_vertex(request, graph)
    visited: set[str] = set()
    order: list[str] = []
    steps = [_step(1, "初始图", f"从 {start} 开始深度优先遍历。", graph, None, order, "current")]

    def dfs(vertex: str) -> None:
        visited.add(vertex)
        order.append(vertex)
        steps.append(_step(len(steps) + 1, f"访问 {vertex}", f"访问 {vertex}，访问序列：{' -> '.join(order)}。", graph, vertex, order, "current"))
        for nxt, _weight in graph["adj"].get(vertex, []):
            if nxt not in visited:
                dfs(nxt)

    dfs(start)
    return _trace(request, "图 DFS 深度优先遍历演示", graph, order, "O(n+e)", "O(n)", steps)


def _bfs(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    start = _start_vertex(request, graph)
    visited = {start}
    queue: deque[str] = deque([start])
    order: list[str] = []
    steps = [_step(1, "初始图", f"从 {start} 开始广度优先遍历，先入队。", graph, start, order, "current")]
    while queue:
        vertex = queue.popleft()
        order.append(vertex)
        steps.append(_step(len(steps) + 1, f"出队并访问 {vertex}", f"访问 {vertex}，当前访问序列：{' -> '.join(order)}。", graph, vertex, order, "current"))
        for nxt, _weight in graph["adj"].get(vertex, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
                steps.append(_step(len(steps) + 1, f"{nxt} 入队", f"{nxt} 未访问，加入队列。", graph, nxt, order, "new"))
    return _trace(request, "图 BFS 广度优先遍历演示", graph, order, "O(n+e)", "O(n)", steps)


def _dijkstra(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    start = _start_vertex(request, graph)
    vertices = graph["vertices"]
    dist = {v: float("inf") for v in vertices}
    dist[start] = 0
    used: set[str] = set()
    steps = [_step(1, "初始化距离", f"源点 {start} 的距离为 0，其余为无穷大。", graph, start, [f"{v}:{_fmt(dist[v])}" for v in vertices], "current")]
    while len(used) < len(vertices):
        candidate = None
        for vertex in vertices:
            if vertex not in used and (candidate is None or dist[vertex] < dist[candidate]):
                candidate = vertex
        if candidate is None or dist[candidate] == float("inf"):
            break
        used.add(candidate)
        steps.append(_step(len(steps) + 1, f"确定 {candidate}", f"选择未确定顶点中距离最小的 {candidate}，距离为 {_fmt(dist[candidate])}。", graph, candidate, [f"{v}:{_fmt(dist[v])}" for v in vertices], "success"))
        for nxt, weight in graph["adj"].get(candidate, []):
            if nxt not in used and dist[candidate] + weight < dist[nxt]:
                dist[nxt] = dist[candidate] + weight
                steps.append(_step(len(steps) + 1, f"松弛 {nxt}", f"通过 {candidate} 更新 {nxt} 的距离为 {_fmt(dist[nxt])}。", graph, nxt, [f"{v}:{_fmt(dist[v])}" for v in vertices], "changed"))
    result = [f"{v}:{_fmt(dist[v])}" for v in vertices]
    return _trace(request, "Dijkstra 最短路径演示", graph, result, "O(n^2)（邻接矩阵写法）", "O(n)", steps)


def _trace(request: OperationRequest, title: str, graph: dict[str, Any], result: list[Any], time_complexity: str, space_complexity: str, steps: list[Step]) -> VisualizationTrace:
    return VisualizationTrace(
        title=title,
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=str(graph["vertices"]), result=" -> ".join(str(item) for item in result), time_complexity=time_complexity, space_complexity=space_complexity),
        steps=steps,
    )


def _step(step_id: int, title: str, description: str, graph: dict[str, Any], vertex: str | None, order: list[Any], role: str) -> Step:
    highlights = Highlights()
    if vertex is not None:
        highlights.nodes.append(NodeHighlight(id=str(vertex), role=role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase="visit" if vertex is not None else "init",
        title=title,
        description=description,
        state={"kind": "graph", "nodes": graph["vertices"], "edges": graph["edges"], "visit_order": list(order)},
        highlights=highlights,
        actions=[Action(type="visit", description=description, target=str(vertex))] if vertex is not None else [],
        message=description,
    )


def _parse_graph(data: list[Any], metadata: dict[str, Any]) -> dict[str, Any]:
    vertices = [str(v) for v in metadata.get("vertices", [])]
    edges: list[dict[str, Any]] = []
    if data and all(isinstance(row, list) for row in data):
        size = len(data)
        if not vertices:
            vertices = [chr(ord("A") + index) for index in range(size)]
        for i, row in enumerate(data):
            for j, value in enumerate(row):
                if value:
                    edges.append({"from": vertices[i], "to": vertices[j], "weight": value})
    else:
        for item in data:
            if isinstance(item, dict):
                src = str(item.get("from"))
                dst = str(item.get("to"))
                weight = item.get("weight", 1)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                src, dst = str(item[0]), str(item[1])
                weight = item[2] if len(item) > 2 else 1
            else:
                continue
            edges.append({"from": src, "to": dst, "weight": weight})
            vertices.extend([src, dst])
        vertices = list(dict.fromkeys(vertices))
    adj: dict[str, list[tuple[str, float]]] = {vertex: [] for vertex in vertices}
    directed = bool(metadata.get("directed", True))
    for edge in edges:
        src = str(edge["from"])
        dst = str(edge["to"])
        weight = float(edge.get("weight", 1))
        adj.setdefault(src, []).append((dst, weight))
        adj.setdefault(dst, [])
        if not directed:
            adj[dst].append((src, weight))
    return {"vertices": vertices, "edges": edges, "adj": adj}


def _start_vertex(request: OperationRequest, graph: dict[str, Any]) -> str:
    start = request.params.value or request.params.target or request.initial_state.metadata.get("start")
    return str(start or (graph["vertices"][0] if graph["vertices"] else "A"))


def _fmt(value: float) -> str:
    if value == float("inf"):
        return "∞"
    return str(int(value)) if value == int(value) else str(value)
