from __future__ import annotations

from collections import deque
from typing import Any

from visualizer.protocol import Action, Highlights, OperationRequest, Step, Summary, VisualizationTrace


def simulate_stack_application(request: OperationRequest) -> VisualizationTrace:
    handlers = {
        "linked_push": _linked_push,
        "linked_pop": _linked_pop,
        "base_conversion": _base_conversion,
        "bracket_matching": _bracket_matching,
        "expression_bracket_check": _bracket_matching,
        "infix_to_postfix": _infix_to_postfix,
        "postfix_evaluation": _postfix_evaluation,
        "prefix_evaluation": _prefix_evaluation,
        "expression_evaluation": _expression_evaluation,
        "call_stack": _call_stack,
        "recursion_trace": _recursion_trace,
        "hanoi_recursive": _hanoi_recursive,
        "hanoi_iterative": _hanoi_iterative,
        "maze_backtracking": _maze_backtracking,
        "dfs_iterative": _dfs_iterative,
        "binary_tree_preorder_iterative": _tree_preorder,
        "binary_tree_inorder_iterative": _tree_inorder,
        "binary_tree_postorder_iterative": _tree_postorder,
        "browser_history": _browser_history,
        "undo_redo": _undo_redo,
        "tag_matching": _tag_matching,
        "syntax_parse_stack": _syntax_parse_stack,
        "monotonic_stack": _next_greater_element,
        "next_greater_element": _next_greater_element,
        "largest_rectangle": _largest_rectangle,
        "daily_temperatures": _daily_temperatures,
        "stack_sort": _stack_sort,
        "two_stacks_queue": _two_stacks_queue,
        "reverse_stack": _reverse_stack,
        "train_rearrangement": _train_rearrangement,
        "pop_sequence_validation": _pop_sequence_validation,
    }
    return handlers[request.operation](request)


def _trace(request: OperationRequest, title: str, steps: list[Step], result: str, time: str, space: str) -> VisualizationTrace:
    initial = _format_initial(request.initial_state.data)
    return VisualizationTrace(
        title=title,
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=result, time_complexity=time, space_complexity=space),
        steps=steps,
    )


def _state(
    stacks: dict[str, list[Any]] | list[Any],
    *,
    input_items: list[Any] | None = None,
    output_items: list[Any] | None = None,
    note: str = "",
    current: Any | None = None,
) -> dict[str, Any]:
    if isinstance(stacks, list):
        stack_map = {"stack": list(stacks)}
    else:
        stack_map = {name: list(values) for name, values in stacks.items()}
    return {
        "kind": "stack_app",
        "stacks": stack_map,
        "input": list(input_items or []),
        "output": list(output_items or []),
        "current": current,
        "note": note,
    }


def _step(
    step_id: int,
    phase: str,
    title: str,
    description: str,
    stacks: dict[str, list[Any]] | list[Any],
    *,
    input_items: list[Any] | None = None,
    output_items: list[Any] | None = None,
    action: Action | None = None,
    code_refs: list[str] | None = None,
    current: Any | None = None,
) -> Step:
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(stacks, input_items=input_items, output_items=output_items, current=current),
        highlights=Highlights(),
        actions=[action] if action else [],
        code_refs=code_refs or [],
        message=description,
    )


def _format_initial(data: list[Any]) -> str:
    return "[" + ", ".join(str(item) for item in data) + "]"


def _as_tokens(request: OperationRequest, default: list[Any]) -> list[Any]:
    if request.params.values:
        return list(request.params.values)
    if request.initial_state.data:
        return list(request.initial_state.data)
    if request.params.value is not None:
        value = request.params.value
        if isinstance(value, str):
            return value.split()
        return [value]
    return list(default)


def _as_text(request: OperationRequest, default: str) -> str:
    if request.params.value is not None:
        return str(request.params.value)
    if request.initial_state.data:
        return "".join(str(item) for item in request.initial_state.data)
    return default


def _linked_push(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data or [10, 20])
    value = request.params.value if request.params.value is not None else 99
    steps = [
        _step(1, "init", "链栈初始状态", "链栈通常用链表头部作为栈顶。", data),
        _step(2, "create", "创建新结点", f"申请新结点，数据域写入 {value}。", data, action=Action(type="create_node", description="s = malloc(sizeof(Node)); s->data = value;", value=value)),
        _step(3, "link", "新结点指向原栈顶", "让 s->next 指向原来的 top。", data, action=Action(type="link", description="s->next = top;", target="s->next")),
        _step(4, "push", "更新栈顶指针", "top 指向新结点，入栈完成。", [value] + data, action=Action(type="push", description="top = s;", value=value)),
    ]
    return _trace(request, "链栈入栈演示", steps, _format_initial([value] + data), "O(1)", "O(1)")


