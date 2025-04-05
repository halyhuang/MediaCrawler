import asyncio
import aiohttp
import requests
from tools import utils
import config

async def test_proxy():
    # 快代理API参数
    secret_id = "olwgz3serr0j2w3hddxa"
    signature = "3b4klhrsaed2lxsqowwmk66uezxoxf3h"
    
    # 构建API请求URL
    api_url = f"https://dps.kdlapi.com/api/getdps/?secret_id={secret_id}&signature={signature}&num=1&pt=1&sep=1"
    
    try:
        # 获取代理IP
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(api_url, headers=headers)
        if response.status_code != 200:
            utils.logger.error(f"获取代理失败: {response.text}")
            return
            
        proxy_ip = response.text.strip()
        if not proxy_ip:
            utils.logger.error("获取到的代理IP为空")
            return
            
        proxy_url = f"http://{proxy_ip}"
        utils.logger.info(f"获取到代理IP: {proxy_url}")
        
        # 测试代理连接
        async with aiohttp.ClientSession() as session:
            # 使用代理访问抖音
            proxy_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            async with session.get(
                "https://www.douyin.com",
                proxy=proxy_url,
                headers=proxy_headers,
                timeout=30,
                ssl=False
            ) as response:
                if response.status == 200:
                    utils.logger.info("代理连接成功！")
                    # 获取响应内容
                    content = await response.text()
                    utils.logger.info(f"响应内容长度: {len(content)}")
                else:
                    utils.logger.error(f"代理连接失败，状态码: {response.status}")
                    
            # 测试IP地址
            async with session.get(
                "http://httpbin.org/ip",
                proxy=proxy_url,
                headers=proxy_headers,
                timeout=30,
                ssl=False
            ) as response:
                if response.status == 200:
                    ip_info = await response.json()
                    utils.logger.info(f"当前代理IP: {ip_info.get('origin')}")
                else:
                    utils.logger.error("无法获取IP信息")
                    
    except Exception as e:
        utils.logger.error(f"代理测试失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_proxy()) 