import os
import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport

# ==========================================
# 1. 初始化 FastMCP 应用
# ==========================================
# 注意：在 Serverless 环境中，通常建议将实例放在全局
mcp = FastMCP("weather", log_level="ERROR")

# ==========================================
# 2. 工具函数与 API 调用
# ==========================================

NWS_API_BASE = os.getenv("NWS_API_BASE", "https://api.weather.gov/")
USER_AGENT = os.getenv("USER_AGENT", "weather-mcp/1.0")


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API and return the JSON response."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
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


# ==========================================
# 3. MCP Tools 定义
# ==========================================

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


# ==========================================
# 4. Cloudflare Worker 入口 (关键修改)
# ==========================================

# 创建一个全局的 SSE 传输层
# 注意：在 Workers 中，我们不需要指定 port，而是处理 request
sse = SseServerTransport("/mcp/sse")


async def handle_request(request, env, context):
    """
    Cloudflare Worker 的标准入口函数。
    所有请求都会经过这里，并被转发给 MCP 服务器处理。
    """
    # 将 request 交给 mcp server 处理
    # mcp.server.run 会处理 SSE 连接和消息交换
    return await mcp.run(request)