def _linked_pop(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data or [30, 20, 10])
    popped = data[0]
    result = data[1:]
    steps = [
        _step(1, "init", "链栈初始状态", "链栈栈顶在链表头部。", data),
        _step(2, "check", "检查空栈", "top != NULL，可以出栈。", data, action=Action(type="check_condition", description="if (top == NULL) return ERROR;", target="top")),
        _step(3, "pop", "保存栈顶结点", f"读取栈顶元素 {popped}。", data, action=Action(type="pop", description="p = top; value = p->data;", value=popped)),
        _step(4, "unlink", "更新 top 并释放结点", "top 后移到下一个结点。", result, action=Action(type="delete_node", description="top = top->next; free(p);", value=popped)),
    ]
    return _trace(request, "链栈出栈演示", steps, _format_initial(result), "O(1)", "O(1)")


def _base_conversion(request: OperationRequest) -> VisualizationTrace:
    number = int(request.params.value or (request.initial_state.data[0] if request.initial_state.data else 13))
    base = int(request.params.target or request.initial_state.metadata.get("base") or 2)
    original = number
    digits = "0123456789ABCDEF"
    stack: list[str] = []
    steps = [_step(1, "init", "准备转换", f"把十进制数 {original} 转成 {base} 进制。", stack, input_items=[original])]
    step_id = 2
    while number:
        rem = number % base
        stack.append(digits[rem])
        steps.append(_step(step_id, "push", "余数入栈", f"{number} % {base} = {rem}，余数 {digits[rem]} 入栈。", stack, action=Action(type="push", description="push(n % base);", value=digits[rem])))
        number //= base
        step_id += 1
    output: list[str] = []
    while stack:
        output.append(stack.pop())
        steps.append(_step(step_id, "pop", "逆序出栈", "依次弹出余数，得到高位到低位的结果。", stack, output_items=output, action=Action(type="pop", description="digit = pop();", value=output[-1])))
        step_id += 1
    result = "".join(output) or "0"
    return _trace(request, "进制转换演示", steps, result, "O(log n)", "O(log n)")


def _bracket_matching(request: OperationRequest) -> VisualizationTrace:
    text = _as_text(request, "([{}])")
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    stack: list[str] = []
    steps = [_step(1, "init", "开始扫描括号串", f"输入串：{text}", stack, input_items=list(text))]
    ok = True
    for index, ch in enumerate(text, start=1):
        if ch in opens:
            stack.append(ch)
            steps.append(_step(len(steps) + 1, "push", "左括号入栈", f"读到 {ch}，压入栈。", stack, input_items=list(text), action=Action(type="push", description="push(leftBracket);", value=ch), current=ch))
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                ok = False
                steps.append(_step(len(steps) + 1, "compare", "匹配失败", f"第 {index} 个字符 {ch} 与栈顶不匹配。", stack, input_items=list(text), action=Action(type="compare", description="top 与右括号不匹配。", value=ch), current=ch))
                break
            top = stack.pop()
            steps.append(_step(len(steps) + 1, "pop", "匹配成功并出栈", f"{top} 与 {ch} 匹配，弹出栈顶。", stack, input_items=list(text), action=Action(type="pop", description="pop();", value=top), current=ch))
    if ok and stack:
        ok = False
        steps.append(_step(len(steps) + 1, "check", "扫描结束但栈非空", "还有未匹配的左括号。", stack, input_items=list(text), action=Action(type="check_condition", description="stack 非空，匹配失败。")))
    steps.append(_step(len(steps) + 1, "done", "检查结束", "括号匹配成功。" if ok else "括号匹配失败。", stack, input_items=list(text)))
    return _trace(request, "括号匹配演示", steps, "匹配成功" if ok else "匹配失败", "O(n)", "O(n)")


