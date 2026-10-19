# PyQt 天气应用 — 完整测试报告

- 项目：按选定日期显示天气的桌面应用（PyQt5 5.15.11 / Python 3.11.9）
- 工作区：`c:\Users\xinyi\Documents\trae_projects\agent团队`
- 开发流程：CodeWriter 编码 → CodeReviewer 评审 → 修复 → TestEngineer 测试 → Bug 修复迭代 → 全部通过
- 报告日期：2026-10-12（第 2 轮：P2 遗留项修复后更新）
- 最终结论：**256 passed / 0 failed / 0 error / 0 skipped（1.52s），全部通过，评审问题 15/15 闭环，无遗留缺陷**

---

## 1. 功能范围

| 功能 | 说明 |
|---|---|
| 城市选择 | 内置 16 个常用城市（含经纬度）；支持 Open-Meteo 地理编码在线搜索（中文候选） |
| 日期选择 | QCalendarWidget，可选范围 [今天−6, 今天+15]，范围外日期禁用 |
| 天气详情 | 天气现象（中文+WMO 码映射）、最高/最低/当前温度、体感、湿度、风速风向（蒲福风级+16方位）、降水概率、气压、紫外线指数、日出日落 |
| 温度趋势图 | 自定义 QPainter 折线图（前后 7 天最高/最低温，数值标注、选中日高亮，无第三方图表依赖） |
| 单位切换 | °C / °F 全局转换（内部恒存摄氏，仅显示层换算） |
| 城市收藏 | QSettings 持久化，可添加/移除，收藏置顶显示 |
| 异步与离线回退 | API 请求在 QThread 后台执行（5s 超时）；失败自动回退确定性模拟数据并在状态栏标注，不打断用户 |
| 线程安全清理 | closeEvent：断信号 → wait(3s) → terminate 兜底 → 孤儿线程托管，防 QThread 销毁崩溃 |

## 2. 源码清单（10 个文件，共 1,793 行）

| 文件 | 行数 | 职责 |
|---|---:|---|
| `main.py` | 19 | 入口：QApplication + MainWindow，QSettings 身份注册 |
| `weather_app/config.py` | 118 | 常量：内置城市、API URL 模板、WMO 0-99 映射表、QSettings 身份常量 |
| `weather_app/units.py` | 139 | 纯逻辑：°C↔°F 换算、蒲福风级（含 12 级飓风）、风向 16 方位、各类格式化 |
| `weather_app/models.py` | 135 | 纯逻辑：GeoLocation、WMO 查询、DailyWeather / CurrentWeather / WeatherReport |
| `weather_app/api.py` | 350 | OpenMeteoClient（build_url / parse_response / fetch / 防御式解析）+ MockWeatherProvider（确定性模拟） |
| `weather_app/icons.py` | 47 | Qt：Unicode 字符按天气类别着色渲染为 QIcon |
| `weather_app/charts.py` | 200 | Qt：TemperatureChartWidget（QPainter 双曲线折线图） |
| `weather_app/favorites.py` | 103 | FavoritesManager，支持注入 QSettings |
| `weather_app/main_window.py` | 667 | MainWindow：UI 组装、ApiWorker(QThread) 异步、搜索/单位/收藏/日期联动、closeEvent 清理 |
| `weather_app/conftest_helpers.py` | 9 | 导入即设置 `QT_QPA_PLATFORM=offscreen`，供测试基础设施使用 |

架构要点：config / units / models / api 四个纯逻辑模块零 Qt 依赖；MainWindow 支持注入 `client / fallback_provider / favorites / today`，离屏实例化不发起网络请求，首次加载延后至 showEvent。

## 3. 测试代码清单（12 个文件，256 个用例，共 1,569 行）

| 文件 | 用例数 | 覆盖内容 |
|---|---:|---|
| `tests/conftest.py` | — | 离屏基础设施：会话级 qapp、事件泵 pump、零网络 FakeClient / FakeFailingClient、固定报告构造器、QT_QPA_FONTDIR 字体环境 |
| `tests/test_units.py` | 60 | 换算（0/100/−40/26.5）、非法值 ValueError、风级边界（117.9→11级、118→12级）、16 方位边界取整、各格式化防御 |
| `tests/test_models.py` | 45 | 28 个 WMO 码逐一断言 + 未知码/None 回退、dataclass 全字段默认值、find_daily 命中/未命中 |
| `tests/test_api.py` | 44 | URL 构建（坐标/日期/时区/单位/异常）、parse_response 正常样例与全部防御分支（缺字段/空数组/NaN/"3"/截断补齐）、_parse_optional_int 边界、地理编码解析 |
| `tests/test_mock_provider.py` | 8 | 确定性（同参数两次一致）、差异性与数值区间、22 天连续、is_mock 标记 |
| `tests/test_favorites.py` | 10 | 注入 tmp_path QSettings：往返持久化、去重、跨实例读取、损坏条目、分隔符编码 |
| `tests/test_charts.py` | 8 | offscreen 渲染不崩溃、空数据/全缺失防御、°F 路径、7 天窗口切片 |
| `tests/test_icons.py` | 47 | 全部已知码 + 回退码 pixmap 非 null、自定义尺寸、15 例配色映射 |
| `tests/test_main_window.py` | 14 | 完整 UI 流程（见 §5 覆盖矩阵 a–i），全部注入假 client 零网络 |
| `tests/test_p2_fixes.py` | 18 | P2 修复回归：_map_series 缺温映射（None 占位/不伪造极值）、缺温断线渲染、图标像素级分类色断言（含彩色 emoji）、动态时钟跨午夜日历滚动与防信号循环、_get_application 实例复用 |
| `tests/test_main.py` | 2 | 入口模块导入级测试 |

