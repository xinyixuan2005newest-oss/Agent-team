# -*- coding: utf-8 -*-
"""数据模型模块（纯逻辑，不依赖 Qt）。

定义 WMO 天气码映射查询、DailyWeather / CurrentWeather / WeatherReport
等 dataclass，以及地理位置数据结构。温度统一以摄氏度 float 存储。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from . import config


# ---------------------------------------------------------------------------
# 地理位置信息
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeoLocation:
    """地理位置信息（城市）。

    :param name: 城市名称（中文或本地名）
    :param latitude: 纬度
    :param longitude: 经度
    :param country: 国家或行政区描述（可为空）
    """

    name: str
    latitude: float
    longitude: float
    country: str = ""

    def display_text(self) -> str:
        """返回下拉框中显示的文本。

        :return: 形如 "北京 (39.90, 116.41)" 的字符串
        """
        if self.country:
            return f"{self.name} · {self.country} ({self.latitude:.2f}, {self.longitude:.2f})"
        return f"{self.name} ({self.latitude:.2f}, {self.longitude:.2f})"


# ---------------------------------------------------------------------------
# WMO 天气码
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeatherCodeInfo:
    """WMO 天气码对应信息。

    :param code: WMO weather_code 整数值
    :param description: 中文天气描述
    :param icon_char: 图标字符（Unicode/Emoji）
    """

    code: int
    description: str
    icon_char: str


def describe_weather_code(code: Optional[int]) -> WeatherCodeInfo:
    """查询 WMO 天气码对应的中文描述与图标。

    :param code: WMO weather_code，可能为 None
    :return: 对应的 WeatherCodeInfo；未知或缺失码返回"未知天气"
    """
    if code is None:
        return WeatherCodeInfo(-1, config.UNKNOWN_CODE_DESC, config.UNKNOWN_CODE_ICON)
    mapping: Optional[Tuple[str, str]] = config.WMO_CODE_MAP.get(code)
    if mapping is None:
        return WeatherCodeInfo(code, config.UNKNOWN_CODE_DESC, config.UNKNOWN_CODE_ICON)
    return WeatherCodeInfo(code, mapping[0], mapping[1])


# ---------------------------------------------------------------------------
# 天气数据
# ---------------------------------------------------------------------------


@dataclass
class DailyWeather:
    """单日天气数据。

    温度字段统一为摄氏度 float（缺失用 None 表示）。

    :param date: 该日日期
    :param weather_code: WMO 天气码
    :param temp_max: 最高气温（°C）
    :param temp_min: 最低气温（°C）
    :param apparent_max: 最高体感温度（°C）
    :param apparent_min: 最低体感温度（°C）
    :param precipitation_prob_max: 最大降水概率（%，0-100）
    :param wind_speed_max: 最大风速（km/h）
    :param wind_direction: 主导风向角度（0-360）
    :param sunrise: 日出时间 ISO 字符串
    :param sunset: 日落时间 ISO 字符串
    :param uv_index_max: 紫外线指数最大值
    """

    date: Optional[date] = None
    weather_code: Optional[int] = None
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    apparent_max: Optional[float] = None
    apparent_min: Optional[float] = None
    precipitation_prob_max: Optional[float] = None
    wind_speed_max: Optional[float] = None
    wind_direction: Optional[float] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    uv_index_max: Optional[float] = None

    @property
    def weather(self) -> WeatherCodeInfo:
        """返回该日天气码对应的描述与图标信息。"""
        return describe_weather_code(self.weather_code)


@dataclass
class CurrentWeather:
    """当前天气数据（仅请求范围包含今天时由 API 返回）。

    :param temperature: 当前气温（°C）
    :param apparent_temperature: 当前体感温度（°C）
    :param humidity: 当前相对湿度（%）
    :param weather_code: 当前 WMO 天气码
    :param wind_speed: 当前风速（km/h）
    :param wind_direction: 当前风向角度（0-360）
    :param pressure_msl: 当前海平面气压（hPa）
    """

    temperature: Optional[float] = None
    apparent_temperature: Optional[float] = None
    humidity: Optional[float] = None
    weather_code: Optional[int] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    pressure_msl: Optional[float] = None

    @property
    def weather(self) -> WeatherCodeInfo:
        """返回当前天气码对应的描述与图标信息。"""
        return describe_weather_code(self.weather_code)


@dataclass
class WeatherReport:
    """一次完整天气查询的结果。

    :param location: 查询的地理位置
    :param daily_list: 按日期升序的每日天气列表
    :param current: 当前天气（仅当范围含今天时有效，否则为 None）
    :param is_mock: 是否来自离线模拟数据
    """

    location: GeoLocation
    daily_list: List[DailyWeather] = field(default_factory=list)
    current: Optional[CurrentWeather] = None
    is_mock: bool = False

    def find_daily(self, target: date) -> Optional[DailyWeather]:
        """查找指定日期的每日天气记录。

        :param target: 目标日期
        :return: 匹配的 DailyWeather；未找到返回 None
        """
        for daily in self.daily_list:
            if daily.date == target:
                return daily
        return None
