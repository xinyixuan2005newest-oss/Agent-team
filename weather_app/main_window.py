# -*- coding: utf-8 -*-
"""主窗口模块（Qt）。

组装城市选择、日期选择、天气展示与趋势图界面；
网络请求在后台 QThread 中执行，失败时自动回退离线模拟数据。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Set, Union

from PyQt5.QtCore import QDate, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import config, icons, units
from .api import MockWeatherProvider, OpenMeteoClient
from .charts import TemperatureChartWidget
from .favorites import FavoritesManager
from .models import GeoLocation, WeatherReport

#: 日期选择窗口样式表（日历标题配色）
_CALENDAR_QSS = """
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #2c5f8a;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
}
QCalendarWidget QAbstractItemView {
    selection-background-color: #4a90d9;
    selection-color: #ffffff;
}
"""

#: 关闭窗口时等待单个工作线程结束的时限（毫秒），避免 GUI 长时间阻塞
_WORKER_CLOSE_WAIT_MS: int = 3000

#: 对超时线程 terminate() 后的额外收尾时限（毫秒）
_WORKER_TERMINATE_WAIT_MS: int = 1000

#: 窗口关闭时仍未能及时结束的工作线程（“孤儿”线程）。
#: 保持 Python 引用防止线程运行期间对象被垃圾回收引发销毁竞态崩溃；
#: 线程自然结束后由 finished→deleteLater（_track_worker 中连接）销毁并移除。
_detached_workers: List["ApiWorker"] = []


class ApiWorker(QThread):
    """通用后台请求线程。

    在子线程中执行注入的任务函数，成功/失败分别发信号；
    线程被请求中断（窗口关闭）时不再发射任何信号。
    """

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, job: Callable[[], object], parent: Optional[QObject] = None) -> None:
        """初始化工作线程。

        :param job: 将在子线程执行的可调用对象
        :param parent: 父 QObject
        """
        super().__init__(parent)
        self._job = job

    def run(self) -> None:
        """线程主体：执行任务并按结果发射信号。"""
        try:
            result = self._job()
        except Exception as exc:  # 网络异常/解析异常统一转失败信号
            if self.isInterruptionRequested():
                return
            self.failed.emit(str(exc))
            return
        if self.isInterruptionRequested():
            return
        self.succeeded.emit(result)


class MainWindow(QMainWindow):
    """天气查询主窗口。"""

    def __init__(
        self,
        client: Optional[OpenMeteoClient] = None,
        fallback_provider: Optional[MockWeatherProvider] = None,
        favorites: Optional[FavoritesManager] = None,
        today: Optional[Union[date, Callable[[], date]]] = None,
    ) -> None:
        """初始化界面、状态与默认城市（北京）。

        全部依赖均可注入，便于离屏测试替换为假客户端/模拟数据；
        首次天气加载延迟到窗口首次显示（showEvent）之后经事件循环启动，
        因此仅实例化 MainWindow() 不会发起任何网络请求。

        :param client: 天气 API 客户端（默认 OpenMeteoClient()）
        :param fallback_provider: 离线模拟数据提供者（默认 MockWeatherProvider()）
        :param favorites: 收藏管理器（默认 FavoritesManager()）
        :param today: 作为"今天"的基准日期（date）或零参日期时钟（返回 date
            的可调用对象）；默认使用系统时钟 date.today。注入可调用时钟后，
            每次 _start_forecast_fetch 都会重新解析"今天"，应用跨午夜运行时
            日历范围随之滚动更新（便于测试注入可变时钟）
        """
        super().__init__()
        self._client = client if client is not None else OpenMeteoClient()
        self._mock_provider = (
            fallback_provider if fallback_provider is not None else MockWeatherProvider()
        )
        self._favorites = favorites if favorites is not None else FavoritesManager()
        # "今天"时钟：date 包装为零参可调用，None 用系统时钟 date.today
        if today is None:
            self._today_clock: Callable[[], date] = date.today
        elif callable(today):
            self._today_clock = today
        else:
            fixed = today
            self._today_clock = lambda: fixed
        self._today = self._today_clock()  # 当前"今天"锚点（漂移检测基准）
        self._first_load_done = False  # 是否已启动过首次天气加载
        self._unit: str = "c"  # 当前温度单位（"c"/"f"）
        self._report: Optional[WeatherReport] = None
        first_city = config.BUILTIN_CITIES[0]
        self._current_location: GeoLocation = GeoLocation(
            name=first_city.name,
            latitude=first_city.latitude,
            longitude=first_city.longitude,
            country="中国",
        )
        self._combo_locations: List[Optional[GeoLocation]] = []
        self._active_workers: Set[ApiWorker] = set()

        self._init_ui()
        self._rebuild_city_combo(select_name=self._current_location.name)
        self._update_favorite_button()
        self.setWindowTitle("天气查询 - 按日期查看天气")
        self.resize(1000, 730)
        self.setMinimumSize(880, 660)

    # ------------------------------------------------------------------
    # 窗口事件与"今天"时钟
    # ------------------------------------------------------------------

    def _resolve_today(self) -> date:
        """解析最新的"今天"日期（经注入时钟）。

        应用跨午夜运行时返回值可能与锚点 self._today 不同。

        :return: 最新解析出的基准日期
        """
        return self._today_clock()

    def _today_qdate(self) -> QDate:
        """将当前"今天"锚点转换为 QDate。

        :return: 锚点日期对应的 QDate
        """
        return QDate(self._today.year, self._today.month, self._today.day)

    def _refresh_calendar_range(self) -> None:
        """按当前"今天"锚点刷新日历可选范围（today-6 ~ today+15）。

        选中日期若越界则夹取回范围内。全程 blockSignals：setDateRange
        在选中日期越界时会自动调整选中日期并触发 selectionChanged，
        若不屏蔽将造成"改范围 → 误发请求 → 再改范围"的循环。
        """
        today = self._today_qdate()
        min_date = today.addDays(config.DATE_RANGE_MIN_OFFSET)
        max_date = today.addDays(config.DATE_RANGE_MAX_OFFSET)
        self.calendar.blockSignals(True)
        try:
            self.calendar.setDateRange(min_date, max_date)
            selected = self.calendar.selectedDate()
            if selected < min_date:
                self.calendar.setSelectedDate(min_date)
            elif selected > max_date:
                self.calendar.setSelectedDate(max_date)
        finally:
            self.calendar.blockSignals(False)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名约定)
        """首次显示窗口时启动默认城市的天气加载。

        加载经 QTimer 延迟到事件循环中执行：窗口尚未进入事件循环前
        不起后台线程，从而保证离屏实例化 MainWindow() 不发起网络请求。

        :param event: 显示事件
        """
        super().showEvent(event)
        if self._first_load_done:
            return
        self._first_load_done = True
        QTimer.singleShot(
            0, lambda: self._start_forecast_fetch(self._current_location)
        )

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """构建全部界面控件与布局。"""
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 8)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_left_panel(), stretch=0)
        root_layout.addWidget(self._build_right_panel(), stretch=1)

        central.setStyleSheet(
            # 全局字体经级联继承到全部子控件，避免中文回落宋体衬线
            "#central {"
            "  background-color: #eef2f7;"
            "  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei',"
            " 'Noto Sans CJK SC', sans-serif;"
            "  font-size: 10pt;"
            "}"
            "QGroupBox {"
            "  background-color: #ffffff;"
            "  border: 1px solid #d7dee8;"
            "  border-radius: 8px;"
            "  margin-top: 20px;"
            "  font-family: 'Microsoft YaHei';"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  left: 12px;"
            "  padding: 0 6px;"
            "  color: #2c5f8a;"
            "  font-weight: bold;"
            "  font-size: 15px;"
            "}"
            # 统一保证标签行高，详情行文字不再被裁切；
            # #valueLabel 选择器优先级更高，确保值标签保持 24px（高于 QSS 的 22px）
            "QLabel { min-height: 22px; }"
            "#valueLabel { min-height: 24px; }"
            "QComboBox, QLineEdit {"
            "  background: #ffffff;"
            "  border: 1px solid #c3ccd9;"
            "  border-radius: 5px;"
            "  padding: 4px 8px;"
            "  min-height: 22px;"
            "}"
            "QComboBox:hover, QLineEdit:hover { border-color: #4a90d9; }"
            "QPushButton {"
            "  background-color: #2c5f8a;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 5px;"
            "  padding: 6px 14px;"
            "  font-family: 'Microsoft YaHei';"
            "}"
            "QPushButton:hover { background-color: #3a76a8; }"
            "QPushButton:pressed { background-color: #244d70; }"
            "QPushButton:disabled { background-color: #a9b6c6; }"
            "QStatusBar { color: #44536a; }"
        )

    def _build_left_panel(self) -> QWidget:
        """构建左侧面板：城市选择、在线搜索、日期日历。

        :return: 左侧容器控件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- 城市选择分组 ---
        city_group = QGroupBox("城市选择")
        city_layout = QVBoxLayout(city_group)
        # QSS 不为 QGroupBox 的 padding 预留空间，边距由布局显式给出
        city_layout.setContentsMargins(16, 12, 16, 12)
        city_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("常用城市"))
        self.city_combo = QComboBox()
        self.city_combo.setMinimumWidth(190)
        self.city_combo.currentIndexChanged.connect(self._on_city_combo_changed)
        row1.addWidget(self.city_combo, stretch=1)
        city_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("在线搜索"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入城市名，如：丽江")
        self.search_edit.returnPressed.connect(self._on_search_clicked)
        row2.addWidget(self.search_edit, stretch=1)
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self._on_search_clicked)
        row2.addWidget(self.search_button)
        city_layout.addLayout(row2)

        self.search_combo = QComboBox()
        self.search_combo.setVisible(False)
        self.search_combo.currentIndexChanged.connect(self._on_search_result_selected)
        city_layout.addWidget(self.search_combo)

        row3 = QHBoxLayout()
        self.favorite_button = QPushButton("☆ 添加收藏")
        self.favorite_button.clicked.connect(self._on_favorite_toggled)
        row3.addWidget(self.favorite_button)
        row3.addStretch(1)
        row3.addWidget(QLabel("温度单位"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("°C（摄氏度）", "c")
        self.unit_combo.addItem("°F（华氏度）", "f")
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        row3.addWidget(self.unit_combo)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        row3.addWidget(self.refresh_button)
        city_layout.addLayout(row3)

        layout.addWidget(city_group)

        # --- 日期选择分组 ---
        date_group = QGroupBox("选择日期（今天-6 天 至 今天+15 天）")
        date_layout = QVBoxLayout(date_group)
        date_layout.setContentsMargins(16, 12, 16, 12)
        date_layout.setSpacing(10)
        self.calendar = QCalendarWidget()
        today = self._today_qdate()
        self.calendar.setDateRange(
            today.addDays(config.DATE_RANGE_MIN_OFFSET),
            today.addDays(config.DATE_RANGE_MAX_OFFSET),
        )
        self.calendar.setSelectedDate(today)
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.selectionChanged.connect(self._on_date_changed)
        self.calendar.setStyleSheet(_CALENDAR_QSS)
        date_layout.addWidget(self.calendar)

        layout.addWidget(date_group, stretch=1)
        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右侧面板：当日天气展示与温度趋势图。

        :return: 右侧容器控件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        weather_group = QGroupBox("当日天气")
        weather_layout = QVBoxLayout(weather_group)
        weather_layout.setContentsMargins(16, 12, 16, 12)
        weather_layout.setSpacing(10)

        # 头部：大图标 + 天气描述
        header = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(84, 84)
        self.icon_label.setAlignment(Qt.AlignCenter)
        header.addWidget(self.icon_label)
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        self.desc_label = QLabel("--")
        # 字体只经控件自身 QSS 声明，禁止 setFont 与祖先级联 QSS 混用：
        # 两者并存时布局按级联字体计算高度、绘制却用程序字体，
        # 会造成天气描述底部被裁切（高 DPI 缩放下尤为明显）。
        # min-height 同样写入本规则（QSS min-height 会覆盖 setMinimumHeight）。
        self.desc_label.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #2c5f8a;"
            "min-height: 42px; margin-bottom: 2px;"
        )
        self.date_scope_label = QLabel("请选择日期")
        self.date_scope_label.setStyleSheet("color: #6b7a90; font-size: 10.5pt;")
        header_box.addWidget(self.desc_label)
        header_box.addWidget(self.date_scope_label)
        header_box.addStretch(1)
        header.addLayout(header_box, stretch=1)
        weather_layout.addLayout(header)

        # 详情表单
        self.value_labels: Dict[str, QLabel] = {}
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 10, 0, 0)
        rows = (
            ("temp_max", "最高气温"),
            ("temp_min", "最低气温"),
            ("temp_current", "当前气温"),
            ("apparent", "体感温度"),
            ("humidity", "相对湿度"),
            ("wind", "风速与风向"),
            ("precip", "降水概率"),
            ("pressure", "气压"),
            ("uv", "紫外线指数"),
            ("sunrise", "日出时间"),
            ("sunset", "日落时间"),
        )
        for key, title in rows:
            label = QLabel("--")
            label.setObjectName("valueLabel")
            label.setStyleSheet("font-weight: bold; color: #303a4a;")
            label.setMinimumHeight(24)
            label.setAlignment(Qt.AlignVCenter)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.value_labels[key] = label
            form.addRow(QLabel(title), label)
        weather_layout.addLayout(form)
        layout.addWidget(weather_group)

        chart_group = QGroupBox("7 天温度趋势（以所选日期为中心）")
        chart_layout = QVBoxLayout(chart_group)
        chart_layout.setContentsMargins(16, 12, 16, 12)
        chart_layout.setSpacing(10)
        self.chart = TemperatureChartWidget()
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_group, stretch=1)
        return panel

    # ------------------------------------------------------------------
    # 城市下拉与收藏
    # ------------------------------------------------------------------

    def _rebuild_city_combo(self, select_name: Optional[str] = None) -> None:
        """重建城市下拉框：收藏城市置顶，其后为内置城市。

        :param select_name: 重建后尝试选中的城市名
        """
        self.city_combo.blockSignals(True)
        self.city_combo.clear()
        self._combo_locations = []

        favorites = self._favorites.load()
        for location in favorites:
            self.city_combo.addItem(f"★ {location.name}")
            self._combo_locations.append(location)
        if favorites:
            self.city_combo.insertSeparator(self.city_combo.count())
            self._combo_locations.append(None)

        for city in config.BUILTIN_CITIES:
            self.city_combo.addItem(city.name)
            self._combo_locations.append(
                GeoLocation(city.name, city.latitude, city.longitude, "中国")
            )

        # 恢复选中项
        target_index = -1
        if select_name:
            for index, location in enumerate(self._combo_locations):
                if location is not None and location.name == select_name:
                    target_index = index
                    break
        if target_index >= 0:
            self.city_combo.setCurrentIndex(target_index)
        self.city_combo.blockSignals(False)

    def _on_city_combo_changed(self, index: int) -> None:
        """下拉框选择变化：切换当前城市并加载天气。

        :param index: 新选中的索引
        """
        if 0 <= index < len(self._combo_locations):
            location = self._combo_locations[index]
        else:
            location = None
        if location is None:
            return
        self._current_location = location
        self.search_combo.setVisible(False)
        self._update_favorite_button()
        self._start_forecast_fetch(location)

    def _update_favorite_button(self) -> None:
        """根据当前城市是否已收藏更新收藏按钮文案。"""
        if self._favorites.contains(self._current_location.name):
            self.favorite_button.setText("★ 取消收藏")
        else:
            self.favorite_button.setText("☆ 添加收藏")

    def _on_favorite_toggled(self) -> None:
        """收藏按钮点击：添加/移除当前城市收藏并刷新下拉框。"""
        name = self._current_location.name
        if self._favorites.contains(name):
            self._favorites.remove(name)
            self.statusBar().showMessage(f"已从收藏移除：{name}")
        else:
            if self._favorites.add(self._current_location):
                self.statusBar().showMessage(f"已收藏：{name}")
        self._rebuild_city_combo(select_name=name)
        self._update_favorite_button()

    # ------------------------------------------------------------------
    # 在线搜索
    # ------------------------------------------------------------------

    def _on_search_clicked(self) -> None:
        """搜索按钮点击：发起在线城市搜索。"""
        # in-flight 防护：搜索进行中按钮已禁用，
        # 回车触发本槽时直接忽略，避免重复起线程
        if not self.search_button.isEnabled():
            return
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.statusBar().showMessage("请先输入要搜索的城市名")
            return
        self.statusBar().showMessage(f"正在搜索城市：{keyword}…")
        self.search_button.setEnabled(False)
        worker = ApiWorker(lambda: self._client.fetch_geocoding(keyword))
        worker.succeeded.connect(
            lambda results: self._on_search_ok(keyword, results)
        )
        worker.failed.connect(self._on_search_fail)
        self._track_worker(worker)
        worker.start()

    def _on_search_ok(self, keyword: str, results: List[GeoLocation]) -> None:
        """搜索成功：展示候选城市列表。

        :param keyword: 搜索关键词
        :param results: 候选地点列表
        """
        self.search_button.setEnabled(True)
        self._active_workers.discard(self.sender())
        self.search_combo.blockSignals(True)
        try:
            self.search_combo.clear()
            if not results:
                self.search_combo.setVisible(False)
                self.statusBar().showMessage(f"未找到与「{keyword}」匹配的城市")
                return
            for location in results:
                self.search_combo.addItem(location.display_text(), location)
            # addItem 在信号阻塞期间已把 currentIndex 静默置 0；若不复位，
            # 用户直接选第一个候选时索引无变化、currentIndexChanged 不发射。
            # 此处信号仍被阻塞，复位为 -1 不会触发任何槽（无误加载副作用），
            # 之后用户选择任意候选（含索引 0）都会产生 -1→N 的真实索引变化。
            self.search_combo.setCurrentIndex(-1)
            self.search_combo.setVisible(True)
            self.statusBar().showMessage(f"找到 {len(results)} 个候选城市，请选择")
        finally:
            # 无结果早退路径同样必须恢复信号，否则后续选城将永久失效
            self.search_combo.blockSignals(False)

    def _on_search_fail(self, message: str) -> None:
        """搜索失败：状态栏提示（不打断用户）。

        :param message: 失败原因
        """
        self.search_button.setEnabled(True)
        self._active_workers.discard(self.sender())
        self.statusBar().showMessage(f"城市搜索失败：{message}")

    def _on_search_result_selected(self, index: int) -> None:
        """搜索结果选中：切换当前城市并加载天气。

        :param index: 选中索引
        """
        location = self.search_combo.itemData(index)
        if location is None:
            return
        self._current_location = location
        self._update_favorite_button()
        self._start_forecast_fetch(location)

    # ------------------------------------------------------------------
    # 天气请求与结果处理
    # ------------------------------------------------------------------

    def _on_refresh_clicked(self) -> None:
        """刷新按钮点击：重新请求当前城市的天气。"""
        self._start_forecast_fetch(self._current_location)

    def _on_unit_changed(self) -> None:
        """温度单位切换：重新渲染全部温度显示与趋势图。"""
        data = self.unit_combo.currentData()
        if data in ("c", "f"):
            self._unit = data
        self._update_display()
        self._update_chart()

    def _on_date_changed(self) -> None:
        """日期选择变化：更新当日天气与趋势图高亮。"""
        self._update_display()
        self._update_chart()

    def _start_forecast_fetch(self, location: GeoLocation) -> None:
        """发起后台天气预报请求（覆盖日期可选范围全长）。

        :param location: 目标城市
        """
        self.refresh_button.setEnabled(False)
        self.statusBar().showMessage(f"正在加载 {location.name} 的天气…")
        # 解析最新"今天"：跨午夜锚点漂移时先同步日历范围再发起请求
        latest_today = self._resolve_today()
        if latest_today != self._today:
            self._today = latest_today
            self._refresh_calendar_range()
        today = self._today
        start = today + timedelta(days=config.DATE_RANGE_MIN_OFFSET)
        end = today + timedelta(days=config.DATE_RANGE_MAX_OFFSET)
        worker = ApiWorker(
            lambda: self._client.fetch_forecast(location, start, end)
        )
        worker.succeeded.connect(self._on_forecast_ok)
        worker.failed.connect(self._on_forecast_fail)
        self._track_worker(worker)
        worker.start()

    def _on_forecast_ok(self, report: WeatherReport) -> None:
        """预报请求成功：应用在线数据并刷新界面。

        :param report: 天气报告
        """
        self.refresh_button.setEnabled(True)
        self._active_workers.discard(self.sender())
        if not self._is_report_current(report):
            return
        self._report = report
        self._update_display()
        self._update_chart()
        self.statusBar().showMessage(f"加载成功（在线数据）：{report.location.name}")

    def _on_forecast_fail(self, message: str) -> None:
        """预报请求失败：使用离线模拟数据兜底（不弹模态框）。

        :param message: 失败原因
        """
        self.refresh_button.setEnabled(True)
        self._active_workers.discard(self.sender())
        location = self._current_location
        today = self._today
        report = self._mock_provider.generate(
            location,
            today + timedelta(days=config.DATE_RANGE_MIN_OFFSET),
            today + timedelta(days=config.DATE_RANGE_MAX_OFFSET),
        )
        if not self._is_report_current(report):
            return
        self._report = report
        self._update_display()
        self._update_chart()
        self.statusBar().showMessage(
            f"离线模拟数据（网络请求失败：{message}）", 0
        )

    def _is_report_current(self, report: WeatherReport) -> bool:
        """检查报告是否仍属于当前所选城市（防止快速切换导致串数据）。

        :param report: 待检查的天气报告
        :return: 属于当前城市返回 True
        """
        current = self._current_location
        return (
            report.location.name == current.name
            and abs(report.location.latitude - current.latitude) < 0.05
            and abs(report.location.longitude - current.longitude) < 0.05
        )

    # ------------------------------------------------------------------
    # 界面刷新
    # ------------------------------------------------------------------

    def _selected_day(self) -> date:
        """获取日历当前选中的日期。

        :return: 选中的日期
        """
        return self.calendar.selectedDate().toPyDate()

    def _update_display(self) -> None:
        """根据当前报告与所选日期刷新天气展示区。"""
        selected = self._selected_day()
        today = self._today
        self.date_scope_label.setText(
            f"{selected.year} 年 {selected.month} 月 {selected.day} 日"
        )

        report = self._report
        if report is None:
            self._reset_display_values()
            return

        daily = report.find_daily(selected)
        if daily is None:
            self._reset_display_values()
            self.date_scope_label.setText(
                f"{selected.isoformat()}（超出数据范围）"
            )
            return

        # 天气现象（图标 + 描述）
        info = daily.weather
        self.icon_label.setPixmap(
            icons.weather_pixmap(info.icon_char, 72, icons.color_for_code(daily.weather_code))
        )
        self.desc_label.setText(info.description)

        unit = self._unit
        self.value_labels["temp_max"].setText(
            self._fmt_temp(daily.temp_max, unit)
        )
        self.value_labels["temp_min"].setText(
            self._fmt_temp(daily.temp_min, unit)
        )

        current = report.current if selected == today else None
        self.value_labels["temp_current"].setText(
            self._fmt_temp(current.temperature, unit)
            if current is not None and current.temperature is not None
            else "--（仅当天显示）"
        )

        if current is not None and current.apparent_temperature is not None:
            apparent_text = (
                f"{units.format_temperature(current.apparent_temperature, unit)}"
                f"（全天 {self._fmt_temp(daily.apparent_min, unit)} ~ "
                f"{self._fmt_temp(daily.apparent_max, unit)}）"
            )
        else:
            apparent_text = (
                f"{self._fmt_temp(daily.apparent_min, unit)} ~ "
                f"{self._fmt_temp(daily.apparent_max, unit)}"
            )
        self.value_labels["apparent"].setText(apparent_text)

        self.value_labels["humidity"].setText(
            units.format_humidity(current.humidity)
            if current is not None and current.humidity is not None
            else "--"
        )

        if daily.wind_speed_max is not None:
            wind_text = units.format_wind_speed(daily.wind_speed_max)
            if daily.wind_direction is not None:
                wind_text += (
                    f" · {units.wind_direction_name(daily.wind_direction)}"
                    f" · {units.wind_force_name(daily.wind_speed_max)}"
                )
            self.value_labels["wind"].setText(wind_text)
        else:
            self.value_labels["wind"].setText("--")

        self.value_labels["precip"].setText(
            f"{daily.precipitation_prob_max:.0f}%"
            if daily.precipitation_prob_max is not None
            else "--"
        )

        self.value_labels["pressure"].setText(
            units.format_pressure(current.pressure_msl)
            if current is not None and current.pressure_msl is not None
            else "--"
        )

        self.value_labels["uv"].setText(
            units.format_uv_index(daily.uv_index_max)
            if daily.uv_index_max is not None
            else "--"
        )
        self.value_labels["sunrise"].setText(units.format_time_iso(daily.sunrise or ""))
        self.value_labels["sunset"].setText(units.format_time_iso(daily.sunset or ""))

    def _update_chart(self) -> None:
        """刷新温度趋势图数据。"""
        if self._report is None:
            self.chart.clear()
            return
        self.chart.set_data(self._report.daily_list, self._selected_day(), self._unit)

    def _reset_display_values(self) -> None:
        """将天气展示区全部重置为占位符。"""
        self.icon_label.clear()
        self.desc_label.setText("--")
        for label in self.value_labels.values():
            label.setText("--")

    @staticmethod
    def _fmt_temp(celsius: Optional[float], unit: str) -> str:
        """格式化可选温度值。

        :param celsius: 摄氏温度（可为 None）
        :param unit: 目标单位
        :return: 形如 "23.5°C"；缺失时为 "--"
        """
        if celsius is None:
            return "--"
        return units.format_temperature(celsius, unit)

    # ------------------------------------------------------------------
    # 线程管理与安全退出
    # ------------------------------------------------------------------

    def _track_worker(self, worker: ApiWorker) -> None:
        """登记后台线程，并在其结束时自动清理。

        :param worker: 工作线程
        """
        self._active_workers.add(worker)
        worker.finished.connect(
            lambda w=worker: self._active_workers.discard(w)
        )
        worker.finished.connect(worker.deleteLater)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名约定)
        """窗口关闭：安全清理仍在运行的请求线程。

        先断开信号避免向已销毁界面发消息，再请求中断并限时等待；
        单线程最多等待 3 秒，避免逐个串行长等导致 GUI 长时间无响应。

        :param event: 关闭事件
        """
        for worker in list(self._active_workers):
            try:
                worker.succeeded.disconnect()
                worker.failed.disconnect()
            except TypeError:
                pass  # 信号尚未连接或已断开
            worker.requestInterruption()
        for worker in list(self._active_workers):
            if not worker.isRunning():
                continue
            if worker.wait(_WORKER_CLOSE_WAIT_MS):
                continue  # 已正常结束，finished→deleteLater 会自动清理
            # 限时内未结束：任务可能阻塞在无法响应中断的网络调用上，
            # 请求强制终止后再给一次短暂等待
            worker.terminate()
            if worker.wait(_WORKER_TERMINATE_WAIT_MS):
                continue
            # 仍存活：不再阻塞关闭流程。将其移入模块级孤儿列表保持
            # Python 引用，待线程自然结束后经 finished→deleteLater 销毁
            # 并从列表移除，避免线程运行期间对象被垃圾回收导致崩溃。
            self._active_workers.discard(worker)
            _detached_workers.append(worker)
            worker.finished.connect(_detached_workers.remove)
        super().closeEvent(event)
