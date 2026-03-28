import pydantic
from pydantic import BaseModel, Field

class User(BaseModel):
    name: str
    age: int
print("Pydantic version:", pydantic.__version__) 
u = User(name="Alice", age=30)
print(u.model_dump())  # 运行正常，输出 {'name': 'Alice', 'age': 30}
print(type(u))         # <class '__main__.User'>
print(hasattr(u, 'model_dump'))  # True

# import sys
# print("=== 调试环境信息 ===")
# print("Python 路径:", sys.executable)
# print("sys.path 前3项:", sys.path[:3])

# try:
#     import pydantic
#     print("Pydantic 版本:", pydantic.__version__)
# except Exception as e:
#     print("导入 pydantic 失败:", e)