测试原则：禁止真实网络（全部 monkeypatch/注入）；异步尽量转同步（信号阻塞 + 事件泵），不使用脆弱的 waitForFinished；不依赖 pytest-qt / pytest-env 等未安装插件。

## 4. CodeReviewer 评审问题与修复记录（共 15 项，已全部修复闭环）

| 级别 | 编号 | 问题 | 修复结果 |
|---|---|---|---|
| P0 | #1 | `_on_search_ok` 空结果早退漏调 `blockSignals(False)`，搜索选城永久失效 | ✅ try/finally 确保恢复 |
| P1 | #2 | MainWindow 硬编码依赖、构造即联网、时间不可注入，无法离屏测试 | ✅ 增加 DI 参数 + 首载延后至 showEvent |
| P1 | #3 | closeEvent 串行 wait(8s) 阻塞 GUI 且未检查返回值，有线程销毁崩溃风险 | ✅ wait(3s)+检查+terminate+孤儿托管 |
| P1 | #4 | 搜索无 in-flight 防护，回车绕过禁用按钮重复起 worker | ✅ 入口检查按钮状态 |
| P1 | #5 | 蒲福风级缺 12 级，≥118 km/h 仍显示 11 级 | ✅ 补 118.0→"飓风(12级)" |
| P2 | #8 | QSettings 身份两处不一致 | ✅ config.py 常量统一 |
| P2 | #9 | weather_code 对 NaN/数字字符串解析不防御 | ✅ 统一走 `_parse_optional_int` + OverflowError |
| P2 | #10 | 5 处死代码 | ✅ 全部删除 |
| P2 | #11 | 不实的"循环依赖"注释 | ✅ 随死代码删除 |
| P2 | #12 | pytest.ini 依赖未安装插件，offscreen 不生效 | ✅ 改为插件无关方案（conftest_helpers） |
| P2 | #13 | 初始状态栏冗余消息 | ✅ 删除 |
| P2 | #6 | 图表缺温数据贴底渲染 | ✅ 缺失值 None 占位，折线断线、跳过标注，y 轴仅按有效值缩放 |
| P2 | #7 | emoji 字符在 Windows 忽略画笔着色 | ✅ 蒙版着色（白色绘字 + SourceIn 填充分类色），彩色 emoji 亦被统一着色 |
| P2 | #14 | 构造与请求分别取"今天"，跨午夜可错位一天 | ✅ today 支持 date/可调用时钟，每次请求时解析并滚动日历范围（blockSignals 防循环） |
| P2 | #15 | main() 无 QApplication.instance() 防护 | ✅ 拆出 `_get_application()`，复用已有实例，入口行为不变 |

## 5. 单元测试覆盖矩阵（main_window 完整流程，全部通过）

| # | 场景 | 结果 |
|---|---|---|
| a | 离屏实例化不发起网络（fetch 计数 = 0） | ✅ |
| b | show 后首次加载成功：状态栏"成功/在线"、详情更新、仅请求一次、worker 清理 | ✅ |
| c | client 抛 NetworkError → 回退模拟数据、状态栏"离线/模拟"提示 | ✅ |
| d | 城市切换重新拉取、`_current_location` 正确 | ✅ |
| e | °C↔°F 切换（26.5°C ↔ 80°F） | ✅ |
| f | 日历范围 = today−6 ~ today+15、选日更新、非当天隐藏当前气温 | ✅ |
| g | 在线搜索：候选重建、直选第一个候选即激活；空结果"未找到"且 `signalsBlocked()` 为 False | ✅ |
| h | in-flight 防护：按钮禁用期间按钮/回车均不重复请求 | ✅ |
| i | 收藏：添加后下拉框出现"★ 北京"、ini 持久化、可取消 | ✅ |
| + | 快速切城防串台（`_is_report_current`） | ✅ |

