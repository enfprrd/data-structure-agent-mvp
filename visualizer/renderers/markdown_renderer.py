from __future__ import annotations

from visualizer.protocol import VisualizationTrace


def render_trace_markdown(trace: VisualizationTrace) -> str:
    lines = [f"# {trace.title}", "", f"- 初始：{trace.summary.initial}", f"- 结果：{trace.summary.result}", ""]
    for step in trace.steps:
        lines.append(f"## {step.step_id}. {step.title}")
        lines.append(step.description)
        for action in step.actions:
            lines.append(f"- {action.type}: {action.description}")
        lines.append("")
    return "\n".join(lines)
