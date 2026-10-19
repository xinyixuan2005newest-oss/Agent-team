# -*- coding: utf-8 -*-
"""单位换算与格式化模块（纯逻辑，不依赖 Qt）。

提供摄氏/华氏温度换算、蒲福风级判定、风向角度转中文方位，
以及各类显示格式化函数。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 温度换算
# ---------------------------------------------------------------------------


def celsius_to_fahrenheit(celsius: float) -> float:
    """将摄氏温度转换为华氏温度。

    :param celsius: 摄氏温度
    :return: 对应的华氏温度
    """
    return celsius * 9.0 / 5.0 + 32.0


def convert_temperature(celsius: float, unit: str) -> float:
    """将摄氏温度按目标单位转换。

    :param celsius: 摄氏温度值
    :param unit: 目标单位，"c" 表示摄氏度，"f" 表示华氏度
    :return: 转换后的温度数值
    :raises ValueError: 当单位不是 "c" 或 "f" 时抛出
    """
    normalized = unit.strip().lower()
    if normalized == "c":
        return celsius
    if normalized == "f":
        return celsius_to_fahrenheit(celsius)
    raise ValueError(f"不支持的温度单位: {unit!r}，仅支持 'c' 或 'f'")


def format_temperature(celsius: float, unit: str, with_unit: bool = True) -> str:
    """格式化温度显示字符串（内部统一存摄氏，显示层转换单位）。

    :param celsius: 摄氏温度值
    :param unit: 目标显示单位（"c" 或 "f"）
    :param with_unit: 是否附带单位后缀（如 "°C"）
    :return: 形如 "23.5°C" 或 "-8°F" 的字符串（华氏度取整）
    """
    value = convert_temperature(celsius, unit)
    if unit.strip().lower() == "f":
        text = f"{value:.0f}"
        suffix = "°F"
    else:
        text = f"{value:.1f}"
        suffix = "°C"
    if with_unit:
        return f"{text}{suffix}"
    return text


def temperature_unit_label(unit: str) -> str:
    """返回温度单位的标准显示标签。

    :param unit: "c" 或 "f"
    :return: "°C" 或 "°F"
    :raises ValueError: 当单位不合法时抛出
    """
    normalized = unit.strip().lower()
    if normalized == "c":
        return "°C"
    if normalized == "f":
        return "°F"
    raise ValueError(f"不支持的温度单位: {unit!r}")


# ---------------------------------------------------------------------------
# 风速等级与风向
# ---------------------------------------------------------------------------


#: 风速等级起始阈值（km/h），对应蒲福风级 1-12 级的下限风速
_WIND_SCALE_BOUNDS: tuple = (1.0, 6.0, 12.0, 20.0, 29.0, 39.0, 50.0, 62.0, 75.0, 89.0, 103.0, 118.0)

#: 蒲福风级中文描述（索引 0 对应 0 级）
WIND_FORCE_NAMES: tuple = (
    "无风", "软风", "轻风", "微风", "和风", "清劲风",
    "强风", "疾风", "大风", "烈风", "狂风", "暴风", "飓风",
)


def wind_force_name(kmh: float) -> str:
    """根据风速（km/h）返回蒲福风级中文描述。

    :param kmh: 风速（千米/小时）
    :return: 形如 "微风(3级)" 的描述
    """
    level = 0
    for index, bound in enumerate(_WIND_SCALE_BOUNDS):
        if kmh >= bound:
            level = index + 1
    return f"{WIND_FORCE_NAMES[level]}({level}级)"


def wind_direction_name(degrees: float) -> str:
    """将风向角度转换为中文十六方位描述。

    :param degrees: 风向角度（0-360，气象惯例为风的来向）
    :return: 形如 "东北风" 的中文方位描述
    """
    directions = (
        "北", "东北偏北", "东北", "东北偏东", "东", "东南偏东",
        "东南", "东南偏南", "南", "西南偏南", "西南", "西南偏西",
        "西", "西北偏西", "西北", "西北偏北",
    )
    normalized = degrees % 360.0
    index = int((normalized + 11.25) // 22.5) % 16
    return f"{directions[index]}风"


def format_wind_speed(kmh: float) -> str:
    """格式化风速显示字符串。

    :param kmh: 风速（千米/小时）
    :return: 形如 "12.3 km/h" 的字符串
    """
    return f"{kmh:.1f} km/h"


# ---------------------------------------------------------------------------
# 其它格式化
# ---------------------------------------------------------------------------


def format_humidity(humidity: float) -> str:
    """格式化相对湿度显示字符串。

    :param humidity: 相对湿度（0-100）
    :return: 形如 "65%" 的字符串
    """
    return f"{humidity:.0f}%"


def format_pressure(pressure_hpa: float) -> str:
    """格式化气压显示字符串。

    :param pressure_hpa: 气压值（百帕）
    :return: 形如 "1013 hPa" 的字符串
    """
    return f"{pressure_hpa:.0f} hPa"


def format_uv_index(uv_value: float) -> str:
    """格式化紫外线指数并附带等级描述。

    :param uv_value: 紫外线指数
    :return: 形如 "6 (高)" 的字符串
    """
    if uv_value < 3:
        level = "低"
    elif uv_value < 6:
        level = "中"
    elif uv_value < 8:
        level = "高"
    elif uv_value < 11:
        level = "很高"
    else:
        level = "极高"
    return f"{uv_value:.1f} ({level})"


def format_time_iso(iso_text: str) -> str:
    """从 ISO 时间字符串中提取简短的时分部分。

    例如 "2026-10-10T06:12" → "06:12"。

    :param iso_text: ISO 格式时间字符串
    :return: 时分部分；解析失败时返回原字符串
    """
    if not iso_text:
        return "--:--"
    if "T" in iso_text:
        time_part = iso_text.split("T", 1)[1]
        return time_part[:5]
    return iso_text
