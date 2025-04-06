import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Optional

from tools import utils


class DouYinMessageListener:
    def __init__(self, save_dir: str = "data/messages"):
        self.save_dir = save_dir
        self._ensure_save_dir()
        
    def _ensure_save_dir(self):
        """确保消息保存目录存在"""
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            
    def _get_message_file_path(self) -> str:
        """获取当前日期的消息文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.save_dir, f"douyin_messages_{today}.txt")
        
    async def save_message(self, message: Dict) -> None:
        """保存消息到文件"""
        try:
            file_path = self._get_message_file_path()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 格式化消息内容
            formatted_message = f"[{timestamp}] {json.dumps(message, ensure_ascii=False)}\n"
            
            # 追加写入文件
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(formatted_message)
                
            utils.logger.info(f"Message saved to {file_path}")
        except Exception as e:
            utils.logger.error(f"Failed to save message: {e}")
            
    async def start_listening(self, dy_client) -> None:
        """开始监听消息"""
        utils.logger.info("Starting DouYin message listener...")
        try:
            while True:
                # 这里需要实现具体的消息获取逻辑
                # 可以通过轮询或其他方式获取消息
                messages = await dy_client.get_messages()
                for message in messages:
                    await self.save_message(message)
                await asyncio.sleep(5)  # 每5秒检查一次新消息
        except Exception as e:
            utils.logger.error(f"Error in message listener: {e}") 