import time
from fastmcp import FastMCP

mcp = FastMCP(name="slow")


@mcp.tool()
def slow_tool() -> str:
    time.sleep(5)
    return "done"


if __name__ == "__main__":
    try:
        mcp.run(show_banner=False)
    except TypeError:
        mcp.run()
