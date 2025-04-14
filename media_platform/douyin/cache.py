import asyncio
from typing import Dict, Any
from tools import utils

class ExpiringLocalCache:
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._clear_task = None
        self._expiration_times: Dict[str, float] = {}
        self._running = False

    async def _start_clear_cron(self):
        """启动定时清理过期缓存的任务"""
        try:
            while self._running:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self._clear_expired()
        except asyncio.CancelledError:
            utils.logger.info("缓存清理任务已取消")
        except Exception as e:
            utils.logger.error(f"缓存清理任务出错: {e}")
        finally:
            self._running = False
            self._clear_task = None

    async def _clear_expired(self):
        """清理过期的缓存项"""
        current_time = asyncio.get_event_loop().time()
        expired_keys = [
            key for key, expire_time in self._expiration_times.items()
            if expire_time <= current_time
        ]
        for key in expired_keys:
            del self._cache[key]
            del self._expiration_times[key]
        if expired_keys:
            utils.logger.info(f"已清理 {len(expired_keys)} 个过期缓存项")

    async def start(self):
        """启动缓存清理任务"""
        if not self._running and self._clear_task is None:
            self._running = True
            self._clear_task = asyncio.create_task(self._start_clear_cron())
            utils.logger.info("缓存清理任务已启动")

    async def stop(self):
        """停止缓存清理任务"""
        if self._running:
            self._running = False
            if self._clear_task:
                self._clear_task.cancel()
                try:
                    await self._clear_task
                except asyncio.CancelledError:
                    pass
                self._clear_task = None
            utils.logger.info("缓存清理任务已停止")

    def set(self, key: str, value: Any, expire_seconds: int = 300):
        """设置缓存项
        
        Args:
            key: 缓存键
            value: 缓存值
            expire_seconds: 过期时间（秒），默认5分钟
        """
        self._cache[key] = value
        self._expiration_times[key] = asyncio.get_event_loop().time() + expire_seconds

    def get(self, key: str) -> Any:
        """获取缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的值，如果不存在或已过期则返回None
        """
        if key not in self._cache:
            return None
            
        current_time = asyncio.get_event_loop().time()
        if self._expiration_times[key] <= current_time:
            del self._cache[key]
            del self._expiration_times[key]
            return None
            
        return self._cache[key]

    def delete(self, key: str):
        """删除缓存项
        
        Args:
            key: 缓存键
        """
        if key in self._cache:
            del self._cache[key]
            del self._expiration_times[key]

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        self._expiration_times.clear()
        utils.logger.info("所有缓存已清空") 