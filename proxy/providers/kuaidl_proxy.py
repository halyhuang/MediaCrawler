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
# @Time    : 2024/4/5 09:43
# @Desc    : 快代理HTTP实现，官方文档：https://www.kuaidaili.com/?ref=ldwkjqipvz6c
import os
import re
from typing import Dict, List
import asyncio
import time

import httpx
from pydantic import BaseModel, Field

from proxy import IpCache, IpInfoModel, ProxyProvider
from proxy.types import ProviderNameEnum
from tools import utils


class KuaidailiProxyModel(BaseModel):
    ip: str = Field("ip")
    port: int = Field("端口")
    expire_ts: int = Field("过期时间")


def parse_kuaidaili_proxy(proxy_info: str) -> KuaidailiProxyModel:
    """
    解析快代理的IP信息
    Args:
        proxy_info: 格式为 "ip:port" 或 "ip:port,expire_ts"

    Returns:
        KuaidailiProxyModel
    """
    # 检查是否包含过期时间
    if "," in proxy_info:
        # 格式为 "ip:port,expire_ts"
        ip_port, expire_ts = proxy_info.split(",")
        ip, port = ip_port.split(":")
        return KuaidailiProxyModel(
            ip=ip,
            port=int(port),
            expire_ts=int(expire_ts)
        )
    else:
        # 格式为 "ip:port"
        ip, port = proxy_info.split(":")
        # 默认过期时间为10分钟
        return KuaidailiProxyModel(
            ip=ip,
            port=int(port),
            expire_ts=int(time.time()) + 600
        )


class KuaiDaiLiProxy(ProxyProvider):
    def __init__(self, kdl_user_name: str, kdl_user_pwd: str, kdl_secret_id: str, kdl_signature: str):
        """

        Args:
            kdl_user_name:
            kdl_user_pwd:
        """
        self.kdl_user_name = kdl_user_name
        self.kdl_user_pwd = kdl_user_pwd
        self.api_base = "https://dps.kdlapi.com"
        self.secret_id = kdl_secret_id
        self.signature = kdl_signature
        self.ip_cache = IpCache()
        self.proxy_brand_name = ProviderNameEnum.KUAI_DAILI_PROVIDER.value
        self.params = {
            "secret_id": self.secret_id,
            "signature": self.signature,
            "pt": 1,
            "format": "json",
            "sep": 1,
            "f_et": 1,
            "username": self.kdl_user_name,
            "password": self.kdl_user_pwd
        }

    async def get_proxies(self, num: int = 1) -> List[IpInfoModel]:
        """
        从快代理API获取代理IP
        Args:
            num: 需要获取的代理IP数量，默认为1
        Returns:
            List[IpInfoModel]: 代理IP列表
        """
        try:
            # 构建API请求URL
            api_url = f"https://dps.kdlapi.com/api/getdps/?secret_id={self.secret_id}&signature={self.signature}&num={num}&pt=1&sep=1&format=json"
            utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 尝试从快代理API获取代理IP，URL: {api_url}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 0 and data.get("data"):
                        proxy_list = data["data"]["proxy_list"]
                        utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 成功获取到{len(proxy_list)}个代理IP")
                        
                        # 解析代理IP信息
                        ip_info_list = []
                        for proxy in proxy_list:
                            try:
                                ip, port = proxy.split(":")
                                # 计算过期时间（10分钟后）
                                expired_time_ts = int(time.time()) + 600
                                
                                ip_info = IpInfoModel(
                                    ip=ip,
                                    port=int(port),
                                    user=self.kdl_user_name,  # 使用user而不是username
                                    password=self.kdl_user_pwd,
                                    expired_time_ts=expired_time_ts  # 添加过期时间
                                )
                                ip_info_list.append(ip_info)
                                
                                # 缓存代理IP信息
                                cache_key = f"proxy:{ip}:{port}"
                                await self.ip_cache.set(cache_key, ip_info, expire_seconds=600)  # 10分钟过期
                                
                            except Exception as e:
                                utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 解析代理IP失败: {proxy}, 错误: {str(e)}")
                                continue
                        
                        return ip_info_list
                    else:
                        utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] API返回错误: {data}")
                else:
                    utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] API请求失败: {response.status_code}")
                
        except Exception as e:
            utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 获取代理IP失败: {str(e)}")
        
        return []


def new_kuai_daili_proxy() -> KuaiDaiLiProxy:
    """
    构造快代理HTTP实例
    Returns:

    """
    # 从环境变量获取凭证，如果不存在则使用默认值
    secret_id = os.getenv("kdl_secret_id", "ol8uttmcvpzmkj4cuv5v")
    signature = os.getenv("kdl_signature", "jrla2myvgayveubgpe8juycchplh9skz")
    username = os.getenv("kdl_user_name", "17688161544")
    password = os.getenv("kdl_user_pwd", "Hhlcom1234")
    
    utils.logger.info(f"使用快代理参数: secret_id={secret_id}, signature={signature}")
    utils.logger.info(f"用户名: {username}, 密码: {'*' * len(password) if password else '未设置'}")
    
    return KuaiDaiLiProxy(
        kdl_secret_id=secret_id,
        kdl_signature=signature,
        kdl_user_name=username,
        kdl_user_pwd=password,
    )
