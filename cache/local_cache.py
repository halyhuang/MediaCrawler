# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Name    : 程序员阿江-Relakkes
# @Time    : 2024/6/2 11:05
# @Desc    : 本地缓存

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from cache.abs_cache import AbstractCache


class ExpiringLocalCache(AbstractCache):
    """
    本地缓存，支持过期时间
    """
    def __init__(self):
        self._cache = {}
        self._expire_times = {}
        self._lock = asyncio.Lock()
        self._clear_task = None
        self._is_running = True
        # 移除在初始化时启动定时任务
        # self._start_clear_cron()

    async def ensure_clear_task(self):
        """
        确保清理任务已启动
        """
        if self._clear_task is None:
            self._start_clear_cron()

    def _start_clear_cron(self):
        """
        启动定时清理任务
        """
        async def clear_expired():
            while self._is_running:
                try:
                    await self._clear_expired()
                except Exception as e:
                    utils.logger.error(f"清理过期缓存时发生错误: {str(e)}")
                await asyncio.sleep(60)  # 每分钟清理一次

        self._clear_task = asyncio.create_task(clear_expired())

    async def close(self):
        """
        关闭缓存，清理资源
        """
        self._is_running = False
        if self._clear_task:
            self._clear_task.cancel()
            try:
                await self._clear_task
            except asyncio.CancelledError:
                pass
        await self._clear_expired()
        self._cache.clear()
        self._expire_times.clear()

    async def _clear_expired(self):
        """
        清理过期的缓存
        """
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, t in self._expire_times.items() if t <= now]
            for k in expired_keys:
                self._cache.pop(k, None)
                self._expire_times.pop(k, None)

    async def get(self, key):
        """
        获取缓存值
        """
        await self.ensure_clear_task()
        async with self._lock:
            if key in self._cache:
                expire_time = self._expire_times.get(key)
                if expire_time is None or expire_time > time.time():
                    return self._cache[key]
                else:
                    # 已过期，删除
                    self._cache.pop(key)
                    self._expire_times.pop(key)
            return None

    async def set(self, key, value, expire_seconds=None):
        """
        设置缓存值
        """
        await self.ensure_clear_task()
        async with self._lock:
            self._cache[key] = value
            if expire_seconds is not None:
                self._expire_times[key] = time.time() + expire_seconds
            else:
                self._expire_times.pop(key, None)

    async def delete(self, key):
        """
        删除缓存值
        """
        async with self._lock:
            self._cache.pop(key, None)
            self._expire_times.pop(key, None)

    async def clear(self):
        """
        清空缓存
        """
        async with self._lock:
            self._cache.clear()
            self._expire_times.clear()

    def keys(self, pattern: str) -> List[str]:
        """
        获取所有符合pattern的key
        :param pattern: 匹配模式
        :return:
        """
        if pattern == '*':
            return list(self._cache.keys())

        # 本地缓存通配符暂时将*替换为空
        if '*' in pattern:
            pattern = pattern.replace('*', '')

        return [key for key in self._cache.keys() if pattern in key]


if __name__ == '__main__':
    cache = ExpiringLocalCache()
    cache.set('name', '程序员阿江-Relakkes', 3)
    print(cache.get('key'))
    print(cache.keys("*"))
    time.sleep(4)
    print(cache.get('key'))
    del cache
    time.sleep(1)
    print("done")