def _infix_to_postfix(request: OperationRequest) -> VisualizationTrace:
    tokens = _as_tokens(request, ["3", "+", "5", "*", "2"])
    priority = {"+": 1, "-": 1, "*": 2, "/": 2}
    stack: list[str] = []
    output: list[str] = []
    steps = [_step(1, "init", "开始中缀转后缀", "运算符入栈，操作数直接输出。", stack, input_items=tokens, output_items=output)]
    for token in tokens:
        token = str(token)
        if token.isalnum() and token not in priority:
            output.append(token)
            steps.append(_step(len(steps) + 1, "visit", "输出操作数", f"{token} 是操作数，直接进入后缀表达式。", stack, input_items=tokens, output_items=output, action=Action(type="visit", description="output operand;", value=token), current=token))
        elif token == "(":
            stack.append(token)
            steps.append(_step(len(steps) + 1, "push", "左括号入栈", "左括号作为边界入栈。", stack, input_items=tokens, output_items=output, action=Action(type="push", description="push('(');", value=token), current=token))
        elif token == ")":
            while stack and stack[-1] != "(":
                output.append(stack.pop())
            if stack:
                stack.pop()
            steps.append(_step(len(steps) + 1, "pop", "弹出到左括号", "右括号触发弹出运算符。", stack, input_items=tokens, output_items=output, action=Action(type="pop", description="pop until '(';"), current=token))
        else:
            while stack and stack[-1] != "(" and priority.get(stack[-1], 0) >= priority.get(token, 0):
                output.append(stack.pop())
            stack.append(token)
            steps.append(_step(len(steps) + 1, "push", "处理运算符", f"根据优先级处理 {token}，再入栈。", stack, input_items=tokens, output_items=output, action=Action(type="push", description="push(operator);", value=token), current=token))
    while stack:
        output.append(stack.pop())
        steps.append(_step(len(steps) + 1, "pop", "弹出剩余运算符", "扫描结束，栈中运算符依次输出。", stack, input_items=tokens, output_items=output, action=Action(type="pop", description="output pop();")))
    return _trace(request, "中缀表达式转后缀演示", steps, " ".join(output), "O(n)", "O(n)")


def _postfix_evaluation(request: OperationRequest) -> VisualizationTrace:
    tokens = _as_tokens(request, ["3", "5", "2", "*", "+"])
    stack: list[int] = []
    steps = [_step(1, "init", "开始求后缀表达式", "数字入栈，遇到运算符弹出两个操作数。", stack, input_items=tokens)]
    for token in tokens:
        token = str(token)
        if token.lstrip("-").isdigit():
            stack.append(int(token))
            steps.append(_step(len(steps) + 1, "push", "操作数入栈", f"{token} 入栈。", stack, input_items=tokens, action=Action(type="push", description="push(number);", value=token), current=token))
        else:
            b = stack.pop()
            a = stack.pop()
            value = _apply_operator(a, b, token)
            stack.append(value)
            steps.append(_step(len(steps) + 1, "pop", "弹出并计算", f"弹出 {a} 和 {b}，计算 {a} {token} {b} = {value}，结果入栈。", stack, input_items=tokens, action=Action(type="pop", description="b = pop(); a = pop(); push(a op b);", value=value), current=token))
    return _trace(request, "后缀表达式求值演示", steps, str(stack[-1]), "O(n)", "O(n)")


def _prefix_evaluation(request: OperationRequest) -> VisualizationTrace:
    tokens = _as_tokens(request, ["+", "3", "*", "5", "2"])
    stack: list[int] = []
    steps = [_step(1, "init", "开始求前缀表达式", "从右向左扫描，数字入栈，运算符弹出两个操作数。", stack, input_items=tokens)]
    for token in reversed(tokens):
        token = str(token)
        if token.lstrip("-").isdigit():
            stack.append(int(token))
            steps.append(_step(len(steps) + 1, "push", "操作数入栈", f"{token} 入栈。", stack, input_items=tokens, action=Action(type="push", description="push(number);", value=token), current=token))
        else:
            a = stack.pop()
            b = stack.pop()
            value = _apply_operator(a, b, token)
            stack.append(value)
            steps.append(_step(len(steps) + 1, "pop", "弹出并计算", f"弹出 {a} 和 {b}，计算 {a} {token} {b} = {value}。", stack, input_items=tokens, action=Action(type="pop", description="a = pop(); b = pop(); push(a op b);", value=value), current=token))
    return _trace(request, "前缀表达式求值演示", steps, str(stack[-1]), "O(n)", "O(n)")


