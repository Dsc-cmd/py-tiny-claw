# cmd/claw/main.py
# 第 6 章：挂载 read_file / write_file / bash / edit_file 四大原语，
# 用一次综合任务验证 Tool Registry 的分发能力。
# 运行方式（在 py-tiny-claw 目录下）: python -m cmd.claw.main
import logging
import os
import sys
from pathlib import Path

# PyCharm 直接运行脚本时，优先导入本章包，避免其他章节的源码根目录干扰。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.provider.openai import new_deepseek_provider
from internal.tools.bash import BashTool
from internal.tools.edit_file import EditFileTool
from internal.tools.read_file import ReadFileTool
from internal.tools.registry import new_registry
from internal.tools.write_file import WriteFileTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y/%m/%d %H:%M:%S")


def main():
    if not os.getenv("DEEPSEEK_API_KEY"):
        sys.exit("请先配置 DEEPSEEK_API_KEY 环境变量")

    # 把 Agent 的活动范围锁定在 workspace/ 子目录，避免模型生成的文件弄乱项目代码
    work_dir = PROJECT_ROOT / "workspace"
    work_dir.mkdir(exist_ok=True)
    work_dir = str(work_dir)

    llm_provider = new_deepseek_provider("deepseek-v4-flash")

    # 1. 创建注册中心，挂载四大原语
    registry = new_registry()
    registry.register(ReadFileTool(work_dir))
    registry.register(WriteFileTool(work_dir))
    registry.register(BashTool(work_dir))
    registry.register(EditFileTool(work_dir))

    # 2. 为节省 token，本实验关闭慢思考模式
    eng = AgentEngine(llm_provider, registry, work_dir, False)

    # 3. 一个需要四大原语协作的综合任务
    prompt = """
请按顺序完成以下操作，每一步都使用对应的工具：
1. 用 write_file 创建 calc.py，内容是一个函数 add(a, b) 返回 a + b，并在文件末尾 print(add(2, 3))
2. 用 bash 执行 python calc.py
3. 用 edit_file 把 return a + b 改成 return a * b
4. 用 read_file 读取 calc.py 确认修改成功
5. 再用 bash 执行一次 python calc.py，告诉我两次输出分别是多少
"""

    try:
        eng.run(prompt)
    except Exception as e:
        sys.exit(f"引擎运行崩溃: {e}")


if __name__ == "__main__":
    main()
