import asyncio
import os
import json
import sys  # 需要导入 sys 来处理命令行参数
from typing import Optional, List
from contextlib import AsyncExitStack

from openai import OpenAI
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters, types  # 导入 types
from mcp.client.stdio import stdio_client

# 加载 .env 文件，确保 API Key 受到保护
load_dotenv()


class MCPClient:
    def __init__(self):
        """初始化 MCP 客户端"""
        self.exit_stack = AsyncExitStack()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")  # 读取 OpenAI API Key
        self.base_url = os.getenv("BASE_URL")  # 读取 BASE YRL
        self.model = os.getenv("MODEL")  # 读取 model
        if not self.openai_api_key:
            raise ValueError(
                "❌ 未找到 OpenAI API Key，请在 .env 文件中设置 OPENAI_API_KEY"
            )

        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        # 创建OpenAI client
        self.session: Optional[ClientSession] = None
        self.stdio_read = None  # 添加用于存储读取流的属性
        self.stdio_write = None  # 添加用于存储写入流的属性

    async def transform_json(self, json2_data):
        """
        将Claude Function calling参数格式转换为OpenAI Function calling参数格式，多余
        字段会被直接删除。

        :param json2_data: 一个可被解释为列表的 Python 对象（或已解析的
        :return: 转换后的新列表
        """
        result = []

        for item in json2_data:
            # 确保有 "type" 和 "function" 两个关键字
            if (
                not isinstance(item, dict)
                or "type" not in item
                or "function" not in item
            ):
                continue

            old_func = item["function"]

            # 确保 function 下有我们需要的子字段
            if (
                not isinstance(old_func, dict)
                or "name" not in old_func
                or "description" not in old_func
            ):
                continue

            # 处理新 function 字段
            new_func = {
                "name": old_func["name"],
                "description": old_func["description"],
                "parameters": {},
            }

            # 读取 input_schema 并转成 parameters
            if "input_schema" in old_func and isinstance(
                old_func["input_schema"], dict
            ):
                old_schema = old_func["input_schema"]

                # 新的 parameters 保留 type, properties, required
                new_func["parameters"]["type"] = old_schema.get(
                    "type", "object"
                )  # Default to object if not specified
                new_func["parameters"]["properties"] = old_schema.get(
                    "properties", {}
                )  # Default to empty dict
                # Handle required field if it exists
                if "required" in old_schema:
                    new_func["parameters"]["required"] = old_schema["required"]

            result.append({"type": "function", "function": new_func})

        return result

    async def connect_and_list_tools(self, server_script_path: str) -> List[types.Tool]:
        """
        连接到指定的 MCP 服务器并列出可用的工具。

        Args:
            server_script_path: MCP 服务器脚本的路径 (例如 'server.py' 或 'index.js')。

        Returns:
            一个包含可用工具对象的列表。

        Raises:
            ValueError: 如果服务器脚本路径无效或连接失败。
            Exception: 如果在连接或列出工具时发生其他错误。
        """
        if self.session:
            print("ℹ️ 已连接到服务器。")
            # 如果已有会话，直接列出工具
            try:
                response = await self.session.list_tools()
                print("✅ 成功列出工具:")
                for tool in response.tools:
                    print(f"  - {tool.name}: {tool.description}")
                return response.tools
            except Exception as e:
                print(f"❌ 列出工具时出错: {e}")
                raise

        print(f"🔌 正在尝试连接到服务器: {server_script_path}...")
        is_python = server_script_path.endswith(".py")
        is_js = server_script_path.endswith(".js")
        # 可以根据需要扩展支持其他脚本类型，例如 .jar
        # is_java = server_script_path.endswith('.jar')

        if not (is_python or is_js):
            raise ValueError("❌ 服务器脚本必须是 .py 或 .js 文件")

        command = "python" if is_python else "node"
        # 如果支持 Java: command = "java" if is_java else command
        args = [server_script_path]
        # 如果支持 Java: args = ["-jar", server_script_path] if is_java else args

        server_params = StdioServerParameters(
            command=command, args=args, env=None  # 可以根据需要传递环境变量
        )

        try:
            # 使用 AsyncExitStack 管理 stdio_client 和 ClientSession 的生命周期
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio_read, self.stdio_write = stdio_transport

            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio_read, self.stdio_write)
            )

            # 初始化连接
            await self.session.initialize()
            print("✅ 服务器连接初始化成功。")

            # 列出可用工具
            response = await self.session.list_tools()
            tools = response.tools
            print("✅ 成功列出工具:")
            if tools:
                for tool in tools:
                    print(f"  - {tool.name}: {tool.description}")
            else:
                print("  🤔 服务器未提供任何工具。")
            return tools

        except FileNotFoundError:
            print(
                f"❌ 错误: 找不到命令 '{command}' 或服务器脚本 '{server_script_path}'。请确保命令已安装并在 PATH 中，且脚本路径正确。"
            )
            await self.cleanup()  # 尝试清理资源
            raise
        except Exception as e:
            print(f"❌ 连接到服务器或列出工具时出错: {e}")
            await self.cleanup()  # 尝试清理资源
            raise

    async def cleanup(self):
        """清理 MCP 连接和资源"""
        print("🧹 正在清理资源...")
        await self.exit_stack.aclose()
        self.session = None
        self.stdio_read = None
        self.stdio_write = None
        print("✅ 资源清理完毕。")


# --- 示例用法 ---
async def run_example():
    client = MCPClient()
    # 假设你的 MCP 服务器脚本名为 'mcp_server.py' 并且位于同一目录下
    # 或者你可以提供绝对/相对路径
    server_script = "rag_server.py"  # <--- 修改为你的服务器脚本路径

    # 检查服务器脚本是否存在 (可选但推荐)
    if not os.path.exists(server_script):
        print(f"⚠️ 警告: 服务器脚本 '{server_script}' 不存在。请确保路径正确。")
        # 你可以选择在这里退出或继续尝试连接
        # sys.exit(1)

    try:
        available_tools = await client.connect_and_list_tools(server_script)
        # 在这里可以根据 available_tools 做后续操作
        # 例如，如果需要调用某个工具:
        # if client.session and any(tool.name == 'desired_tool_name' for tool in available_tools):
        #     try:
        #         result = await client.session.call_tool('desired_tool_name', arguments={'arg1': 'value1'})
        #         print(f"调用工具结果: {result.content}")
        #     except Exception as e:
        #         print(f"调用工具时出错: {e}")

    except (ValueError, Exception) as e:
        print(f"程序执行出错: {e}")
    finally:
        await client.cleanup()


if __name__ == "__main__":
    # 注意：直接运行此脚本可能不会成功，因为它依赖于一个正在运行的 MCP 服务器。
    # 这里只是展示如何调用新添加的方法。
    # 你需要根据你的实际情况来集成和运行。
    # 例如，从另一个主程序中实例化 MCPClient 并调用 connect_and_list_tools。

    # 取消注释下面这行来运行示例 (确保 server_script 指向有效的服务器脚本)
    # asyncio.run(run_example())
    print(
        "ℹ️ MCPClient 类已更新，包含 connect_and_list_tools 方法。请在你的主程序中实例化并使用它。"
    )
    pass  # 防止直接运行时出错