def _expression_evaluation(request: OperationRequest) -> VisualizationTrace:
    infix_request = request.model_copy(update={"params": request.params.model_copy(update={"values": _as_tokens(request, ["3", "+", "5", "*", "2"])})})
    trace = _infix_to_postfix(infix_request)
    postfix = trace.summary.result.split()
    eval_request = request.model_copy(update={"params": request.params.model_copy(update={"values": postfix})})
    eval_trace = _postfix_evaluation(eval_request)
    steps = trace.steps + [
        _step(len(trace.steps) + 1, "switch", "切换到后缀求值", "先得到后缀表达式，再用操作数栈求值。", [], input_items=postfix)
    ] + [
        step.model_copy(update={"step_id": len(trace.steps) + 1 + index})
        for index, step in enumerate(eval_trace.steps, start=1)
    ]
    return _trace(request, "表达式求值演示", steps, eval_trace.summary.result, "O(n)", "O(n)")


def _apply_operator(a: int, b: int, op: str) -> int:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return int(a / b)
    raise ValueError(f"不支持的运算符：{op}")


def _call_stack(request: OperationRequest) -> VisualizationTrace:
    frames = _as_tokens(request, ["main()", "sum(3)", "sum(2)", "sum(1)"])
    stack: list[Any] = []
    steps = [_step(1, "init", "函数调用开始", "每次函数调用都会压入一个活动记录。", stack, input_items=frames)]
    for frame in frames:
        stack.append(frame)
        steps.append(_step(len(steps) + 1, "push", "调用入栈", f"调用 {frame}，压入调用栈。", stack, action=Action(type="push", description="push(call frame);", value=frame)))
    while stack:
        frame = stack.pop()
        steps.append(_step(len(steps) + 1, "pop", "返回出栈", f"{frame} 执行完毕，弹出调用栈。", stack, action=Action(type="pop", description="return; pop frame;", value=frame)))
    return _trace(request, "函数调用栈演示", steps, "调用栈清空", "O(n)", "O(n)")


def _recursion_trace(request: OperationRequest) -> VisualizationTrace:
    n = int(request.params.value or (request.initial_state.data[0] if request.initial_state.data else 4))
    frames = [f"f({i})" for i in range(n, 0, -1)]
    new_request = request.model_copy(update={"initial_state": request.initial_state.model_copy(update={"data": frames})})
    return _call_stack(new_request).model_copy(update={"title": "递归调用过程演示", "operation": request.operation})


def _hanoi_recursive(request: OperationRequest) -> VisualizationTrace:
    n = int(request.params.value or (request.initial_state.data[0] if request.initial_state.data else 3))
    stacks = {"A": list(range(n, 0, -1)), "B": [], "C": []}
    steps = [_step(1, "init", "汉诺塔初始状态", f"{n} 个盘子从 A 移到 C，B 作为辅助柱。", stacks)]

    def move(count: int, src: str, aux: str, dst: str) -> None:
        if count == 0:
            return
        move(count - 1, src, dst, aux)
        disk = stacks[src].pop()
        stacks[dst].append(disk)
        steps.append(_step(len(steps) + 1, "move", "移动盘子", f"移动盘 {disk}: {src} -> {dst}。", stacks, action=Action(type="move", description=f"move({disk}, {src}, {dst});", value=disk)))
        move(count - 1, aux, src, dst)

    move(n, "A", "B", "C")
    return _trace(request, "汉诺塔递归演示", steps, str(stacks), "O(2^n)", "O(n)")


def _hanoi_iterative(request: OperationRequest) -> VisualizationTrace:
    trace = _hanoi_recursive(request)
    return trace.model_copy(update={"title": "汉诺塔非递归栈模拟演示", "operation": request.operation})


def _maze_backtracking(request: OperationRequest) -> VisualizationTrace:
    path = _as_tokens(request, ["(0,0)", "(0,1)", "(1,1)", "(1,2)", "(2,2)"])
    dead = request.initial_state.metadata.get("dead_end", "(1,2)")
    stack: list[Any] = []
    steps = [_step(1, "init", "迷宫回溯开始", "路径位置入栈；遇到死路就退栈。", stack, input_items=path)]
    for cell in path:
        stack.append(cell)
        steps.append(_step(len(steps) + 1, "push", "前进一步", f"走到 {cell}，位置入栈。", stack, action=Action(type="push", description="push(position);", value=cell)))
        if str(cell) == str(dead):
            popped = stack.pop()
            steps.append(_step(len(steps) + 1, "pop", "遇到死路回退", f"{popped} 是死路，弹出并回到上一个位置。", stack, action=Action(type="pop", description="pop dead end;", value=popped)))
    return _trace(request, "迷宫回溯演示", steps, _format_initial(stack), "O(mn)", "O(mn)")


