# demo1_serial.py：串行 —— 一个人排队做 3 件事
import time


def read(name):
    time.sleep(1)               # 假装读一个文件要 1 秒
    return name + " 读完了"


# 基线：3 个任务串行 = 3 秒；demo2 用并发把同一件事压到 1 秒左右。
start = time.time()
results = []
for name in ["a.txt", "b.txt", "c.txt"]:
    results.append(read(name))  # 做完一件，才做下一件

print(results)
print(f"总耗时: {time.time() - start:.1f} 秒")
