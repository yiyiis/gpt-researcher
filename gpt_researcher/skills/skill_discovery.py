"""
指令型 Skill 发现与加载（Superpowers 式 progressive disclosure）

机制：
1. 扫描 skills_dir/*/SKILL.md
2. 解析 frontmatter（name + description），构建索引
3. 研究时用 LLM 从 description 语义匹配出最相关的 skill（progressive disclosure）
4. 命中的 skill 才按需读取正文，注入 system prompt 作为方法论指导

frontmatter 解析为零依赖正则实现（仿 superpowers .opencode/plugins/superpowers.js）。
"""
import logging
import os
import re
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# frontmatter 正则：匹配 ---\n...\n---\n<body>
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class SkillInfo:
    """一个指令型 skill 的元信息（不含正文，避免占用内存）。"""

    def __init__(self, name: str, description: str, skill_dir: Path, skill_md_path: Path):
        self.name = name
        self.description = description
        self.skill_dir = skill_dir
        self.skill_md_path = skill_md_path

    def get_body(self) -> str:
        """按需读取 SKILL.md 正文（progressive disclosure，剥离 frontmatter）。"""
        try:
            content = self.skill_md_path.read_text(encoding="utf-8")
            match = _FRONTMATTER_RE.match(content)
            if match:
                return match.group(2).strip()
            return content.strip()
        except Exception as e:
            logger.error(f"[skills] 读取 {self.name} 正文失败: {e}")
            return ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "dir": self.skill_dir.name,
            "type": "instruction",
        }


def _parse_frontmatter(content: str) -> tuple[Dict[str, str], str]:
    """解析 YAML frontmatter（零依赖，只处理简单 key: value）。返回 (frontmatter, body)。"""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content.strip()

    fm_text, body = match.group(1), match.group(2)
    fm: Dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # 去掉引号
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        if key:
            fm[key] = value
    return fm, body.strip()


def get_skills_dir() -> Path:
    """获取 skill 目录（来自环境变量 SKILLS_DIR，默认 'skills'）。"""
    skills_dir = os.getenv("SKILLS_DIR", "skills")
    p = Path(skills_dir)
    if not p.is_absolute():
        # 相对路径基于项目根（本文件上 3 级 = 项目根）
        root = Path(__file__).resolve().parents[2]
        p = root / skills_dir
    return p


# 模块级缓存：避免重复扫描 IO
_skills_cache: Optional[List[SkillInfo]] = None


def discover_skills(force_refresh: bool = False) -> List[SkillInfo]:
    """
    扫描 skills_dir 下的所有 skill（每个子目录含 SKILL.md）。

    Args:
        force_refresh: 强制刷新缓存

    Returns:
        List[SkillInfo]
    """
    global _skills_cache
    if _skills_cache is not None and not force_refresh:
        return _skills_cache

    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        logger.info(f"[skills] 目录不存在: {skills_dir}")
        _skills_cache = []
        return []

    skills: List[SkillInfo] = []
    for sub in sorted(skills_dir.iterdir()):
        if not sub.is_dir():
            continue
        skill_md = sub / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            fm, _ = _parse_frontmatter(content)
            name = fm.get("name", "").strip() or sub.name
            description = fm.get("description", "").strip()
            if not description:
                logger.warning(f"[skills] {sub.name}: SKILL.md 缺少 description，跳过")
                continue
            skills.append(SkillInfo(name, description, sub, skill_md))
            logger.info(f"[skills] ✓ 发现场skill: {name} ({sub.name})")
        except Exception as e:
            logger.error(f"[skills] ✗ 解析 {sub.name}/SKILL.md 失败: {e}")

    logger.info(f"[skills] 共发现 {len(skills)} 个指令型 skill")
    _skills_cache = skills
    return skills


def list_skills_info() -> List[Dict]:
    """返回所有 skill 的展示信息（供 API，不含正文）。"""
    return [s.to_dict() for s in discover_skills()]


def get_skill_body(name: str) -> str:
    """按需读取指定 skill 的正文（progressive disclosure）。"""
    for s in discover_skills():
        if s.name == name:
            return s.get_body()
    return ""


def delete_skill(skill_name: str) -> bool:
    """删除一个 skill 目录。返回是否删除成功。"""
    import shutil

    skills_dir = get_skills_dir()
    for s in discover_skills():
        if s.name == skill_name:
            target = s.skill_dir.resolve()
            # 安全：确保在 skills_dir 内
            if not str(target).startswith(str(skills_dir.resolve())):
                logger.error(f"[skills] 拒绝删除 skills_dir 之外的目录: {target}")
                return False
            shutil.rmtree(target, ignore_errors=True)
            # 刷新缓存
            global _skills_cache
            _skills_cache = None
            logger.info(f"[skills] 已删除 skill: {skill_name} ({target.name})")
            return True
    return False


async def find_relevant_skills(query: str, top_k: int = 3, cfg=None) -> List[str]:
    """
    用 LLM 从所有 skill 的 description 语义匹配出最相关的 skill 名。

    Args:
        query: 研究查询
        top_k: 最多返回几个 skill
        cfg: Config 对象（用于获取 LLM 配置）

    Returns:
        List[str]: 相关 skill 的 name 列表（可能为空）
    """
    skills = discover_skills()
    if not skills:
        return []
    if len(skills) <= top_k:
        # skill 很少时直接全返回
        return [s.name for s in skills]

    # 构造 LLM 选择 prompt（仿 MCP tool_selector 模式）
    skills_list = "\n".join(
        f"{i+1}. {s.name}: {s.description}" for i, s in enumerate(skills)
    )
    prompt = f"""You are selecting which methodology skills are most relevant to a research query.

RESEARCH QUERY: "{query}"

AVAILABLE SKILLS (name: description):
{skills_list}

Select up to {top_k} most relevant skills. Return ONLY a JSON array of skill names, e.g. ["skill-a", "skill-b"].
If none are relevant, return []. Consider the query's domain and each skill's description carefully."""

    try:
        if cfg is None:
            from ..config import Config
            cfg = Config()

        from ..utils.llm import create_chat_completion
        response = await create_chat_completion(
            model=cfg.strategic_llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200,
            llm_provider=cfg.strategic_llm_provider,
            llm_kwargs=cfg.llm_kwargs,
        )
        # 解析 JSON 数组
        import json
        match = re.search(r"\[.*?\]", response, re.DOTALL)
        if match:
            names = json.loads(match.group(0))
            valid_names = {s.name for s in skills}
            selected = [n for n in names if n in valid_names]
            logger.info(f"[skills] 语义匹配 skill: {selected} (query: {query[:40]})")
            return selected[:top_k]
    except Exception as e:
        logger.error(f"[skills] 语义匹配失败: {e}")

    # 失败时返回空（不注入，避免误用）
    return []


def build_skill_guidance(skill_names: List[str]) -> str:
    """
    把选中的 skill 正文拼成 system prompt 注入段。

    Returns:
        注入字符串（若 skill_names 为空返回空串）
    """
    if not skill_names:
        return ""

    parts = []
    for name in skill_names:
        body = get_skill_body(name)
        if body:
            parts.append(f'<SKILL name="{name}">\n{body}\n</SKILL>')

    if not parts:
        return ""

    return (
        "\n\n<SKILL_GUIDANCE>\n"
        "以下是适用于本次研究的方法论指导。请在研究和撰写报告时参考这些框架和方法：\n\n"
        + "\n\n".join(parts)
        + "\n</SKILL_GUIDANCE>"
    )