def _dfs_iterative(request: OperationRequest) -> VisualizationTrace:
    graph = request.initial_state.metadata.get("graph") or {"A": ["B", "C"], "B": ["D"], "C": [], "D": []}
    start = str(request.params.value or request.params.target or request.initial_state.data[0] if request.initial_state.data else "A")
    stack = [start]
    visited: list[str] = []
    steps = [_step(1, "init", "非递归 DFS 开始", "用栈保存待访问顶点。", stack, output_items=visited)]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.append(node)
        steps.append(_step(len(steps) + 1, "visit", "访问顶点", f"弹出并访问 {node}。", stack, output_items=visited, action=Action(type="visit", description="v = pop(); visit(v);", value=node)))
        for nxt in reversed(list(graph.get(node, []))):
            if nxt not in visited:
                stack.append(nxt)
        steps.append(_step(len(steps) + 1, "push", "邻接点入栈", f"把 {node} 的未访问邻接点入栈。", stack, output_items=visited, action=Action(type="push", description="push unvisited neighbors;")))
    return _trace(request, "非递归 DFS 演示", steps, " -> ".join(visited), "O(V+E)", "O(V)")


def _tree_values(request: OperationRequest) -> list[Any]:
    return _as_tokens(request, ["A", "B", "C", "D", "E", "F"])


def _tree_preorder(request: OperationRequest) -> VisualizationTrace:
    values = _tree_values(request)
    stack = [0]
    order: list[Any] = []
    steps = [_step(1, "init", "非递归先序遍历", "栈中保存待访问结点下标。", stack, input_items=values, output_items=order)]
    while stack:
        i = stack.pop()
        if i >= len(values) or values[i] is None:
            continue
        order.append(values[i])
        steps.append(_step(len(steps) + 1, "visit", "访问根结点", f"访问 {values[i]}。", stack, input_items=values, output_items=order, action=Action(type="visit", description="visit(node);", value=values[i])))
        stack.append(2 * i + 2)
        stack.append(2 * i + 1)
    return _trace(request, "二叉树先序非递归遍历演示", steps, " -> ".join(map(str, order)), "O(n)", "O(n)")


def _tree_inorder(request: OperationRequest) -> VisualizationTrace:
    values = _tree_values(request)
    stack: list[int] = []
    order: list[Any] = []
    i = 0
    steps = [_step(1, "init", "非递归中序遍历", "沿左链入栈，再访问并转向右子树。", stack, input_items=values, output_items=order)]
    while stack or i < len(values):
        while i < len(values) and values[i] is not None:
            stack.append(i)
            steps.append(_step(len(steps) + 1, "push", "沿左链入栈", f"{values[i]} 入栈。", stack, input_items=values, output_items=order, action=Action(type="push", description="push(node);", value=values[i])))
            i = 2 * i + 1
        if not stack:
            break
        i = stack.pop()
        order.append(values[i])
        steps.append(_step(len(steps) + 1, "visit", "弹出并访问", f"访问 {values[i]}。", stack, input_items=values, output_items=order, action=Action(type="pop", description="node = pop(); visit(node);", value=values[i])))
        i = 2 * i + 2
    return _trace(request, "二叉树中序非递归遍历演示", steps, " -> ".join(map(str, order)), "O(n)", "O(n)")


def _tree_postorder(request: OperationRequest) -> VisualizationTrace:
    values = _tree_values(request)
    stack = [(0, False)]
    order: list[Any] = []
    steps = [_step(1, "init", "非递归后序遍历", "使用标记位区分第一次到达和回退访问。", stack, input_items=values, output_items=order)]
    while stack:
        i, visited = stack.pop()
        if i >= len(values) or values[i] is None:
            continue
        if visited:
            order.append(values[i])
            steps.append(_step(len(steps) + 1, "visit", "左右子树后访问根", f"访问 {values[i]}。", stack, input_items=values, output_items=order, action=Action(type="visit", description="visit after children;", value=values[i])))
        else:
            stack.append((i, True))
            stack.append((2 * i + 2, False))
            stack.append((2 * i + 1, False))
            steps.append(_step(len(steps) + 1, "push", "根结点带标记回栈", f"{values[i]} 暂不访问，等待左右子树完成。", stack, input_items=values, output_items=order, action=Action(type="push", description="push(node, visited=true);", value=values[i])))
    return _trace(request, "二叉树后序非递归遍历演示", steps, " -> ".join(map(str, order)), "O(n)", "O(n)")


