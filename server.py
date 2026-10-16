# server.py

def handle_request(user):
    print("收到请求")

    # TODO: 增加鉴权逻辑
    if user is None:
        print("Forbidden!")
        return

    print("请求处理成功")


handle_request(None)