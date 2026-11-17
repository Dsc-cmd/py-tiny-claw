# demo3_order.py：谁先做完谁先写 —— 结果顺序会乱
import random
import time
from concurrent.futures import ThreadPoolExecutor

# 反例：共享列表 + "做完就 append"，顺序由线程调度决定。
# 这正是 engine 改用"预分配槽位"的原因——顺序必须等于模型的请求顺序。
results = []


def read(name):
    time.sleep(random.random())  # 每个文件的耗时不一样
    results.append(name)         # 做完就往共享列表末尾追加


with ThreadPoolExecutor(max_workers=3) as executor:
    for n in ["a.txt", "b.txt", "c.txt"]:
        executor.submit(read, n)

print(results)   # 每次运行顺序都可能不同！
