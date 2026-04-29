import os
import asyncio
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport


mcp = FastMCP("weather", log_level="ERROR")

NWS_API_BASE = "https://api.weather.gov/"
USER_AGENT = "weather-mcp/1.0"

async def make_nws_request(url: str) -> dict[str, Any]|None:
    """Make a request to the NWS API and return the JSON response."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers,timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error making request to NWS API: {e}")
            return None
        



def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)



@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # Format the periods into a readable forecast
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
{period['name']}:
Temperature: {period['temperature']}°{period['temperatureUnit']}
Wind: {period['windSpeed']} {period['windDirection']}
Forecast: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)


if __name__ == "__main__":
    # 获取端口号，优先使用环境变量 PORT，默认使用 8000
    # Render, Railway, Heroku 等通常使用 PORT 环境变量
    port = int(os.environ.get("PORT", 8000))
    
    # 创建 SSE 传输层，监听指定端口
    # 注意：FastMCP 的 run() 方法如果传了 transport='sse'，它会自动处理
    # 但为了更灵活控制，我们这里直接启动 SSE 服务器
    
    # 方案 A: 使用 FastMCP 自带的 SSE 支持 (推荐)
    # 注意：FastMCP 的 run() 方法在 transport='sse' 时会自动绑定到端口
    # 如果 FastMCP 版本较新，可以直接用这种方式：
    
    print(f"Starting Weather MCP Server on port {port}...")
    
    # 这里我们使用 run() 方法，并指定 transport 为 sse
    # 这样会自动处理 HTTP 路由和 SSE 流
    mcp.run(transport='sse', port=port)
    
    # 如果上面的 run() 方法在特定版本下行为不同，可以使用下面的备用方案：
    # transport = SseServerTransport("/mcp", port=port)
    # mcp.run(transport=transport)