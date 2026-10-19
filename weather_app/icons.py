# -*- coding: utf-8 -*-
"""天气图标绘制模块（Qt）。

基于 QPainter 将 Unicode/Emoji 天气字符渲染为指定颜色、
指定尺寸的 QPixmap，供天气展示区使用。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap


def weather_pixmap(icon_char: str, size: int, color: str = "#4a90d9") -> QPixmap:
    """将天气字符渲染为单色 QPixmap（蒙版着色）。

    先以白色把字符画入透明画布形成蒙版，再经 CompositionMode_SourceIn
    用目标分类色填充全部非透明像素——即使字符按彩色 emoji 渲染
    （如 Windows 的 Segoe UI Emoji 字体会忽略画笔颜色），
    最终所有非透明像素也统一为目标色，保证 color_for_code 分类着色生效。

    :param icon_char: Unicode/Emoji 天气字符（如 "☀"、"🌧"）
    :param size: 目标边长（像素，正方形）
    :param color: 前景色（十六进制颜色字符串）
    :return: 渲染完成的 QPixmap
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    # 优先使用支持 emoji 的字体族，保证字符可显示（颜色由蒙版阶段统一替换）
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(int(size * 0.78))
    painter.setFont(font)
    # 第一步：以白色绘制字符蒙版（彩色 emoji 此步可能自带颜色）
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, icon_char)
    # 第二步：SourceIn 用目标色覆盖全部非透明像素，实现统一着色
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


def color_for_code(code: Optional[int]) -> str:
    """根据 WMO 天气码返回合适的图标前景色。

    :param code: WMO weather_code（可为 None）
    :return: 十六进制颜色字符串
    """
    if code is None:
        return "#8a8f98"
    if code == 0 or code == 1:  # 晴 / 大致晴朗
        return "#f5a623"
    if code in (2, 3, 45, 48):  # 云与雾
        return "#8a95a5"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):  # 各类降雨
        return "#4a90d9"
    if code in (71, 73, 75, 77, 85, 86):  # 各类降雪
        return "#63b3ed"
    if code in (95, 96, 99):  # 雷暴
        return "#9f7aea"
    return "#4a90d9"
