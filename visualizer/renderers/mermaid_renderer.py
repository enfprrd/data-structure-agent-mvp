from __future__ import annotations

from visualizer.protocol import Step


def render_linked_mermaid(step: Step) -> str:
    state = step.state
    if state.get("kind") != "linked":
        return "flowchart LR\n  empty[No linked state]"
    lines = ["flowchart LR"]
    for node in state.get("nodes", []):
        node_id = str(node.get("id"))
        label = str(node.get("label"))
        lines.append(f"  {node_id}[{label}]")
    for edge in state.get("edges", []):
        src = str(edge.get("from")).replace("NULL", "null_node")
        dst = str(edge.get("to")).replace("NULL", "null_node")
        if dst == "null_node":
            lines.append("  null_node[NULL]")
        lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)
