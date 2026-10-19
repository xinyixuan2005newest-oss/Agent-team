# -*- coding: utf-8 -*-
"""pytest 环境辅助设置（供 tests/conftest.py 首行导入）。

不依赖 pytest-env / pytest-qt 等插件：仅在导入阶段用标准库设置
Qt 运行所需的环境变量。必须在导入 PyQt5 之前导入本模块才能生效。
"""

import os

# 无显示器环境（CI / 离屏测试）下强制 Qt 使用离屏平台插件；
# 使用 setdefault 保留调用方显式指定的平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
