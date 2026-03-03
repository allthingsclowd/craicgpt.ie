"""
content_pipeline/tools/weather_tool.py
========================================
LangChain tool for fetching current weather conditions.

TUTORIAL: Tools with External HTTP APIs
-----------------------------------------
This tool calls wttr.in — a free weather API that requires no API key.
It returns weather data as JSON, which we parse and include in our prompts.

The weather is used by the content agent to set the mood and opening context
for the main article — rainy Dublin mornings produce very different craic
than sunny ones. This demonstrates how real-world data shapes LLM outputs.

wttr.in JSON API docs: https://wttr.in/:help
"""

import json
import logging
import urllib.request
import urllib.error
from urllib.parse import quote

from langchain_core.tools import tool

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)


@tool
def get_weather(location: str = "") -> str:
    """
    Fetch the current weather conditions for the specified location (default: Dublin).
    Returns a JSON string with temperature, conditions, humidity, and wind speed.
    Use this to set the mood and atmosphere in article opening paragraphs.
    """
    city = location if location else cfg.news.weather_location
    logger.info(f"[weather_tool] Fetching weather for: {city}")

    # TUTORIAL: wttr.in's ?format=j1 returns structured JSON — no API key needed.
    # This is a great zero-cost data source for demos and tutorials.
    url = f"https://wttr.in/{quote(city)}?format=j1"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = json.loads(response.read().decode("utf-8"))

        # TUTORIAL: We extract only what the LLM needs — sending the full
        # wttr.in response to an LLM wastes tokens. Always pre-process tool
        # outputs to keep context windows lean.
        current = raw["current_condition"][0]
        weather = {
            "location": city,
            "temp_c": int(current["temp_C"]),
            "temp_f": int(current["temp_F"]),
            "conditions": current["weatherDesc"][0]["value"],
            "humidity_pct": int(current["humidity"]),
            "wind_kmh": int(current["windspeedKmph"]),
            "feels_like_c": int(current["FeelsLikeC"]),
        }

        logger.info(
            f"[weather_tool] {city}: {weather['temp_c']}°C, {weather['conditions']}"
        )
        return json.dumps(weather)

    except urllib.error.URLError as exc:
        # Network failure — return a plausible Dublin default.
        logger.warning(f"[weather_tool] HTTP error: {exc}")
        return _fallback_weather(city)
    except (KeyError, json.JSONDecodeError) as exc:
        # Unexpected response format.
        logger.warning(f"[weather_tool] Parse error: {exc}")
        return _fallback_weather(city)
    except Exception as exc:
        logger.warning(f"[weather_tool] Unexpected error: {exc}")
        return _fallback_weather(city)


def _fallback_weather(city: str) -> str:
    """Return a plausible Dublin fallback when the API is unreachable."""
    logger.info("[weather_tool] Using fallback weather data")
    return json.dumps({
        "location": city,
        "temp_c": 9,
        "temp_f": 48,
        "conditions": "Overcast with a chance of existential drizzle",
        "humidity_pct": 82,
        "wind_kmh": 23,
        "feels_like_c": 6,
        "note": "Fallback data — actual weather API unreachable",
    })
