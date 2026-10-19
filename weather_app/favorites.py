# -*- coding: utf-8 -*-
"""常用城市收藏管理模块（QSettings 持久化）。

以 "名称|纬度|经度|国家" 文本格式保存收藏，支持注入
自定义 QSettings 实例以便单元测试。
"""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QSettings

from . import config
from .models import GeoLocation

#: QSettings 中存放收藏的键名
_FAVORITES_KEY: str = "favorites/cities"

#: 收藏条目的分隔符（避免与城市名常用字符冲突）
_SEP = "|"


def _encode(location: GeoLocation) -> str:
    """将 GeoLocation 编码为存储文本。

    :param location: 地理位置对象
    :return: 形如 "北京|39.9042|116.4074|中国" 的字符串
    """
    name = location.name.replace(_SEP, " ")
    country = location.country.replace(_SEP, " ")
    return f"{name}{_SEP}{location.latitude!r}{_SEP}{location.longitude!r}{_SEP}{country}"


def _decode(text: str) -> Optional[GeoLocation]:
    """将存储文本解码为 GeoLocation。

    :param text: 编码字符串
    :return: GeoLocation 对象；格式非法时返回 None
    """
    parts = text.split(_SEP)
    if len(parts) != 4:
        return None
    try:
        return GeoLocation(
            name=parts[0],
            latitude=float(parts[1]),
            longitude=float(parts[2]),
            country=parts[3],
        )
    except ValueError:
        return None


class FavoritesManager:
    """基于 QSettings 的城市收藏管理器。"""

    def __init__(self, settings: Optional[QSettings] = None) -> None:
        """初始化管理器。

        :param settings: 注入的 QSettings 实例；为 None 时使用默认构造
        """
        if settings is None:
            # 与 main.py 中的 QApplication 组织/应用名保持一致（见 config.py）
            settings = QSettings(
                config.QSETTINGS_ORGANIZATION, config.QSETTINGS_APPLICATION
            )
        self._settings = settings

    def load(self) -> List[GeoLocation]:
        """读取全部收藏城市。

        :return: 收藏列表（保持添加顺序）
        """
        raw = self._settings.value(_FAVORITES_KEY)
        if raw is None:
            return []
        texts = raw if isinstance(raw, list) else [raw]
        favorites: List[GeoLocation] = []
        for text in texts:
            if not isinstance(text, str):
                continue
            location = _decode(text)
            if location is not None:
                favorites.append(location)
        return favorites

    def save(self, favorites: List[GeoLocation]) -> None:
        """保存全部收藏城市。

        :param favorites: 收藏列表
        """
        texts = [_encode(item) for item in favorites]
        self._settings.setValue(_FAVORITES_KEY, texts)
        self._settings.sync()

    def add(self, location: GeoLocation) -> bool:
        """添加收藏（按名称去重）。

        :param location: 要收藏的城市
        :return: 成功新增返回 True；已存在返回 False
        """
        favorites = self.load()
        for existing in favorites:
            if existing.name == location.name:
                return False
        favorites.append(location)
        self.save(favorites)
        return True

    def remove(self, name: str) -> bool:
        """按城市名移除收藏。

        :param name: 城市名
        :return: 成功移除返回 True；不存在返回 False
        """
        favorites = self.load()
        remaining = [item for item in favorites if item.name != name]
        if len(remaining) == len(favorites):
            return False
        self.save(remaining)
        return True

    def contains(self, name: str) -> bool:
        """判断某城市名是否已被收藏。

        :param name: 城市名
        :return: 已收藏返回 True
        """
        return any(item.name == name for item in self.load())
