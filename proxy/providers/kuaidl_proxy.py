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

    async def get_proxies(self, num: int) -> List[IpInfoModel]:
        """
        快代理实现
        Args:
            num:

        Returns:

        """
        uri = "/api/getdps/"

        # 优先从缓存中拿 IP
        ip_cache_list = self.ip_cache.load_all_ip(proxy_brand_name=self.proxy_brand_name)
        if len(ip_cache_list) >= num:
            utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 从缓存中获取到 {len(ip_cache_list)} 个代理IP")
            return ip_cache_list[:num]

        # 如果缓存中的数量不够，从IP代理商获取补上，再存入缓存中
        need_get_count = num - len(ip_cache_list)
        
        # 构建API请求URL
        api_url = f"{self.api_base}{uri}?secret_id={self.secret_id}&signature={self.signature}&num={need_get_count}&pt=1&sep=1&format=json"
        
        ip_infos: List[IpInfoModel] = []
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 尝试从快代理API获取代理IP，URL: {api_url}")
                    response = await client.get(api_url)

                    if response.status_code != 200:
                        utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 状态码不是200，响应内容: {response.text}")
                        retry_count += 1
                        if retry_count < max_retries:
                            utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 第{retry_count}次重试...")
                            await asyncio.sleep(2)  # 等待2秒后重试
                            continue
                        else:
                            # 如果重试次数用完，尝试使用缓存中的IP
                            if ip_cache_list:
                                utils.logger.warning(f"[KuaiDaiLiProxy.get_proxies] API请求失败，使用缓存中的{len(ip_cache_list)}个代理IP")
                                return ip_cache_list[:num]
                            else:
                                raise Exception("get ip error from proxy provider and status code not 200 ...")

                    ip_response: Dict = response.json()
                    if ip_response.get("code") != 0:
                        utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 响应码不是0，消息: {ip_response.get('msg')}")
                        retry_count += 1
                        if retry_count < max_retries:
                            utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 第{retry_count}次重试...")
                            await asyncio.sleep(2)  # 等待2秒后重试
                            continue
                        else:
                            # 如果重试次数用完，尝试使用缓存中的IP
                            if ip_cache_list:
                                utils.logger.warning(f"[KuaiDaiLiProxy.get_proxies] API请求失败，使用缓存中的{len(ip_cache_list)}个代理IP")
                                return ip_cache_list[:num]
                            else:
                                raise Exception("get ip error from proxy provider and code not 0 ...")

                    proxy_list: List[str] = ip_response.get("data", {}).get("proxy_list", [])
                    if not proxy_list:
                        utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 代理IP列表为空，响应内容: {ip_response}")
                        retry_count += 1
                        if retry_count < max_retries:
                            utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 第{retry_count}次重试...")
                            await asyncio.sleep(2)  # 等待2秒后重试
                            continue
                        else:
                            # 如果重试次数用完，尝试使用缓存中的IP
                            if ip_cache_list:
                                utils.logger.warning(f"[KuaiDaiLiProxy.get_proxies] API请求失败，使用缓存中的{len(ip_cache_list)}个代理IP")
                                return ip_cache_list[:num]
                            else:
                                raise Exception("get ip error from proxy provider and proxy list is empty ...")
                    
                    utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 成功获取到{len(proxy_list)}个代理IP")
                    
                    for proxy in proxy_list:
                        try:
                            proxy_model = parse_kuaidaili_proxy(proxy)
                            ip_info_model = IpInfoModel(
                                ip=proxy_model.ip,
                                port=proxy_model.port,
                                user=self.kdl_user_name,
                                password=self.kdl_user_pwd,
                                expired_time_ts=proxy_model.expire_ts,
                            )
                            ip_key = f"{self.proxy_brand_name}_{ip_info_model.ip}_{ip_info_model.port}"
                            self.ip_cache.set_ip(ip_key, ip_info_model.model_dump_json(), ex=ip_info_model.expired_time_ts)
                            ip_infos.append(ip_info_model)
                        except Exception as e:
                            utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 解析代理IP失败: {proxy}, 错误: {str(e)}")
                            continue
                    
                    break  # 成功获取代理IP，跳出循环
            except Exception as e:
                utils.logger.error(f"[KuaiDaiLiProxy.get_proxies] 请求快代理API异常: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    utils.logger.info(f"[KuaiDaiLiProxy.get_proxies] 第{retry_count}次重试...")
                    await asyncio.sleep(2)  # 等待2秒后重试
                else:
                    # 如果重试次数用完，尝试使用缓存中的IP
                    if ip_cache_list:
                        utils.logger.warning(f"[KuaiDaiLiProxy.get_proxies] API请求失败，使用缓存中的{len(ip_cache_list)}个代理IP")
                        return ip_cache_list[:num]
                    else:
                        raise Exception(f"get ip error from proxy provider: {str(e)}")

        return ip_cache_list + ip_infos


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
