# -*- coding: utf-8 -*-
"""Open-Meteo API 客户端与离线模拟数据提供者（纯逻辑，不依赖 Qt）。

包含：
- OpenMeteoClient：URL 构建、响应解析、同步网络请求（由调用方放入线程）
- MockWeatherProvider：基于城市名+日期种子的确定性模拟数据生成器
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import config
from .models import CurrentWeather, DailyWeather, GeoLocation, WeatherReport


# ---------------------------------------------------------------------------
# 异常定义
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """API 相关错误的基类。"""


class ApiResponseError(ApiError):
    """响应格式错误（字段缺失/结构异常）。"""


class NetworkError(ApiError):
    """网络请求失败（连接/超时/HTTP 状态码异常）。"""


# ---------------------------------------------------------------------------
# Open-Meteo 客户端
# ---------------------------------------------------------------------------


class OpenMeteoClient:
    """Open-Meteo API 客户端（纯逻辑，网络请求应放入后台线程执行）。"""

    def __init__(self, timeout: float = config.REQUEST_TIMEOUT) -> None:
        """初始化客户端。

        :param timeout: 请求超时时间（秒）
        """
        self._timeout = timeout

    # ------------------------------------------------------------------
    # URL 构建
    # ------------------------------------------------------------------

    @staticmethod
    def build_geocoding_url(city_name: str) -> str:
        """构建地理编码搜索 URL。

        :param city_name: 城市名称关键词
        :return: 编码完成的完整 URL
        :raises ValueError: 城市名为空时抛出
        """
        if not city_name or not city_name.strip():
            raise ValueError("城市名不能为空")
        encoded = urllib.parse.quote(city_name.strip())
        return config.GEOCODING_URL_TEMPLATE.format(city=encoded)

    @staticmethod
    def build_forecast_url(location: GeoLocation, start_date: date, end_date: date) -> str:
        """构建天气预报 URL。

        :param location: 地理位置信息
        :param start_date: 起始日期（含）
        :param end_date: 结束日期（含）
        :return: 编码完成的完整 URL
        :raises ValueError: 当 start_date > end_date 或位置非法时抛出
        """
        if start_date > end_date:
            raise ValueError("起始日期不能晚于结束日期")
        return config.FORECAST_URL_TEMPLATE.format(
            lat=f"{location.latitude:.6f}",
            lon=f"{location.longitude:.6f}",
            sd=start_date.isoformat(),
            ed=end_date.isoformat(),
        )

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    @staticmethod
    def parse_geocoding_response(payload: Dict[str, Any]) -> List[GeoLocation]:
        """解析地理编码响应，返回候选地点列表。

        :param payload: JSON 反序列化后的字典
        :return: 候选 GeoLocation 列表（无结果时为空列表）
        :raises ApiResponseError: 响应结构非法时抛出
        """
        if not isinstance(payload, dict):
            raise ApiResponseError("地理编码响应不是 JSON 对象")
        results = payload.get("results")
        if results is None:
            return []  # 未找到结果时 API 省略该字段
        if not isinstance(results, list):
            raise ApiResponseError("地理编码响应的 results 字段不是列表")
        locations: List[GeoLocation] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            latitude = item.get("latitude")
            longitude = item.get("longitude")
            if name is None or latitude is None or longitude is None:
                continue  # 跳过关键字段缺失的条目
            try:
                location = GeoLocation(
                    name=str(name),
                    latitude=float(latitude),
                    longitude=float(longitude),
                    country=str(item.get("country", "") or ""),
                )
            except (TypeError, ValueError):
                continue
            locations.append(location)
        return locations

    @staticmethod
    def _parse_optional_float(value: Any) -> Optional[float]:
        """将响应值安全解析为可选浮点数。

        NaN/Inf 等非有限值按非法数据处理（与 parse_response 注释一致）。

        :param value: 原始值（可能是 None / 数字 / 字符串）
        :return: 有限浮点数或 None
        """
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(result):
            return None
        return result

    @staticmethod
    def _parse_date_text(text: Any) -> Optional[date]:
        """将 "YYYY-MM-DD" 文本解析为 date。

        :param text: 原始日期文本
        :return: date 对象；非法时返回 None
        """
        if not text or not isinstance(text, str):
            return None
        try:
            return date.fromisoformat(text.strip()[:10])
        except ValueError:
            return None

    @classmethod
    def parse_response(cls, payload: Dict[str, Any], location: GeoLocation) -> WeatherReport:
        """解析预报响应为 WeatherReport。

        防御式处理：字段缺失/空列表时抛出明确异常，不崩溃。

        :param payload: JSON 反序列化后的字典
        :param location: 本次查询的地理位置
        :return: 解析后的 WeatherReport
        :raises ApiResponseError: 响应结构非法时抛出
        """
        if not isinstance(payload, dict):
            raise ApiResponseError("预报响应不是 JSON 对象")

        error_info = payload.get("error")
        if error_info:
            reason = payload.get("reason", "未知原因")
            raise ApiResponseError(f"API 返回错误: {reason}")

        daily_block = payload.get("daily")
        if not isinstance(daily_block, dict):
            raise ApiResponseError("响应缺少 daily 字段或其不是对象")

        date_texts = daily_block.get("time")
        if not isinstance(date_texts, list) or not date_texts:
            raise ApiResponseError("响应缺少 daily.time 或为空列表")

        def _daily_list(key: str) -> List[Optional[Any]]:
            """取 daily 下与 time 等长（或缺失补 None）的数组。

            :param key: 字段名
            :return: 与日期数等长的列表，缺失位置为 None
            """
            raw = daily_block.get(key)
            if not isinstance(raw, list):
                return [None] * len(date_texts)
            # 长度不齐时按日期数截断/补齐
            values: List[Optional[Any]] = list(raw[: len(date_texts)])
            while len(values) < len(date_texts):
                values.append(None)
            return values

        weather_codes = _daily_list("weather_code")
        temp_maxes = _daily_list("temperature_2m_max")
        temp_mins = _daily_list("temperature_2m_min")
        apparent_maxes = _daily_list("apparent_temperature_max")
        apparent_mins = _daily_list("apparent_temperature_min")
        precip_probs = _daily_list("precipitation_probability_max")
        wind_speeds = _daily_list("wind_speed_10m_max")
        wind_dirs = _daily_list("wind_direction_10m_dominant")
        sunrises = _daily_list("sunrise")
        sunsets = _daily_list("sunset")
        uv_maxes = _daily_list("uv_index_max")

        daily_list: List[DailyWeather] = []
        for index, date_text in enumerate(date_texts):
            raw_code = weather_codes[index]
            daily = DailyWeather(
                date=cls._parse_date_text(date_text),
                # 统一走防御式解析：兼容数字字符串，NaN/Inf/非法值返回 None
                weather_code=cls._parse_optional_int(raw_code),
            )
            daily.temp_max = cls._parse_optional_float(temp_maxes[index])
            daily.temp_min = cls._parse_optional_float(temp_mins[index])
            daily.apparent_max = cls._parse_optional_float(apparent_maxes[index])
            daily.apparent_min = cls._parse_optional_float(apparent_mins[index])
            daily.precipitation_prob_max = cls._parse_optional_float(precip_probs[index])
            daily.wind_speed_max = cls._parse_optional_float(wind_speeds[index])
            daily.wind_direction = cls._parse_optional_float(wind_dirs[index])
            sunrise_val = sunrises[index]
            daily.sunrise = str(sunrise_val) if sunrise_val is not None else None
            sunset_val = sunsets[index]
            daily.sunset = str(sunset_val) if sunset_val is not None else None
            daily.uv_index_max = cls._parse_optional_float(uv_maxes[index])
            daily_list.append(daily)

        # 解析 current（缺失时保持 None，不影响整体）
        current: Optional[CurrentWeather] = None
        current_block = payload.get("current")
        if isinstance(current_block, dict):
            current = CurrentWeather(
                temperature=cls._parse_optional_float(current_block.get("temperature_2m")),
                apparent_temperature=cls._parse_optional_float(
                    current_block.get("apparent_temperature")
                ),
                humidity=cls._parse_optional_float(
                    current_block.get("relative_humidity_2m")
                ),
                weather_code=cls._parse_optional_int(current_block.get("weather_code")),
                wind_speed=cls._parse_optional_float(current_block.get("wind_speed_10m")),
                wind_direction=cls._parse_optional_float(
                    current_block.get("wind_direction_10m")
                ),
                pressure_msl=cls._parse_optional_float(current_block.get("pressure_msl")),
            )

        return WeatherReport(location=location, daily_list=daily_list, current=current)

    @staticmethod
    def _parse_optional_int(value: Any) -> Optional[int]:
        """将响应值安全解析为可选整数。

        :param value: 原始值
        :return: 整数或 None
        """
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            # ValueError：非法字符串/NaN；OverflowError：float 的 Inf
            return None

    # ------------------------------------------------------------------
    # 网络请求
    # ------------------------------------------------------------------

    def _http_get_json(self, url: str) -> Dict[str, Any]:
        """执行 GET 请求并返回 JSON 字典。

        :param url: 目标 URL
        :return: JSON 反序列化后的字典
        :raises NetworkError: 网络失败/超时/状态码异常/JSON 非法时抛出
        """
        request = urllib.request.Request(url, headers={"User-Agent": "PyQt5WeatherApp/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except Exception as exc:  # 统一转为 NetworkError，交由上层兜底
            raise NetworkError(f"网络请求失败: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NetworkError(f"响应不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise NetworkError("响应 JSON 顶层不是对象")
        return data

    def fetch_geocoding(self, city_name: str) -> List[GeoLocation]:
        """在线搜索城市，返回候选地点列表。

        :param city_name: 城市名称关键词
        :return: 候选 GeoLocation 列表（无结果时为空列表）
        :raises NetworkError: 网络失败时抛出
        :raises ApiResponseError: 响应非法时抛出
        """
        url = self.build_geocoding_url(city_name)
        payload = self._http_get_json(url)
        return self.parse_geocoding_response(payload)

    def fetch_forecast(
        self, location: GeoLocation, start_date: date, end_date: date
    ) -> WeatherReport:
        """在线获取天气预报。

        :param location: 地理位置信息
        :param start_date: 起始日期（含）
        :param end_date: 结束日期（含）
        :return: WeatherReport
        :raises NetworkError: 网络失败时抛出
        :raises ApiResponseError: 响应非法时抛出
        """
        url = self.build_forecast_url(location, start_date, end_date)
        payload = self._http_get_json(url)
        return self.parse_response(payload, location)


# ---------------------------------------------------------------------------
# 离线模拟数据
# ---------------------------------------------------------------------------


class MockWeatherProvider:
    """确定性模拟天气数据生成器（网络失败时的离线回退）。

    以「城市名 + 日期」为随机种子，同一城市同一日期
    每次生成的数据完全一致，保证展示稳定。
    """

    # 常见天气码池（晴/多云/阴/雨/雪/雾/雷按权重排列）
    _CODE_POOL: tuple = (
        0, 0, 1, 1, 2, 2, 2, 3, 3, 45, 51, 53,
        61, 61, 63, 65, 71, 73, 80, 81, 95,
    )

    @staticmethod
    def _make_seed(city_name: str, day: date) -> int:
        """根据城市名与日期生成稳定整数种子。

        :param city_name: 城市名
        :param day: 日期
        :return: 32 位整数种子
        """
        text = f"{city_name}|{day.isoformat()}"
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def generate(
        self, location: GeoLocation, start_date: date, end_date: date
    ) -> WeatherReport:
        """生成模拟的 WeatherReport。

        :param location: 地理位置信息
        :param start_date: 起始日期（含）
        :param end_date: 结束日期（含）
        :return: 标记 is_mock=True 的 WeatherReport
        """
        daily_list: List[DailyWeather] = []
        current_day = start_date
        today = date.today()
        while current_day <= end_date:
            rng = random.Random(self._make_seed(location.name, current_day))
            code = rng.choice(self._CODE_POOL)
            # 以纬度为基础估算基准气温（越冷纬度越简单模拟）
            base_temp = 28.0 - abs(location.latitude) * 0.35
            temp_max = base_temp + rng.uniform(0.0, 6.0)
            temp_min = temp_max - rng.uniform(5.0, 12.0)
            daily = DailyWeather(
                date=current_day,
                weather_code=code,
                temp_max=round(temp_max, 1),
                temp_min=round(temp_min, 1),
                apparent_max=round(temp_max + rng.uniform(0.5, 3.0), 1),
                apparent_min=round(temp_min - rng.uniform(0.5, 3.0), 1),
                precipitation_prob_max=rng.choice([0, 0, 10, 20, 30, 50, 70, 90]),
                wind_speed_max=round(rng.uniform(3.0, 45.0), 1),
                wind_direction=float(rng.randrange(0, 360, 15)),
                sunrise=f"{current_day.isoformat()}T0{rng.randrange(4, 7)}:{rng.randrange(10, 60):02d}",
                sunset=f"{current_day.isoformat()}T1{rng.randrange(7, 9)}:{rng.randrange(10, 60):02d}",
                uv_index_max=round(rng.uniform(0.0, 10.0), 1),
            )
            daily_list.append(daily)
            current_day = current_day + timedelta(days=1)

        current: Optional[CurrentWeather] = None
        if start_date <= today <= end_date:
            rng = random.Random(self._make_seed(location.name + "#current", today))
            current = CurrentWeather(
                temperature=round(rng.uniform(2.0, 33.0), 1),
                apparent_temperature=round(rng.uniform(0.0, 35.0), 1),
                humidity=float(rng.randrange(25, 95)),
                weather_code=rng.choice(self._CODE_POOL),
                wind_speed=round(rng.uniform(2.0, 30.0), 1),
                wind_direction=float(rng.randrange(0, 360, 15)),
                pressure_msl=round(rng.uniform(995.0, 1030.0), 0),
            )

        return WeatherReport(
            location=location, daily_list=daily_list, current=current, is_mock=True
        )
