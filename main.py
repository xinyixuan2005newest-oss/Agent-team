# -*- coding: utf-8 -*-
"""天气查询应用入口。

创建 QApplication 并启动主窗口。
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from weather_app import config
from weather_app.main_window import MainWindow

# ---------------------------------------------------------------------------
# 高 DPI 缩放（必须在创建 QApplication 之前设置）：
# Qt5 运行时使进程 DPI-aware，但默认不启用 HighDpiScaling——125%/150% 显示
# 缩放下 pt 字号按真实 DPI 放大而布局像素不变，文字超出控件高度被裁切。
# PassThrough 舍入策略很关键：默认 Round 会把 125% 舍入为 100%，使修复失效。
# ---------------------------------------------------------------------------
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)


def _get_application() -> QApplication:
    """创建或复用 QApplication 实例。

    已存在实例（如脚本/测试中重复调用 main）时直接复用，
    避免重复创建 QApplication 引发 Qt 异常。

    :return: 全局唯一的 QApplication 实例
    """
    return QApplication.instance() or QApplication(sys.argv)


def main() -> None:
    """应用入口：初始化 Qt 应用并进入事件循环。"""
    app = _get_application()
    # 与 favorites.py 的 QSettings 使用同一组织/应用名（见 config.py 常量）
    app.setOrganizationName(config.QSETTINGS_ORGANIZATION)
    app.setApplicationName(config.QSETTINGS_APPLICATION)
    # 全局字体双保险：QSS 级联之外再显式设置应用默认字体，
    # 确保详情区/下拉框等不回落到宋体衬线
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