def _browser_history(request: OperationRequest) -> VisualizationTrace:
    pages = _as_tokens(request, ["home", "course", "stack", "queue"])
    back: list[Any] = []
    forward: list[Any] = []
    current = pages[0]
    steps = [_step(1, "init", "浏览器历史开始", f"当前页：{current}", {"back": back, "forward": forward}, current=current)]
    for page in pages[1:]:
        back.append(current)
        current = page
        forward.clear()
        steps.append(_step(len(steps) + 1, "push", "访问新页面", f"访问 {page}，旧页面进入后退栈。", {"back": back, "forward": forward}, action=Action(type="push", description="back.push(current);", value=page), current=current))
    if back:
        forward.append(current)
        current = back.pop()
        steps.append(_step(len(steps) + 1, "pop", "点击后退", "当前页进前进栈，后退栈弹出为当前页。", {"back": back, "forward": forward}, action=Action(type="pop", description="current = back.pop();"), current=current))
    return _trace(request, "浏览器前进后退演示", steps, str(current), "O(1)/次", "O(n)")


def _undo_redo(request: OperationRequest) -> VisualizationTrace:
    ops = _as_tokens(request, ["type A", "type B", "delete B"])
    undo: list[Any] = []
    redo: list[Any] = []
    steps = [_step(1, "init", "撤销重做开始", "新操作进入撤销栈，重做栈清空。", {"undo": undo, "redo": redo})]
    for op in ops:
        undo.append(op)
        redo.clear()
        steps.append(_step(len(steps) + 1, "push", "执行操作", f"执行 {op}，压入 undo 栈。", {"undo": undo, "redo": redo}, action=Action(type="push", description="undo.push(operation);", value=op)))
    if undo:
        redo.append(undo.pop())
        steps.append(_step(len(steps) + 1, "pop", "撤销一次", "undo 弹出，进入 redo 栈。", {"undo": undo, "redo": redo}, action=Action(type="pop", description="redo.push(undo.pop());")))
    return _trace(request, "撤销/重做演示", steps, f"undo={undo}, redo={redo}", "O(1)/次", "O(n)")


def _tag_matching(request: OperationRequest) -> VisualizationTrace:
    tags = _as_tokens(request, ["<html>", "<body>", "</body>", "</html>"])
    stack: list[str] = []
    steps = [_step(1, "init", "标签匹配开始", "开始标签入栈，结束标签与栈顶匹配。", stack, input_items=tags)]
    ok = True
    for tag in tags:
        tag = str(tag)
        if not tag.startswith("</"):
            stack.append(tag)
            steps.append(_step(len(steps) + 1, "push", "开始标签入栈", f"{tag} 入栈。", stack, input_items=tags, action=Action(type="push", description="push(openTag);", value=tag)))
        else:
            expected = "<" + tag[2:]
            if not stack or stack[-1] != expected:
                ok = False
                steps.append(_step(len(steps) + 1, "compare", "标签不匹配", f"{tag} 与栈顶不匹配。", stack, input_items=tags, action=Action(type="compare", description="close tag mismatch;", value=tag)))
                break
            stack.pop()
            steps.append(_step(len(steps) + 1, "pop", "标签匹配出栈", f"{expected} 与 {tag} 匹配。", stack, input_items=tags, action=Action(type="pop", description="pop openTag;", value=tag)))
    return _trace(request, "HTML/XML 标签匹配演示", steps, "匹配成功" if ok and not stack else "匹配失败", "O(n)", "O(n)")


def _syntax_parse_stack(request: OperationRequest) -> VisualizationTrace:
    tokens = _as_tokens(request, ["id", "+", "id"])
    stack = ["$"]
    steps = [_step(1, "init", "语法分析栈开始", "分析栈保存尚未归约的符号。", stack, input_items=tokens)]
    for token in tokens:
        stack.append(token)
        steps.append(_step(len(steps) + 1, "push", "移进符号", f"读入 {token}，移进分析栈。", stack, input_items=tokens, action=Action(type="push", description="shift token;", value=token)))
        if len(stack) >= 2 and stack[-1] == "id":
            stack[-1] = "E"
            steps.append(_step(len(steps) + 1, "assign", "归约", "id 归约为表达式 E。", stack, input_items=tokens, action=Action(type="assign", description="reduce id -> E;", value="E")))
    return _trace(request, "语法分析栈演示", steps, _format_initial(stack), "取决于文法", "O(n)")


