"""
PPT 生成工具（工具型 skill）

被 LLM 调用时：
1. 接收标题 + 报告内容（markdown）
2. 用 LLM 把报告拆成幻灯片 HTML（基于 guizang-ppt-skill 的模板布局）
3. 填进 template.html 的 <!-- SLIDES_HERE --> 位置
4. 输出完整 HTML 到 outputs/，返回访问 URL

这样研究报告完成后，用户说"生成PPT"，LLM 就能真正调用此工具生成文件。
"""
import asyncio
import logging
import os
import time
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_template_path() -> Path:
    """获取 guizang-ppt-skill 的模板路径。"""
    # custom_skills 上两级 = 项目根，再 skills/guizang-ppt-skill/assets/template.html
    root = Path(__file__).resolve().parents[1]  # custom_skills 的父级 = 项目根
    return root / "skills" / "guizang-ppt-skill" / "assets" / "template.html"


def _get_layouts_reference() -> str:
    """读取 layouts.md 作为 LLM 生成幻灯片的参考。"""
    root = Path(__file__).resolve().parents[1]
    layouts_path = root / "skills" / "guizang-ppt-skill" / "references" / "layouts.md"
    try:
        return layouts_path.read_text(encoding="utf-8")[:8000]  # 截断避免过长
    except Exception:
        return ""


async def _generate_slides_html(title: str, content: str, style: str = "magazine") -> str:
    """用 LLM 把报告内容转成幻灯片 HTML。"""
    from gpt_researcher.config.config import Config
    from gpt_researcher.utils.llm import create_chat_completion

    cfg = Config()
    layouts_ref = _get_layouts_reference()

    prompt = f"""你是 PPT 幻灯片生成专家。请把下面的报告内容转换成网页 PPT 的幻灯片 HTML。

要求：
1. 生成 8-15 页幻灯片，每页是一个 <section class="slide ...">...</section> 代码块
2. 第一页必须是 Hero 封面页（Layout 1，用 hero dark），标题用：{title}
3. 中间页用不同布局（Layout 3 纯文字、Layout 4 标题+正文、Layout 5 数据统计等）
4. 最后一页用收束页（金句或行动建议）
5. 严格使用以下布局参考里的 class 名和结构，不要发明新 class：

{layouts_ref}

6. 每页交替使用 light/dark 主题（封面和章节页用 dark/hero，内容页用 light）
7. 内容要精炼，每页只讲一个要点，不要堆砌大段文字
8. 所有元素加 data-anim 属性以启用入场动画

**严格输出要求**：
- 绝对不要任何思考过程、解释、前言后语、markdown 代码块标记
- 只输出纯 HTML，从第一个 <section 开始，到最后一个 </section> 结束
- 不要 ```html 这种围栏标记
- 不要 "Here is the presentation" 这种说明文字

报告内容：
{content[:6000]}
"""

    response = await create_chat_completion(
        model=cfg.smart_llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        llm_provider=cfg.smart_llm_provider,
        llm_kwargs=cfg.llm_kwargs,
    )
    return response


@tool
async def generate_ppt(title: str, content: str) -> str:
    """生成网页 PPT（横向翻页的 HTML 演示文稿）并写入 outputs/ 目录。

    **重要**：调用此工具会**真的生成一个可访问的 HTML 文件**，不需要再问用户确认。
    当用户要求生成 PPT / 幻灯片 / 演示文稿 / slide / deck 时，**直接调用本工具**，
    把报告标题作为 title，整个报告内容作为 content 传入即可。

    参数：
    - title: PPT 标题（如"内衣品牌调研报告"）。必填。
    - content: 要做成 PPT 的内容（研究报告正文、文章、大纲等，markdown 格式）。必填。

    返回：生成结果，包含可访问 URL（形如 /outputs/ppt_xxx.html）和页数。
    """
    try:
        # 1. 读取模板
        template_path = _get_template_path()
        if not template_path.exists():
            return f"错误：找不到 PPT 模板文件 {template_path}"

        template_html = template_path.read_text(encoding="utf-8")

        # 2. 用 LLM 生成幻灯片 HTML
        logger.info(f"[PPT] 开始生成幻灯片，标题: {title}")
        slides_html = await _generate_slides_html(title, content)

        # 严格清洗：用正则精确提取所有 <section class="slide ...">...</section> 块
        # 丢掉一切 LLM 额外输出的内容（thinking、解释、markdown 围栏等）
        import re
        slide_blocks = re.findall(
            r'<section class="slide[^"]*"[^>]*>.*?</section>',
            slides_html,
            re.DOTALL,
        )
        if slide_blocks:
            slides_html = "\n".join(slide_blocks)
            logger.info(f"[PPT] 正则提取到 {len(slide_blocks)} 个 slide 块")
        else:
            # 回退：粗暴剥 markdown 围栏
            slides_html = slides_html.strip()
            for fence in ["```html", "```"]:
                if slides_html.startswith(fence):
                    slides_html = slides_html[len(fence):]
                if slides_html.endswith(fence):
                    slides_html = slides_html[:-len(fence)]
            slides_html = slides_html.strip()
            logger.warning("[PPT] 正则未匹配到 slide 块，使用原始 LLM 输出")

        # 3. 填进模板
        final_html = template_html.replace("<!-- SLIDES_HERE -->", slides_html)

        # 替换标题占位符
        final_html = final_html.replace("[必填] 替换为 PPT 标题 · Deck Title", title)

        # 4. 输出到 outputs/
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        timestamp = int(time.time())
        safe_title = "".join(c for c in title if c.isalnum() or c in "-_")[:30]
        filename = f"ppt_{safe_title}_{timestamp}.html"
        filepath = outputs_dir / filename

        # 4.1 把模板依赖的本地资源打包到 outputs/ 下（file:// 也能正常加载）
        # motion.min.js 是模板通过 './assets/motion.min.js' 动态导入的
        assets_src = _get_template_path().parent  # skills/guizang-ppt-skill/assets/
        assets_dst = outputs_dir / "assets"
        assets_dst.mkdir(exist_ok=True)
        import shutil
        for f in assets_src.iterdir():
            if f.is_file():
                shutil.copy2(f, assets_dst / f.name)
        logger.info(f"[PPT] 打包资源到 {assets_dst}")

        # 4.2 把模板里 './assets/motion.min.js' 改成 'assets/motion.min.js'
        # 让相对路径既能从 file:// 解析（outputs/ 下找 assets/），也能从 http:// 解析
        final_html = final_html.replace("./assets/", "assets/")

        filepath.write_text(final_html, encoding="utf-8")

        # 5. 返回访问 URL
        url = f"/outputs/{filename}"
        slide_count = slides_html.count('<section class="slide')
        logger.info(f"[PPT] 生成成功: {filename} ({slide_count} 页)")

        return f"PPT 已生成成功！\n标题: {title}\n页数: {slide_count}\n访问地址: {url}\n文件: {filepath}"

    except Exception as e:
        logger.error(f"[PPT] 生成失败: {e}", exc_info=True)
        return f"PPT 生成失败: {e}"
