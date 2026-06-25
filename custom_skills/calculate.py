"""
示例 Skill：数学计算

把此文件作为模板，复制后修改即可创建自己的 skill。
约定：
1. 用 langchain_core.tools 的 @tool 装饰器定义工具函数
2. 函数 docstring 会作为"工具说明"告诉 LLM 何时该调用它（很重要，写清楚！）
3. 一个 .py 文件里可以定义多个 @tool 函数，都会被加载
4. 重启后端后生效
"""
from langchain_core.tools import tool


@tool
def calculate(expression: str) -> str:
    """计算一个数学表达式并返回结果。当需要执行数学计算时使用此工具。
    例如：calculate("2 + 3 * 4") 返回 "14"。
    支持 + - * / () 和基本数学运算。
    """
    import ast
    import operator
    try:
        node = ast.parse(expression, mode="eval").body
        ops = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow, ast.USub: operator.neg,
            ast.Mod: operator.mod,
        }
        def _eval(n):
            if isinstance(n, ast.Constant):
                return n.value
            if isinstance(n, ast.BinOp):
                return ops[type(n.op)](_eval(n.left), _eval(n.right))
            if isinstance(n, ast.UnaryOp):
                return ops[type(n.op)](_eval(n.operand))
            raise ValueError("不支持的表达式")
        return str(_eval(node))
    except Exception as e:
        return f"计算失败: {e}"
