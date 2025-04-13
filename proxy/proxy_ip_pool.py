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
# @Time    : 2023/12/2 13:45
# @Desc    : ip代理池实现
import random
from typing import Dict, List
import os
import json
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed
import base64
import requests  # 添加requests库导入

import config
from proxy.providers import new_jisu_http_proxy, new_kuai_daili_proxy
from tools import utils

from .base_proxy import ProxyProvider
from .types import IpInfoModel, ProviderNameEnum

# 缓存文件路径
CACHE_FILE = "proxy_pool_cache.json"

class ProxyIpPool:
    def __init__(self, ip_pool_count: int, enable_validate_ip: bool, ip_provider: ProxyProvider) -> None:
        """
        初始化代理IP池
        Args:
            ip_pool_count: 代理池数量
            enable_validate_ip: 是否启用IP验证
            ip_provider: 代理提供者
        """
        self.valid_ip_url = "https://httpbin.org/ip"  # 验证IP是否有效的URL
        self.ip_pool_count = ip_pool_count
        self.enable_validate_ip = enable_validate_ip
        self.proxy_list: List[IpInfoModel] = []
        self.ip_provider: ProxyProvider = ip_provider
        self.cache_file = CACHE_FILE

    def clear_cache(self):
        """清除缓存文件"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                utils.logger.info("已清除代理IP缓存")
        except Exception as e:
            utils.logger.error(f"清除缓存失败: {str(e)}")

    def load_cached_proxies(self):
        """从缓存文件加载代理IP列表"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                    # 检查缓存是否过期
                    if cache_data.get("expire_time", 0) > time.time():
                        proxy_list_data = cache_data.get("proxy_list", [])
                        utils.logger.info(f"从缓存加载代理IP列表，共{len(proxy_list_data)}个")
                        # 将字典数据转换回IpInfoModel对象
                        self.proxy_list = [IpInfoModel(**proxy_data) for proxy_data in proxy_list_data]
                        return True
                    else:
                        utils.logger.info("缓存已过期，需要重新获取代理IP")
            except Exception as e:
                utils.logger.error(f"加载缓存失败: {str(e)}")
        return False

    def save_proxies_to_cache(self, expire_time=None):
        """保存代理IP列表到缓存文件"""
        try:
            if not expire_time:
                # 默认缓存10分钟
                expire_time = time.time() + 600
                
            # 将IpInfoModel对象转换为字典
            proxy_list_data = [proxy.__dict__ for proxy in self.proxy_list]
            
            cache_data = {
                "proxy_list": proxy_list_data,
                "expire_time": expire_time
            }
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f)
            utils.logger.info(f"代理IP列表已缓存，共{len(self.proxy_list)}个，过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_time))}")
        except Exception as e:
            utils.logger.error(f"保存缓存失败: {str(e)}")

    async def load_proxies(self) -> None:
        """
        加载IP代理
        Returns:
        """
        # 首先尝试从缓存加载
        # if self.load_cached_proxies():
        #     return
            
        # 如果缓存中没有有效的代理，则从API获取
        self.proxy_list = await self.ip_provider.get_proxies(self.ip_pool_count)
        
        # 保存到缓存
        # self.save_proxies_to_cache()

    async def _is_valid_proxy(self, proxy: IpInfoModel) -> bool:
        """
        验证代理IP是否有效
        :param proxy:
        :return:
        """
        utils.logger.info(f"[ProxyIpPool._is_valid_proxy] testing {proxy.ip} is it valid ")
        try:
            # 使用与test_proxy.py完全相同的配置
            proxy_ip = f"{proxy.ip}:{proxy.port}"
            utils.logger.info(f"使用代理IP: {proxy_ip}")
            
            # 记录代理信息，用于调试
            utils.logger.info(f"代理信息: IP={proxy.ip}, 端口={proxy.port}, 用户名={proxy.user}, 密码={'*' * len(proxy.password) if proxy.password else '未设置'}")
            
            # 添加请求头，避免使用隧道模式
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Connection": "close"  # 使用close而不是keep-alive，避免隧道模式
            }
            
            # 方法1: 使用用户名密码认证（私密代理/独享代理）
            proxies1 = {
                "http": f"http://{proxy.user}:{proxy.password}@{proxy_ip}",
                "https": f"http://{proxy.user}:{proxy.password}@{proxy_ip}"
            }
            
            # 记录完整的代理URL，用于调试
            utils.logger.info(f"方法1代理URL: {proxies1['http']}")
            
            # 首先尝试方法1
            utils.logger.info("测试方法1（用户名密码认证）...")
            try:
                response = requests.get(self.valid_ip_url, proxies=proxies1, headers=headers, timeout=30.0, verify=False)
                if response.status_code == 200:
                    utils.logger.info(f"方法1成功，当前代理IP: {response.json().get('origin')}")
                    return True
                else:
                    utils.logger.error(f"方法1失败，状态码: {response.status_code}")
                    utils.logger.error(f"响应内容: {response.text}")
                    
                    # 如果是407错误，尝试其他方法
                    if response.status_code == 407:
                        utils.logger.info("检测到407错误，尝试其他认证方法...")
            except requests.exceptions.ProxyError as e:
                if "407 Proxy Authentication Required" in str(e):
                    utils.logger.error(f"方法1连接异常: 407 Proxy Authentication Required")
                    utils.logger.info("检测到407错误，尝试其他认证方法...")
                else:
                    utils.logger.error(f"方法1连接异常: {str(e)}")
            except Exception as e:
                utils.logger.error(f"方法1连接异常: {str(e)}")
            
            # 如果方法1失败，尝试方法2（隧道代理）
            utils.logger.info("尝试方法2（隧道代理）...")
            proxies2 = {
                "http": f"http://{proxy.user}:{proxy.password}@tps.kdlapi.com:15818",
                "https": f"http://{proxy.user}:{proxy.password}@tps.kdlapi.com:15818"
            }
            
            # 记录完整的代理URL，用于调试
            utils.logger.info(f"方法2代理URL: {proxies2['http']}")
            
            try:
                response = requests.get(self.valid_ip_url, proxies=proxies2, headers=headers, timeout=60.0, verify=False)
                if response.status_code == 200:
                    utils.logger.info(f"方法2成功，当前代理IP: {response.json().get('origin')}")
                    return True
                else:
                    utils.logger.error(f"方法2失败，状态码: {response.status_code}")
                    utils.logger.error(f"响应内容: {response.text}")
                    
                    # 如果是407错误，尝试其他方法
                    if response.status_code == 407:
                        utils.logger.info("检测到407错误，尝试其他认证方法...")
            except requests.exceptions.ProxyError as e:
                if "407 Proxy Authentication Required" in str(e):
                    utils.logger.error(f"方法2连接异常: 407 Proxy Authentication Required")
                    utils.logger.info("检测到407错误，尝试其他认证方法...")
                else:
                    utils.logger.error(f"方法2连接异常: {str(e)}")
            except Exception as e:
                utils.logger.error(f"方法2连接异常: {str(e)}")
            
            # 如果方法2失败，尝试方法3（base64认证头）
            utils.logger.info("尝试方法3（base64认证头）...")
            auth_str = base64.b64encode(f"{proxy.user}:{proxy.password}".encode()).decode()
            headers_with_auth = headers.copy()
            headers_with_auth["Proxy-Authorization"] = f"Basic {auth_str}"
            
            proxies3 = {
                "http": f"http://{proxy_ip}",
                "https": f"http://{proxy_ip}"
            }
            
            # 记录完整的代理URL和认证头，用于调试
            utils.logger.info(f"方法3代理URL: {proxies3['http']}")
            utils.logger.info(f"方法3认证头: Basic {auth_str[:5]}...")
            
            try:
                response = requests.get(self.valid_ip_url, proxies=proxies3, headers=headers_with_auth, timeout=30.0, verify=False)
                if response.status_code == 200:
                    utils.logger.info(f"方法3成功，当前代理IP: {response.json().get('origin')}")
                    return True
                else:
                    utils.logger.error(f"方法3失败，状态码: {response.status_code}")
                    utils.logger.error(f"响应内容: {response.text}")
                    
                    # 如果是407错误，尝试其他方法
                    if response.status_code == 407:
                        utils.logger.info("检测到407错误，尝试其他认证方法...")
            except requests.exceptions.ProxyError as e:
                if "407 Proxy Authentication Required" in str(e):
                    utils.logger.error(f"方法3连接异常: 407 Proxy Authentication Required")
                    utils.logger.info("检测到407错误，尝试其他认证方法...")
                else:
                    utils.logger.error(f"方法3连接异常: {str(e)}")
            except Exception as e:
                utils.logger.error(f"方法3连接异常: {str(e)}")
            
            # 所有方法都失败
            utils.logger.error("所有代理方法都失败")
            return False
        except Exception as e:
            utils.logger.info(f"[ProxyIpPool._is_valid_proxy] testing {proxy.ip} err: {e}")
            raise e

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_proxy(self) -> IpInfoModel:
        """
        从代理池中随机提取一个代理IP
        :return:
        """
        if len(self.proxy_list) == 0:
            await self._reload_proxies()

        proxy = random.choice(self.proxy_list)
        self.proxy_list.remove(proxy) # 取出来一个IP就应该移出掉
        if self.enable_validate_ip:
            if not await self._is_valid_proxy(proxy):
                raise Exception("[ProxyIpPool.get_proxy] current ip invalid and again get it")
        return proxy

    async def _reload_proxies(self):
        """
        # 重新加载代理池
        :return:
        """
        # 清除缓存
        self.clear_cache()
        
        # 重新加载代理
        self.proxy_list = []
        await self.load_proxies()

    async def verify_cookie(self) -> bool:
        """验证Cookie是否有效"""
        try:
            url = "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo"
            headers = {
                "User-Agent": self.user_agent,
                "Cookie": self.cookie_str,
                "Referer": "https://www.xiaohongshu.com"
            }
            
            async with httpx.AsyncClient(proxies=self.proxies, timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                return response.status_code == 200 and 'application/json' in response.headers.get('content-type', '')
                
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.verify_cookie] Error: {e}")
            return False

IpProxyProvider: Dict[str, ProxyProvider] = {
    ProviderNameEnum.JISHU_HTTP_PROVIDER.value: new_jisu_http_proxy(),
    ProviderNameEnum.KUAI_DAILI_PROVIDER.value: new_kuai_daili_proxy()
}


async def create_ip_pool(ip_pool_count: int, enable_validate_ip: bool) -> ProxyIpPool:
    """
     创建 IP 代理池
    :param ip_pool_count: ip池子的数量
    :param enable_validate_ip: 是否开启验证IP代理
    :return:
    """
    pool = ProxyIpPool(ip_pool_count=ip_pool_count,
                       enable_validate_ip=enable_validate_ip,
                       ip_provider=IpProxyProvider.get(config.IP_PROXY_PROVIDER_NAME)
                       )
    pool.clear_cache()  # 清除缓存
    await pool.load_proxies()  # 重新加载代理
    return pool


if __name__ == '__main__':
    pass
