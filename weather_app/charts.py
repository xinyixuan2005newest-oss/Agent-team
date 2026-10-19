# -*- coding: utf-8 -*-
"""温度趋势折线图组件（Qt）。

TemperatureChartWidget 使用 QPainter 自绘所选日期前后共 7 天的
最高/最低温度折线，带数值标注与高亮定位，无 matplotlib 依赖。
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from . import units
from .models import DailyWeather

#: 图表内边距（像素）
_MARGIN = 42
#: 折线图上下额外留白比例
_Y_PADDING = 0.15


class TemperatureChartWidget(QWidget):
    """温度趋势折线图 widget。

    展示以选中日期为中心的 7 天最高/最低温度曲线，
    选中日期以竖直高亮线标记，数据点附带数值标注。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """初始化图表 widget。

        :param parent: 父控件
        """
        super().__init__(parent)
        self._daily_list: List[DailyWeather] = []
        self._selected_date: Optional[date] = None
        self._unit: str = "c"
        self.setMinimumHeight(220)
        self.setMinimumWidth(320)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def set_data(
        self, daily_list: List[DailyWeather], selected: Optional[date], unit: str
    ) -> None:
        """更新图表数据并重绘。

        :param daily_list: 全部可用每日天气（将自动截取 7 天窗口）
        :param selected: 当前选中日期（居中定位）
        :param unit: 温度单位（"c" 或 "f"）
        """
        self._daily_list = daily_list
        self._selected_date = selected
        self._unit = unit
        self.update()

    def clear(self) -> None:
        """清空图表数据。"""
        self._daily_list = []
        self._selected_date = None
        self.update()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _window_slice(self) -> List[DailyWeather]:
        """计算以选中日期为中心的 7 天数据窗口。

        :return: 截取后的每日数据列表（可能不足 7 天）
        """
        if not self._daily_list:
            return []
        center_index = 0
        for index, daily in enumerate(self._daily_list):
            if daily.date == self._selected_date:
                center_index = index
                break
        half = 3
        start = max(0, center_index - half)
        end = min(len(self._daily_list), center_index + half + 1)
        return self._daily_list[start:end]

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名约定)
        """重绘事件：绘制坐标区、曲线、数据点与数值标注。

        :param event: 绘制事件
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), QColor("#f7f9fc"))

        points = self._window_slice()
        if len(points) < 2 or points[0].date is None:
            painter.setPen(QColor("#8a95a5"))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无趋势数据")
            painter.end()
            return

        # 各序列的显示单位温度值；缺失以 None 占位（不再虚假贴底）
        max_values: List[Optional[float]] = []
        min_values: List[Optional[float]] = []
        for daily in points:
            max_values.append(
                units.convert_temperature(daily.temp_max, self._unit)
                if daily.temp_max is not None
                else None
            )
            min_values.append(
                units.convert_temperature(daily.temp_min, self._unit)
                if daily.temp_min is not None
                else None
            )

        # y 轴范围仅按有效值计算
        temps = [value for value in max_values + min_values if value is not None]
        if not temps:
            painter.setPen(QColor("#8a95a5"))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无趋势数据")
            painter.end()
            return
        temp_low = min(temps)
        temp_high = max(temps)
        span = max(temp_high - temp_low, 4.0)
        bottom = temp_low - span * _Y_PADDING
        top = temp_high + span * _Y_PADDING

        plot_rect = QRectF(
            _MARGIN,
            _MARGIN * 0.6,
            self.width() - _MARGIN * 2,
            self.height() - _MARGIN * 1.6,
        )

        max_points = self._map_series(max_values, plot_rect, bottom, top)
        min_points = self._map_series(min_values, plot_rect, bottom, top)

        # 背景网格与日期标签
        grid_font = QFont("Microsoft YaHei", 8)
        painter.setFont(grid_font)
        painter.setPen(QPen(QColor("#dde3ec"), 1, Qt.DotLine))
        for ratio in (0.25, 0.5, 0.75):
            x = plot_rect.left() + ratio * plot_rect.width()
            painter.drawLine(QPointF(x, plot_rect.top()), QPointF(x, plot_rect.bottom()))

        # 选中日期高亮竖线
        selected_index: Optional[int] = None
        for index, daily in enumerate(points):
            if daily.date == self._selected_date:
                selected_index = index
                break
        if selected_index is not None:
            ratio = selected_index / (len(points) - 1)
            x = plot_rect.left() + ratio * plot_rect.width()
            painter.setPen(QPen(QColor("#f5a623"), 2, Qt.DashLine))
            painter.drawLine(QPointF(x, plot_rect.top()), QPointF(x, plot_rect.bottom()))

        # 日期标签（x 轴）
        painter.setPen(QColor("#5f6b7a"))
        for index, daily in enumerate(points):
            if daily.date is None:
                continue
            ratio = index / (len(points) - 1)
            label = f"{daily.date.month}/{daily.date.day}"
            x = plot_rect.left() + ratio * plot_rect.width()
            rect = QRectF(x - 24, plot_rect.bottom() + 4, 48, 16)
            painter.drawText(rect, Qt.AlignCenter, label)

        # 绘制最高温曲线（红橙）
        self._draw_series(painter, max_points, points, QColor("#e8664c"), is_max=True)
        # 绘制最低温曲线（蓝）
        self._draw_series(painter, min_points, points, QColor("#4a90d9"), is_max=False)

        painter.end()

    @staticmethod
    def _map_series(
        values: List[Optional[float]],
        plot_rect: QRectF,
        bottom: float,
        top: float,
    ) -> List[Optional[QPointF]]:
        """将温度值序列映射为可绘制点序列（纯静态方法，便于直测映射逻辑）。

        横轴按索引在绘图区内均分，纵轴按 (bottom, top) 值域线性映射；
        缺失（None）位置不产生坐标点，绘制阶段据此断开线段、跳过标注。

        :param values: 已转换为目标单位的温度值序列（None 表示缺失）
        :param plot_rect: 绘图区域矩形
        :param bottom: y 轴值域下界
        :param top: y 轴值域上界
        :return: 与 values 等长的点列表，缺失位置为 None
        """
        count = len(values)
        mapped: List[Optional[QPointF]] = []
        for index, value in enumerate(values):
            if value is None:
                mapped.append(None)
                continue
            ratio = index / (count - 1) if count > 1 else 0.5
            y_ratio = (top - value) / (top - bottom) if top > bottom else 0.5
            mapped.append(
                QPointF(
                    plot_rect.left() + ratio * plot_rect.width(),
                    plot_rect.top() + y_ratio * plot_rect.height(),
                )
            )
        return mapped

    def _draw_series(
        self,
        painter: QPainter,
        points: List[Optional[QPointF]],
        daily_list: List[DailyWeather],
        color: QColor,
        is_max: bool,
    ) -> None:
        """绘制单条温度曲线及其数值标注。

        缺失点（None）处断开线段：以下一个有效点为起点 moveTo 另起子路径；
        缺失点不绘制数据圆点与数值标注。

        :param painter: 画笔对象
        :param points: 曲线坐标点序列（缺失位置为 None）
        :param daily_list: 对应的每日数据（取数值标注）
        :param color: 曲线颜色
        :param is_max: 是否为最高温曲线
        """
        # 折线：缺失点两侧断开（moveTo 跳至下一个有效点）
        path = QPainterPath()
        pen_down = False
        for point in points:
            if point is None:
                pen_down = False
                continue
            if pen_down:
                path.lineTo(point)
            else:
                path.moveTo(point)
                pen_down = True
        if not path.isEmpty():
            pen = QPen(color, 2.5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # 数据点与数值标注（缺失点直接跳过）
        label_font = QFont("Microsoft YaHei", 8)
        label_font.setBold(True)
        painter.setFont(label_font)
        for point, daily in zip(points, daily_list):
            if point is None:
                continue
            painter.setBrush(QColor("white"))
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(point, 3.2, 3.2)

            value = daily.temp_max if is_max else daily.temp_min
            text = units.format_temperature(value, self._unit)
            painter.setPen(QColor(color.darker(115)))
            if is_max:
                rect = QRectF(point.x() - 26, point.y() - 22, 52, 16)
            else:
                rect = QRectF(point.x() - 26, point.y() + 6, 52, 16)
            painter.drawText(rect, Qt.AlignCenter, text)