def _next_greater_element(request: OperationRequest) -> VisualizationTrace:
    nums = [int(x) for x in _as_tokens(request, [2, 1, 2, 4, 3])]
    stack: list[int] = []
    answer = [-1] * len(nums)
    steps = [_step(1, "init", "单调栈开始", "栈中保存还没找到下一个更大元素的下标。", stack, input_items=nums, output_items=answer)]
    for i, num in enumerate(nums):
        while stack and nums[stack[-1]] < num:
            j = stack.pop()
            answer[j] = num
            steps.append(_step(len(steps) + 1, "pop", "找到下一个更大元素", f"{nums[j]} 的下一个更大元素是 {num}。", stack, input_items=nums, output_items=answer, action=Action(type="pop", description="answer[j] = nums[i];", value=num)))
        stack.append(i)
        steps.append(_step(len(steps) + 1, "push", "下标入栈", f"下标 {i} 入栈。", stack, input_items=nums, output_items=answer, action=Action(type="push", description="push(index);", value=i)))
    return _trace(request, "单调栈/下一个更大元素演示", steps, _format_initial(answer), "O(n)", "O(n)")


def _largest_rectangle(request: OperationRequest) -> VisualizationTrace:
    heights = [int(x) for x in _as_tokens(request, [2, 1, 5, 6, 2, 3])]
    nums = heights + [0]
    stack: list[int] = []
    best = 0
    steps = [_step(1, "init", "柱状图最大矩形开始", "维护递增高度下标栈。", stack, input_items=heights, output_items=[best])]
    for i, h in enumerate(nums):
        while stack and nums[stack[-1]] > h:
            top = stack.pop()
            width = i if not stack else i - stack[-1] - 1
            best = max(best, nums[top] * width)
            steps.append(_step(len(steps) + 1, "pop", "计算矩形面积", f"高度 {nums[top]}，宽度 {width}，当前最大面积 {best}。", stack, input_items=heights, output_items=[best], action=Action(type="pop", description="area = height * width;", value=best)))
        stack.append(i)
    steps.append(_step(len(steps) + 1, "done", "计算完成", f"最大矩形面积为 {best}。", stack, input_items=heights, output_items=[best]))
    return _trace(request, "柱状图最大矩形演示", steps, str(best), "O(n)", "O(n)")


def _daily_temperatures(request: OperationRequest) -> VisualizationTrace:
    temps = [int(x) for x in _as_tokens(request, [73, 74, 75, 71, 69, 72, 76])]
    stack: list[int] = []
    answer = [0] * len(temps)
    steps = [_step(1, "init", "每日温度开始", "单调栈保存等待升温的日期下标。", stack, input_items=temps, output_items=answer)]
    for i, temp in enumerate(temps):
        while stack and temps[stack[-1]] < temp:
            j = stack.pop()
            answer[j] = i - j
            steps.append(_step(len(steps) + 1, "pop", "找到更高温", f"第 {j} 天等待 {answer[j]} 天。", stack, input_items=temps, output_items=answer, action=Action(type="pop", description="answer[j] = i - j;", value=answer[j])))
        stack.append(i)
        steps.append(_step(len(steps) + 1, "push", "日期入栈", f"第 {i} 天入栈。", stack, input_items=temps, output_items=answer, action=Action(type="push", description="push(dayIndex);", value=i)))
    return _trace(request, "每日温度演示", steps, _format_initial(answer), "O(n)", "O(n)")


def _stack_sort(request: OperationRequest) -> VisualizationTrace:
    source = [int(x) for x in _as_tokens(request, [3, 1, 4, 2])]
    aux: list[int] = []
    steps = [_step(1, "init", "栈排序开始", "用辅助栈保持有序。", {"source": source, "aux": aux})]
    while source:
        x = source.pop()
        while aux and aux[-1] > x:
            source.append(aux.pop())
        aux.append(x)
        steps.append(_step(len(steps) + 1, "push", "插入辅助栈", f"把 {x} 插入到辅助栈的合适位置。", {"source": source, "aux": aux}, action=Action(type="push", description="insert into auxiliary stack;", value=x)))
    return _trace(request, "栈排序演示", steps, _format_initial(aux), "O(n^2)", "O(n)")


