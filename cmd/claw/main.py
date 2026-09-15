import logging

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s",
                    dastefmt="%Y/%m/%d %H:%M:%S")

log=logging.getLogger(__name__)

def main():
    print("🚀 欢迎来到 py-tiny-claw 引擎启动序列")
    # TODD: 1. 初始化模型 Provider(大脑)
    # procider = ZhipuClaudeProvider(...)
    # TODD: 2. 初始化 Tool