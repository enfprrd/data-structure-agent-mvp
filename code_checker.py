from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEMP_C_PATH = BASE_DIR / "temp.c"
C_CODE_BLOCK_PATTERN = re.compile(r"```(?:c|C)\s*(.*?)```", re.DOTALL)


@dataclass
class CodeCheckResult:
    has_code: bool
    compiled: bool
    ran: bool
    summary: str
    needs_fix: bool = False


def extract_c_code(answer: str | None) -> str | None:
    if not answer:
        return None

    matches = C_CODE_BLOCK_PATTERN.findall(answer)
    if not matches:
        return None

    code = matches[-1].strip()
    return code or None


def _text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def check_c_code_in_answer(answer: str | None) -> CodeCheckResult:
    code = extract_c_code(answer)
    if not code:
        return CodeCheckResult(
            has_code=False,
            compiled=False,
            ran=False,
            summary="本次回答未检测到 C 语言代码块，因此未执行编译测试。",
        )

    TEMP_C_PATH.write_text(code, encoding="utf-8")

    gcc_path = shutil.which("gcc")
    if not gcc_path:
        return CodeCheckResult(
            has_code=True,
            compiled=False,
            ran=False,
            summary=(
                f"已提取 C 代码并保存到 `{TEMP_C_PATH.name}`，"
                "但当前环境未找到 gcc，无法自动编译。"
            ),
        )

    try:
        with tempfile.TemporaryDirectory(prefix="ds_agent_c_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            compile_c_path = temp_dir_path / "temp.c"
            compile_exe_path = temp_dir_path / "temp_program.exe"
            compile_c_path.write_text(code, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    gcc_path,
                    str(compile_c_path),
                    "-std=c99",
                    "-Wall",
                    "-Wextra",
                    "-o",
                    str(compile_exe_path),
                ],
                cwd=temp_dir_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )

            if compile_result.returncode != 0:
                message = _text(compile_result.stderr) or _text(compile_result.stdout)
                return CodeCheckResult(
                    has_code=True,
                    compiled=False,
                    ran=False,
                    summary=(
                        f"已保存代码到 `{TEMP_C_PATH.name}`，但 gcc 编译失败。\n\n"
                        f"```text\n{message}\n```"
                    ),
                    needs_fix=True,
                )

            run_result = subprocess.run(
                [str(compile_exe_path)],
                cwd=temp_dir_path,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )

            if run_result.returncode != 0:
                message = _text(run_result.stderr) or _text(run_result.stdout)
                return CodeCheckResult(
                    has_code=True,
                    compiled=True,
                    ran=False,
                    summary=(
                        f"已保存代码到 `{TEMP_C_PATH.name}`，编译通过，但运行失败。\n\n"
                        f"```text\n{message}\n```"
                    ),
                    needs_fix=True,
                )

            output = _text(run_result.stdout)
    except subprocess.TimeoutExpired as exc:
        return CodeCheckResult(
            has_code=True,
            compiled=False,
            ran=False,
            summary=f"已保存代码到 `{TEMP_C_PATH.name}`，但编译或运行超时：{exc}",
            needs_fix=True,
        )
    except OSError as exc:
        return CodeCheckResult(
            has_code=True,
            compiled=False,
            ran=False,
            summary=f"已保存代码到 `{TEMP_C_PATH.name}`，但调用 gcc 或运行程序失败：{exc}",
            needs_fix=True,
        )

    summary = f"已保存代码到 `{TEMP_C_PATH.name}`，gcc 编译通过，基础运行测试通过。"
    if output:
        summary += f"\n\n程序输出：\n\n```text\n{output[:2000]}\n```"

    return CodeCheckResult(
        has_code=True,
        compiled=True,
        ran=True,
        summary=summary,
    )
