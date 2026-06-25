"""
Custom Skill Loader — 从 custom_skills/ 目录自动加载用户自定义工具。

工作原理：
1. 扫描 custom_skills/ 下所有 .py 文件（不含 __init__.py）
2. 用 importlib 动态导入每个模块
3. 收集模块内被 @tool 装饰的函数（langchain_core.tools.tool）
4. 返回 LangChain Tool 列表，供 LLM bind_tools 自主调用

错误隔离：单个 skill 文件加载失败（语法错误、导入失败）不影响其他 skill。
"""
import importlib
import importlib.util
import logging
import os
from pathlib import Path
from typing import List, Any, Dict

logger = logging.getLogger(__name__)

# skill 目录（项目根下的 custom_skills/）
def _get_skills_dir() -> Path:
    # 本文件位于 gpt_researcher/skills/custom_loader.py
    # 项目根 = 上两级再上一级（gpt_researcher -> 项目根）
    root = Path(__file__).resolve().parents[2]  # gpt_researcher 的上一级 = 项目根
    return root / "custom_skills"


def _is_tool(obj: Any) -> bool:
    """判断一个对象是否是 LangChain @tool 装饰的工具。"""
    # @tool 装饰后生成 StructuredTool / BaseTool 实例：
    # - 类型名含 Tool
    # - 有 name、description、invoke 属性
    type_name = type(obj).__name__
    return (
        ("Tool" in type_name)
        and hasattr(obj, "name")
        and hasattr(obj, "description")
        and hasattr(obj, "invoke")
        and getattr(obj, "name", "") != ""
    )


def load_custom_skills() -> List[Any]:
    """
    扫描 custom_skills/ 目录，加载所有 @tool 工具。

    Returns:
        List of LangChain tool objects.
    """
    skills_dir = _get_skills_dir()
    if not skills_dir.exists():
        logger.info("[skills] custom_skills/ 目录不存在，跳过加载")
        return []

    tools: List[Any] = []
    skill_files = sorted(
        f for f in skills_dir.glob("*.py") if f.name != "__init__.py"
    )

    if not skill_files:
        logger.info("[skills] custom_skills/ 目录为空，无 skill 加载")
        return []

    logger.info(f"[skills] 发现 {len(skill_files)} 个 skill 文件，开始加载...")

    for skill_file in skill_files:
        module_name = f"custom_skills.{skill_file.stem}"
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, skill_file)
            if spec is None or spec.loader is None:
                logger.warning(f"[skills] 无法为 {skill_file.name} 创建模块规格")
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 收集模块内的 @tool 工具（排除从其他模块 import 进来的）
            file_tools = []
            seen_ids = set()
            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if not _is_tool(obj):
                    continue
                if id(obj) in seen_ids:
                    continue
                # StructuredTool 的底层函数：同步工具在 .func，异步工具在 .coroutine
                func = getattr(obj, "func", None) or getattr(obj, "coroutine", None)
                tool_module = getattr(func, "__module__", "") or getattr(obj, "__module__", "") or ""
                if not tool_module.startswith("custom_skills"):
                    logger.debug(f"[skills] 跳过非本模块工具 {getattr(obj,'name','?')} (module={tool_module})")
                    continue
                seen_ids.add(id(obj))
                file_tools.append(obj)

            if file_tools:
                tools.extend(file_tools)
                names = [t.name for t in file_tools]
                logger.info(f"[skills] ✓ {skill_file.name}: 加载了 {len(file_tools)} 个工具 {names}")
            else:
                logger.warning(f"[skills] {skill_file.name}: 未找到 @tool 装饰的函数")

        except Exception as e:
            logger.error(f"[skills] ✗ 加载 {skill_file.name} 失败: {e}", exc_info=True)
            # 错误隔离：继续加载其他 skill

    logger.info(f"[skills] 加载完成，共 {len(tools)} 个工具: {[t.name for t in tools]}")
    return tools


def list_custom_skills_info() -> List[Dict[str, str]]:
    """
    返回 skill 的展示信息（供 API 使用，不含可执行对象）。

    Returns:
        [{"name": ..., "description": ..., "file": ...}, ...]
    """
    tools = load_custom_skills()
    skills_dir = _get_skills_dir()
    result = []
    for t in tools:
        result.append({
            "name": t.name,
            "description": t.description.strip() if t.description else "",
            "file": _find_source_file(t, skills_dir),
        })
    return result


def _find_source_file(tool: Any, skills_dir: Path) -> str:
    """尝试找出 skill 所属的源文件名。"""
    func = getattr(tool, "func", None)
    module = getattr(func, "__module__", "") or getattr(tool, "__module__", "") or ""
    if module.startswith("custom_skills."):
        stem = module.replace("custom_skills.", "")
        return f"{stem}.py"
    return ""