## 6. 测试发现的 Bug 与修复记录（第 1 轮迭代）

| 编号 | 位置 | 现象 | 修复 |
|---|---|---|---|
| Bug #1 | `api.py` `_parse_optional_float` | NaN/Inf 透传，界面会显示 nan°C、趋势图坐标失真 | 返回前 `math.isfinite` 校验，非有限值返回 None |
| Bug #2 | `main_window.py` `_on_search_ok` | blockSignals 期间 addItem 静默置 currentIndex=0，解除后直选第一个候选不触发信号，候选无法激活 | 填充完成后（仍阻塞中）`setCurrentIndex(-1)` 复位，任意选择均触发真实索引变化 |

测试同步调整（随修复必要翻转，其余 236 例零改动）：
- `test_search_success_and_select_candidate`：移除"先选 1 再选回 0"的绕过写法，恢复直选索引 0 的自然断言；
- `test_parse_optional_float_nan_rejected`、`test_float_nan_rejected_as_none`：原为"记录现状"断言 NaN 透传，修复后翻转为断言 NaN/Inf → None。

## 7. 最终执行结果

```
============================= 256 passed in 1.52s =============================
```

- 第 1 轮测试：238 用例（3 例首轮为测试脚本预期值笔误，修正后通过），发现 2 个应用 bug，修复后复跑通过；
- 第 2 轮（P2 遗留项修复）：新增 18 例（`tests/test_p2_fixes.py`，含像素级着色断言与动态时钟日历滚动断言），既有 238 例零改动，**256 passed**，未发现新 bug；
- 第 3 轮（UI 视觉修复）：用户反馈"文字显示不全/行间距太窄、分组标题位置不佳、字体不美观"。修复：移除 QGroupBox QSS padding（布局裁切根因）改由布局 contentsMargins 承担、详情表单行距 8→12 且值标签 min-height 24、全局字体统一为 Microsoft YaHei UI、标题 margin-top 20px、窗口默认 1000x730。经离屏渲染截图视觉验收（11 行详情完整、行距舒适、标题不压边框），256 例零改动回归通过，exe 已重新打包并冒烟验证；
- 第 4 轮（高 DPI 显示修复）：用户在 Windows 显示缩放（125%/150%）环境反馈天气描述大字仍被裁切——根因为 Qt5 默认不启用 HighDpiScaling，pt 字号按真实 DPI 放大而布局像素不变。修复：main.py 在创建 QApplication 前启用 AA_EnableHighDpiScaling + AA_UseHighDpiPixmaps 并设 HighDpiScaleFactorRoundingPolicy.PassThrough（防 125% 被舍入回 100%），desc_label 加 min-height 44 兜底。经 QT_SCALE_FACTOR=1.5 离屏渲染验收（1563×1141 vs 100% 版 1042×760，缩放生效、全部文字完整），256 例零改动回归通过，exe 已重新打包并冒烟验证；
- 第 5 轮（desc 字体根因修复）：高 DPI 修复后用户反馈天气描述仍被裁切。真正根因：desc_label 用 setFont(20pt) 与祖先 #central QSS font-size 级联混用，布局按级联字体分配高度而绘制用程序字体，且 setMinimumHeight(44) 被 QSS `QLabel{min-height:22px}` 覆盖致兜底失效；离屏验证脚本未走 app.setFont 真实路径故未复现。修复：字体改为仅经控件自身 QSS 声明（font-size: 26px; font-weight: bold; min-height: 42px），删除 setFont 与 QFont 导入。以复现真实启动路径（windows 平台 + app.setFont + 高 DPI 属性）的脚本在 100%/125%/150% 三档缩放实测：desc 控件高 44 ≥ 字体高 33，全部 PASS；150% 最小窗口截图视觉验收通过；256 例零改动回归通过，exe 重新打包冒烟验证；
- 主协调者在终端独立复核确认，无回归。

## 8. 运行方式

```powershell
# 运行应用（在线数据，离线自动回退模拟数据）
python main.py

# 运行全部测试
python -m pytest tests/ -v --tb=short
```

## 9. 未覆盖项与遗留风险

1. 真实网络路径（`_http_get_json`、超时、HTTP 状态码）未测，仅覆盖 URL 构建与解析纯逻辑及注入假 client 的完整流程；
2. `closeEvent` 的 terminate → 孤儿线程托管兜底路径难以确定性构造，未覆盖；
3. 日历"范围外禁用"仅断言 minimumDate/maximumDate，未模拟导航裁剪行为；动态 today 仅覆盖同步时钟闭包场景，真实跨午夜依赖同一代码路径、未做真实等待验证；
4. icons 像素断言依赖本机 `C:\Windows\Fonts` 字体环境（QT_QPA_FONTDIR），其他 OS/精简字体环境需调整后方可复跑。
