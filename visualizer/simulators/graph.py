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
    if request.operation == "prim":
        return _prim(request, graph)
    if request.operation == "kruskal":
        return _kruskal(request, graph)
    if request.operation == "floyd":
        return _floyd(request, graph)
    if request.operation == "topological_sort":
        return _topological_sort(request, graph)
    if request.operation == "build":
        return _build(request, graph)
    return _dfs(request, graph)


def _build(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    partial = {"vertices": [], "edges": [], "adj": {}, "directed": graph.get("directed", True)}
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


def _prim(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    vertices = graph["vertices"]
    if not vertices:
        return _trace(request, "Prim 最小生成树演示", graph, [], "O(n^2)", "O(n)", [])

    start = _start_vertex(request, graph)
    selected = {start}
    mst_edges: list[dict[str, Any]] = []
    steps = [_step(1, "初始化顶点集合", f"从顶点 {start} 开始，当前生成树顶点集合 S={{ {start} }}。", graph, start, [f"S:{start}"], "current")]

    while len(selected) < len(vertices):
        candidate: tuple[float, str, str] | None = None
        for edge in _undirected_edges(graph):
            src = str(edge["from"])
            dst = str(edge["to"])
            weight = float(edge.get("weight", 1))
            crosses = (src in selected and dst not in selected) or (dst in selected and src not in selected)
            if crosses and (candidate is None or weight < candidate[0]):
                candidate = (weight, src, dst)

        if candidate is None:
            steps.append(_step(len(steps) + 1, "图不连通", "当前集合无法再连接新顶点，说明图不连通，不能得到完整最小生成树。", graph, None, _mst_order(mst_edges), "error"))
            break

        weight, src, dst = candidate
        new_vertex = dst if src in selected else src
        selected.add(new_vertex)
        chosen = {"from": src, "to": dst, "weight": weight}
        mst_edges.append(chosen)
        steps.append(
            _step(
                len(steps) + 1,
                f"选择边 {src}-{dst}",
                f"选择连接 S 内外顶点的最小边 {src}-{dst}，权值为 {_fmt(weight)}，把 {new_vertex} 加入 S。",
                {**graph, "edges": mst_edges, "directed": False},
                new_vertex,
                _mst_order(mst_edges),
                "success",
            )
        )

    total = sum(float(edge.get("weight", 1)) for edge in mst_edges)
    result = _mst_order(mst_edges) + [f"总权值:{_fmt(total)}"]
    return _trace(request, "Prim 最小生成树演示", {**graph, "edges": mst_edges or graph["edges"], "directed": False}, result, "O(n^2)（邻接矩阵写法）", "O(n)", steps)


def _kruskal(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    vertices = graph["vertices"]
    parent = {vertex: vertex for vertex in vertices}
    mst_edges: list[dict[str, Any]] = []
    sorted_edges = sorted(_undirected_edges(graph), key=lambda edge: float(edge.get("weight", 1)))
    steps = [_step(1, "按权值排序边", "Kruskal 先按边权从小到大排序，再依次尝试选边。", graph, None, [f"{e['from']}-{e['to']}:{_fmt(float(e.get('weight', 1)))}" for e in sorted_edges], "current")]

    def find(vertex: str) -> str:
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    for edge in sorted_edges:
        src = str(edge["from"])
        dst = str(edge["to"])
        weight = float(edge.get("weight", 1))
        root_src = find(src)
        root_dst = find(dst)
        if root_src == root_dst:
            steps.append(_step(len(steps) + 1, f"跳过边 {src}-{dst}", f"边 {src}-{dst} 会形成回路，跳过。", {**graph, "edges": mst_edges, "directed": False}, src, _mst_order(mst_edges), "error"))
            continue

        parent[root_src] = root_dst
        mst_edges.append({"from": src, "to": dst, "weight": weight})
        steps.append(_step(len(steps) + 1, f"加入边 {src}-{dst}", f"边 {src}-{dst} 不形成回路，加入生成树。", {**graph, "edges": mst_edges, "directed": False}, dst, _mst_order(mst_edges), "success"))
        if len(mst_edges) == max(0, len(vertices) - 1):
            break

    total = sum(float(edge.get("weight", 1)) for edge in mst_edges)
    result = _mst_order(mst_edges) + [f"总权值:{_fmt(total)}"]
    return _trace(request, "Kruskal 最小生成树演示", {**graph, "edges": mst_edges or graph["edges"], "directed": False}, result, "O(e log e)", "O(n)", steps)


def _floyd(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    vertices = graph["vertices"]
    index = {vertex: i for i, vertex in enumerate(vertices)}
    dist = [[float("inf")] * len(vertices) for _ in vertices]
    for i in range(len(vertices)):
        dist[i][i] = 0
    for edge in graph["edges"]:
        src = str(edge["from"])
        dst = str(edge["to"])
        weight = float(edge.get("weight", 1))
        dist[index[src]][index[dst]] = min(dist[index[src]][index[dst]], weight)
        if not graph["directed"]:
            dist[index[dst]][index[src]] = min(dist[index[dst]][index[src]], weight)

    steps = [_step(1, "初始化距离矩阵", "用邻接矩阵初始化任意两点之间的当前最短距离。", graph, None, _dist_rows(vertices, dist), "current")]
    for k, mid in enumerate(vertices):
        steps.append(_step(len(steps) + 1, f"允许经过 {mid}", f"尝试把 {mid} 作为中间顶点更新所有最短路径。", graph, mid, _dist_rows(vertices, dist), "current"))
        for i, src in enumerate(vertices):
            for j, dst in enumerate(vertices):
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
                    steps.append(_step(len(steps) + 1, f"更新 {src}->{dst}", f"经过 {mid} 后，{src}->{dst} 的距离更新为 {_fmt(dist[i][j])}。", graph, dst, _dist_rows(vertices, dist), "changed"))

    return _trace(request, "Floyd 多源最短路径演示", graph, _dist_rows(vertices, dist), "O(n^3)", "O(n^2)", steps)


def _topological_sort(request: OperationRequest, graph: dict[str, Any]) -> VisualizationTrace:
    vertices = graph["vertices"]
    indegree = {vertex: 0 for vertex in vertices}
    for edge in graph["edges"]:
        indegree[str(edge["to"])] = indegree.get(str(edge["to"]), 0) + 1

    queue: deque[str] = deque([vertex for vertex in vertices if indegree.get(vertex, 0) == 0])
    order: list[str] = []
    steps = [_step(1, "计算入度", "拓扑排序先计算每个顶点的入度，并把入度为 0 的顶点入队。", graph, None, _indegree_rows(vertices, indegree), "current")]
    while queue:
        vertex = queue.popleft()
        order.append(vertex)
        steps.append(_step(len(steps) + 1, f"输出 {vertex}", f"输出入度为 0 的顶点 {vertex}。", graph, vertex, list(order), "success"))
        for nxt, _weight in graph["adj"].get(vertex, []):
            indegree[nxt] -= 1
            steps.append(_step(len(steps) + 1, f"删除边 {vertex}->{nxt}", f"删除 {vertex}->{nxt} 后，{nxt} 的入度变为 {indegree[nxt]}。", graph, nxt, _indegree_rows(vertices, indegree), "changed"))
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) < len(vertices):
        steps.append(_step(len(steps) + 1, "检测到回路", "还有顶点未输出，说明图中存在回路，无法得到完整拓扑序列。", graph, None, list(order), "error"))
        result = list(order) + ["存在回路"]
    else:
        result = list(order)
    return _trace(request, "拓扑排序演示", graph, result, "O(n+e)", "O(n)", steps)


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
        state={"kind": "graph", "nodes": graph["vertices"], "edges": graph["edges"], "visit_order": list(order), "directed": graph.get("directed", True)},
        highlights=highlights,
        actions=[Action(type="visit", description=description, target=str(vertex))] if vertex is not None else [],
        message=description,
    )


def _parse_graph(data: list[Any], metadata: dict[str, Any]) -> dict[str, Any]:
    vertices = [str(v) for v in metadata.get("vertices", [])]
    edges: list[dict[str, Any]] = []
    directed = bool(metadata.get("directed", True))
    if data and _looks_like_adjacency_matrix(data):
        size = len(data)
        if not vertices:
            vertices = [chr(ord("A") + index) for index in range(size)]
        for i, row in enumerate(data):
            for j, value in enumerate(row):
                if not directed and j < i:
                    continue
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
    for edge in edges:
        src = str(edge["from"])
        dst = str(edge["to"])
        weight = float(edge.get("weight", 1))
        adj.setdefault(src, []).append((dst, weight))
        adj.setdefault(dst, [])
        if not directed:
            adj[dst].append((src, weight))
    return {"vertices": vertices, "edges": edges, "adj": adj, "directed": directed}


def _start_vertex(request: OperationRequest, graph: dict[str, Any]) -> str:
    start = request.params.value or request.params.target or request.initial_state.metadata.get("start")
    return str(start or (graph["vertices"][0] if graph["vertices"] else "A"))


def _fmt(value: float) -> str:
    if value == float("inf"):
        return "∞"
    return str(int(value)) if value == int(value) else str(value)


def _looks_like_adjacency_matrix(data: list[Any]) -> bool:
    if not data or not all(isinstance(row, list) for row in data):
        return False
    size = len(data)
    if not all(len(row) == size for row in data):
        return False
    for row in data:
        for value in row:
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                continue
            if isinstance(value, str):
                try:
                    float(value)
                except ValueError:
                    return False
                continue
            if value is None:
                continue
            return False
    return True


def _undirected_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for edge in graph["edges"]:
        src = str(edge["from"])
        dst = str(edge["to"])
        key = tuple(sorted((src, dst)))
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _mst_order(edges: list[dict[str, Any]]) -> list[str]:
    return [f"{edge['from']}-{edge['to']}:{_fmt(float(edge.get('weight', 1)))}" for edge in edges]


def _dist_rows(vertices: list[str], dist: list[list[float]]) -> list[str]:
    rows = []
    for vertex, row in zip(vertices, dist):
        rows.append(vertex + ": " + ", ".join(_fmt(value) for value in row))
    return rows


def _indegree_rows(vertices: list[str], indegree: dict[str, int]) -> list[str]:
    return [f"{vertex}:入度{indegree.get(vertex, 0)}" for vertex in vertices]