def _two_stacks_queue(request: OperationRequest) -> VisualizationTrace:
    values = _as_tokens(request, [1, 2, 3])
    in_stack: list[Any] = []
    out_stack: list[Any] = []
    steps = [_step(1, "init", "两个栈实现队列", "入队进 in 栈，出队从 out 栈弹出。", {"in": in_stack, "out": out_stack})]
    for value in values:
        in_stack.append(value)
        steps.append(_step(len(steps) + 1, "push", "入队", f"{value} 压入 in 栈。", {"in": in_stack, "out": out_stack}, action=Action(type="push", description="in.push(x);", value=value)))
    while in_stack:
        out_stack.append(in_stack.pop())
    steps.append(_step(len(steps) + 1, "move", "倒栈", "out 为空时，把 in 栈全部倒入 out 栈。", {"in": in_stack, "out": out_stack}, action=Action(type="move", description="out.push(in.pop());")))
    if out_stack:
        value = out_stack.pop()
        steps.append(_step(len(steps) + 1, "pop", "出队", f"弹出 {value}，符合先进先出。", {"in": in_stack, "out": out_stack}, action=Action(type="pop", description="return out.pop();", value=value)))
    return _trace(request, "两个栈实现队列演示", steps, f"in={in_stack}, out={out_stack}", "均摊 O(1)", "O(n)")


def _reverse_stack(request: OperationRequest) -> VisualizationTrace:
    source = _as_tokens(request, [1, 2, 3, 4])
    target: list[Any] = []
    steps = [_step(1, "init", "栈逆序开始", "不断弹出源栈并压入目标栈。", {"source": source, "target": target})]
    while source:
        value = source.pop()
        target.append(value)
        steps.append(_step(len(steps) + 1, "pop", "弹出并压入目标栈", f"{value} 从 source 到 target。", {"source": source, "target": target}, action=Action(type="pop", description="target.push(source.pop());", value=value)))
    return _trace(request, "栈逆序演示", steps, _format_initial(target), "O(n)", "O(n)")


def _train_rearrangement(request: OperationRequest) -> VisualizationTrace:
    incoming = deque(_as_tokens(request, [1, 2, 3, 4, 5]))
    target = list(request.params.values or request.initial_state.metadata.get("target_order") or [3, 2, 1, 5, 4])
    station: list[Any] = []
    output: list[Any] = []
    steps = [_step(1, "init", "火车调度开始", "进站栈模拟临时调度轨。", {"station": station}, input_items=list(incoming), output_items=output)]
    for want in target:
        while (not station or station[-1] != want) and incoming:
            value = incoming.popleft()
            station.append(value)
            steps.append(_step(len(steps) + 1, "push", "车厢进站", f"车厢 {value} 进入调度栈。", {"station": station}, input_items=list(incoming), output_items=output, action=Action(type="push", description="station.push(car);", value=value)))
        if station and station[-1] == want:
            output.append(station.pop())
            steps.append(_step(len(steps) + 1, "pop", "车厢出站", f"车厢 {want} 出站。", {"station": station}, input_items=list(incoming), output_items=output, action=Action(type="pop", description="output.push(station.pop());", value=want)))
    ok = output == target
    return _trace(request, "栈模拟火车调度演示", steps, "可行" if ok else "不可行", "O(n)", "O(n)")


def _pop_sequence_validation(request: OperationRequest) -> VisualizationTrace:
    push_seq = list(request.initial_state.data or [1, 2, 3, 4, 5])
    pop_seq = list(request.params.values or request.initial_state.metadata.get("pop_sequence") or [4, 5, 3, 2, 1])
    stack: list[Any] = []
    output: list[Any] = []
    push_index = 0
    steps = [_step(1, "init", "出栈序列合法性检查", "按入栈序列模拟，能匹配目标出栈序列则合法。", stack, input_items=push_seq, output_items=output)]
    for want in pop_seq:
        while (not stack or stack[-1] != want) and push_index < len(push_seq):
            stack.append(push_seq[push_index])
            steps.append(_step(len(steps) + 1, "push", "按序入栈", f"{push_seq[push_index]} 入栈。", stack, input_items=push_seq, output_items=output, action=Action(type="push", description="push(next);", value=push_seq[push_index])))
            push_index += 1
        if stack and stack[-1] == want:
            output.append(stack.pop())
            steps.append(_step(len(steps) + 1, "pop", "匹配目标出栈", f"{want} 出栈。", stack, input_items=push_seq, output_items=output, action=Action(type="pop", description="pop matches target;", value=want)))
    ok = output == pop_seq
    return _trace(request, "判断出栈序列是否合法演示", steps, "合法" if ok else "不合法", "O(n)", "O(n)")
