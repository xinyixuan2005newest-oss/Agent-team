# -*- coding: utf-8 -*-
"""应用常量配置模块（纯逻辑，不依赖 Qt）。

包含内置城市列表、API URL 模板、WMO 天气码部分配置、
网络超时时间以及日期可选范围等常量。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# 应用身份（QSettings 持久化使用，favorites 与 main.py 必须保持一致）
# ---------------------------------------------------------------------------

#: QSettings 组织名
QSETTINGS_ORGANIZATION: str = "WeatherTeam"

#: QSettings 应用名
QSETTINGS_APPLICATION: str = "WeatherApp"

# ---------------------------------------------------------------------------
# 网络配置
# ---------------------------------------------------------------------------

#: 网络请求超时时间（秒）
REQUEST_TIMEOUT: float = 5.0

#: 地理编码 API URL 模板（{city} 会被替换为 URL 编码后的城市名）
GEOCODING_URL_TEMPLATE: str = (
    "https://geocoding-api.open-meteo.com/v1/search"
    "?name={city}&count=5&language=zh&format=json"
)

#: 预报 API URL 模板
FORECAST_URL_TEMPLATE: str = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
    "apparent_temperature_max,apparent_temperature_min,"
    "precipitation_probability_max,wind_speed_10m_max,"
    "wind_direction_10m_dominant,sunrise,sunset,uv_index_max"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
    "weather_code,wind_speed_10m,wind_direction_10m,pressure_msl"
    "&start_date={sd}&end_date={ed}&timezone=auto"
    "&temperature_unit=celsius&wind_speed_unit=kmh"
)

# ---------------------------------------------------------------------------
# 日期可选范围（相对今天）
# ---------------------------------------------------------------------------

#: 日期可选范围起点：今天 - 6 天
DATE_RANGE_MIN_OFFSET: int = -6

#: 日期可选范围终点：今天 + 15 天
DATE_RANGE_MAX_OFFSET: int = 15

#: 趋势图展示所选日期前后共 7 天
TREND_WINDOW_DAYS: int = 7

# ---------------------------------------------------------------------------
# 内置城市
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuiltinCity:
    """内置城市信息。

    :param name: 城市中文名
    :param latitude: 纬度（北纬为正）
    :param longitude: 经度（东经为正）
    """

    name: str
    latitude: float
    longitude: float


#: 内置常用城市列表（名称、纬度、经度）
BUILTIN_CITIES: Tuple[BuiltinCity, ...] = (
    BuiltinCity("北京", 39.9042, 116.4074),
    BuiltinCity("上海", 31.2304, 121.4737),
    BuiltinCity("广州", 23.1291, 113.2644),
    BuiltinCity("深圳", 22.5431, 114.0579),
    BuiltinCity("杭州", 30.2741, 120.1551),
    BuiltinCity("成都", 30.5728, 104.0668),
    BuiltinCity("武汉", 30.5928, 114.3055),
    BuiltinCity("西安", 34.3416, 108.9398),
    BuiltinCity("南京", 32.0603, 118.7969),
    BuiltinCity("重庆", 29.5630, 106.5516),
    BuiltinCity("天津", 39.3434, 117.3616),
    BuiltinCity("长沙", 28.2282, 112.9388),
    BuiltinCity("青岛", 36.0671, 120.3826),
    BuiltinCity("昆明", 25.0389, 102.7183),
    BuiltinCity("哈尔滨", 45.8038, 126.5350),
    BuiltinCity("香港", 22.3193, 114.1694),
)

# ---------------------------------------------------------------------------
# WMO 天气码 →（中文描述, 图标字符）映射
# ---------------------------------------------------------------------------

#: WMO weather_code → (中文描述, 图标字符) 映射表。
#: 图标使用 Unicode/Emoji 字符，由 icons.py 负责着色绘制。
WMO_CODE_MAP: "dict[int, Tuple[str, str]]" = {
    0: ("晴", "☀"),
    1: ("大致晴朗", "🌤"),
    2: ("局部多云", "⛅"),
    3: ("阴天", "☁"),
    45: ("雾", "🌫"),
    48: ("雾凇（冻结雾）", "🌫"),
    51: ("小毛毛雨", "🌦"),
    53: ("中毛毛雨", "🌦"),
    55: ("大毛毛雨", "🌧"),
    56: ("冻毛毛雨（轻）", "🌧"),
    57: ("冻毛毛雨（浓）", "🌧"),
    61: ("小雨", "🌧"),
    63: ("中雨", "🌧"),
    65: ("大雨", "🌧"),
    66: ("冻雨（轻）", "🌧"),
    67: ("冻雨（强）", "🌧"),
    71: ("小雪", "🌨"),
    73: ("中雪", "🌨"),
    75: ("大雪", "❄"),
    77: ("雪粒", "❄"),
    80: ("小阵雨", "🌦"),
    81: ("中阵雨", "🌧"),
    82: ("强阵雨", "⛈"),
    85: ("小阵雪", "🌨"),
    86: ("大阵雪", "❄"),
    95: ("雷阵雨", "⛈"),
    96: ("雷阵雨伴冰雹（轻）", "⛈"),
    99: ("雷阵雨伴冰雹（强）", "⛈"),
}

#: 未知天气码的默认描述
UNKNOWN_CODE_DESC: str = "未知天气"

#: 未知天气码的默认图标字符
UNKNOWN_CODE_ICON: str = "☁"
