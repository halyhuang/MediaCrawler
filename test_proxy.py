import asyncio
import aiohttp
import requests
import base64
import os
import urllib.parse
import json
import time
import random
from tools import utils
import config
from proxy.providers.kuaidl_proxy import new_kuai_daili_proxy

# 缓存文件路径
CACHE_FILE = "proxy_cache.json"

def clear_cache():
    """清除缓存文件"""
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            utils.logger.info("已清除代理IP缓存")
    except Exception as e:
        utils.logger.error(f"清除缓存失败: {str(e)}")

def load_cached_proxy():
    """从缓存文件加载代理IP"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache_data = json.load(f)
                # 检查缓存是否过期
                if cache_data.get("expire_time", 0) > time.time():
                    utils.logger.info(f"从缓存加载代理IP: {cache_data.get('proxy_ip')}")
                    return cache_data.get("proxy_ip")
                else:
                    utils.logger.info("缓存已过期，需要重新获取代理IP")
        except Exception as e:
            utils.logger.error(f"加载缓存失败: {str(e)}")
    return None

def save_proxy_to_cache(proxy_ip, expire_time):
    """保存代理IP到缓存文件"""
    try:
        cache_data = {
            "proxy_ip": proxy_ip,
            "expire_time": expire_time
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f)
        utils.logger.info(f"代理IP已缓存: {proxy_ip}, 过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_time))}")
    except Exception as e:
        utils.logger.error(f"保存缓存失败: {str(e)}")

def get_random_user_agent():
    """获取随机User-Agent"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ]
    return random.choice(user_agents)

async def test_proxy():
    # 从环境变量或配置文件中获取快代理参数
    secret_id = os.getenv("kdl_secret_id", "ol8uttmcvpzmkj4cuv5v")
    signature = os.getenv("kdl_signature", "jrla2myvgayveubgpe8juycchplh9skz")
    
    # 使用快代理官方示例中的用户名和密码
    username = "d2846629878"  # 官方示例中的用户名
    password = "fdaxmof2"     # 官方示例中的密码
    
    utils.logger.info(f"使用快代理参数: secret_id={secret_id}, signature={signature}")
    utils.logger.info(f"用户名: {username}, 密码: {'*' * len(password) if password else '未设置'}")
    
    # 尝试从缓存加载代理IP
    proxy_ip = load_cached_proxy()
    
    # 如果缓存中没有有效的代理IP，则从API获取
    if not proxy_ip:
        # 构建API请求URL
        api_url = f"https://dps.kdlapi.com/api/getdps/?secret_id={secret_id}&signature={signature}&num=1&pt=1&sep=1&format=json"
        
        try:
            # 获取代理IP
            headers = {
                "User-Agent": get_random_user_agent()
            }
            
            utils.logger.info("正在从快代理API获取代理IP...")
            response = requests.get(api_url, headers=headers)
            utils.logger.info(f"API响应: {response.text}")
            
            if response.status_code != 200:
                utils.logger.error(f"获取代理失败: {response.text}")
                return
                
            response_json = response.json()
            if response_json.get("code") != 0:
                utils.logger.error(f"获取代理失败，错误信息: {response_json.get('msg')}")
                return
                
            proxy_list = response_json.get("data", {}).get("proxy_list", [])
            if not proxy_list:
                utils.logger.error("获取到的代理IP列表为空")
                return
                
            proxy_ip = proxy_list[0]
            
            # 计算过期时间（假设代理IP有效期为10分钟）
            expire_time = time.time() + 600
            # 保存到缓存
            save_proxy_to_cache(proxy_ip, expire_time)
            
        except Exception as e:
            utils.logger.error(f"获取代理IP失败: {str(e)}")
            return
    
    # 构建代理URL
    proxy_url = f"http://{proxy_ip}"
    utils.logger.info(f"使用代理IP: {proxy_url}")
    
    # 方法1: 使用用户名密码认证（私密代理/独享代理）
    proxies1 = {
        "http": f"http://{username}:{password}@{proxy_ip}",
        "https": f"http://{username}:{password}@{proxy_ip}"
    }
    
    # 方法2: 使用隧道代理
    proxies2 = {
        "http": f"http://{username}:{password}@tps.kdlapi.com:15818",
        "https": f"http://{username}:{password}@tps.kdlapi.com:15818"
    }
    
    # 方法3: 使用base64编码的认证头
    auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Proxy-Authorization": f"Basic {auth_str}",
        "User-Agent": get_random_user_agent(),
        "Accept": "*/*",
        "Connection": "keep-alive"
    }
    
    proxies3 = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    utils.logger.info("已构建三种代理配置方式")
    
    # 测试代理连接 - 使用requests库
    utils.logger.info("正在使用requests库测试代理IP信息（方法1）...")
    try:
        # 首先测试httpbin.org
        r = requests.get("http://httpbin.org/ip", proxies=proxies1, timeout=30)
        if r.status_code == 200:
            ip_info = r.json()
            utils.logger.info(f"方法1成功，当前代理IP: {ip_info.get('origin')}")
        else:
            utils.logger.error(f"方法1失败，状态码: {r.status_code}")
            utils.logger.error(f"响应内容: {r.text}")
            
            # 如果是454错误，清除缓存并重新获取代理IP
            if r.status_code == 454:
                utils.logger.info("代理IP已失效，清除缓存并重新获取...")
                clear_cache()
                return await test_proxy()  # 递归调用，重新获取代理IP
            
            # 尝试方法2
            utils.logger.info("尝试方法2（隧道代理）...")
            try:
                # 增加连接超时时间
                r = requests.get("http://httpbin.org/ip", proxies=proxies2, timeout=60)
                if r.status_code == 200:
                    ip_info = r.json()
                    utils.logger.info(f"方法2成功，当前代理IP: {ip_info.get('origin')}")
                else:
                    utils.logger.error(f"方法2失败，状态码: {r.status_code}")
                    utils.logger.error(f"响应内容: {r.text}")
                    
                    # 尝试方法3
                    utils.logger.info("尝试方法3（base64认证头）...")
                    r = requests.get("http://httpbin.org/ip", proxies=proxies3, headers=headers, timeout=30)
                    if r.status_code == 200:
                        ip_info = r.json()
                        utils.logger.info(f"方法3成功，当前代理IP: {ip_info.get('origin')}")
                    else:
                        utils.logger.error(f"方法3失败，状态码: {r.status_code}")
                        utils.logger.error(f"响应内容: {r.text}")
                        
                        # 所有方法都失败，清除缓存并重新获取代理IP
                        utils.logger.info("所有方法都失败，清除缓存并重新获取代理IP...")
                        clear_cache()
                        return await test_proxy()  # 递归调用，重新获取代理IP
            except requests.exceptions.RequestException as e:
                utils.logger.error(f"方法2连接异常: {str(e)}")
                
                # 尝试方法3
                utils.logger.info("尝试方法3（base64认证头）...")
                try:
                    r = requests.get("http://httpbin.org/ip", proxies=proxies3, headers=headers, timeout=30)
                    if r.status_code == 200:
                        ip_info = r.json()
                        utils.logger.info(f"方法3成功，当前代理IP: {ip_info.get('origin')}")
                    else:
                        utils.logger.error(f"方法3失败，状态码: {r.status_code}")
                        utils.logger.error(f"响应内容: {r.text}")
                        
                        # 所有方法都失败，清除缓存并重新获取代理IP
                        utils.logger.info("所有方法都失败，清除缓存并重新获取代理IP...")
                        clear_cache()
                        return await test_proxy()  # 递归调用，重新获取代理IP
                except requests.exceptions.RequestException as e:
                    utils.logger.error(f"方法3连接异常: {str(e)}")
                    
                    # 所有方法都失败，清除缓存并重新获取代理IP
                    utils.logger.info("所有方法都失败，清除缓存并重新获取代理IP...")
                    clear_cache()
                    return await test_proxy()  # 递归调用，重新获取代理IP
    except Exception as e:
        utils.logger.error(f"使用requests库测试异常: {str(e)}")
        
        # 清除缓存并重新获取代理IP
        utils.logger.info("测试异常，清除缓存并重新获取代理IP...")
        clear_cache()
        return await test_proxy()  # 递归调用，重新获取代理IP
    
    # 测试代理连接抖音
    utils.logger.info("正在测试代理连接抖音...")
    try:
        # 使用成功的方法测试抖音
        if r.status_code == 200:
            # 确定使用哪种代理配置
            if "tps.kdlapi.com" in str(r.request.url):
                proxies = proxies2
                method = "隧道代理"
            elif "Proxy-Authorization" in str(r.request.headers):
                proxies = proxies3
                headers_to_use = headers
                method = "base64认证头"
            else:
                proxies = proxies1
                method = "用户名密码认证"
                
            utils.logger.info(f"使用{method}连接抖音...")
            
            # 抖音特定的请求头
            douyin_headers = {
                "User-Agent": get_random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
            
            # 合并请求头
            if method == "base64认证头":
                douyin_headers.update(headers_to_use)
            
            # 添加随机延迟
            time.sleep(random.uniform(1, 3))
            
            r = requests.get("https://www.douyin.com", proxies=proxies, headers=douyin_headers, timeout=30)
            if r.status_code == 200:
                utils.logger.info("代理连接抖音成功！")
                utils.logger.info(f"响应内容长度: {len(r.text)}")
            else:
                utils.logger.error(f"代理连接抖音失败，状态码: {r.status_code}")
                utils.logger.error(f"响应内容: {r.text}")
                
                # 如果是抖音特定的错误，尝试使用备用URL
                if r.status_code == 444:
                    utils.logger.info("尝试使用抖音备用URL...")
                    time.sleep(random.uniform(2, 4))
                    r = requests.get("https://www.douyin.com/discover", proxies=proxies, headers=douyin_headers, timeout=30)
                    if r.status_code == 200:
                        utils.logger.info("使用备用URL连接抖音成功！")
                        utils.logger.info(f"响应内容长度: {len(r.text)}")
                    else:
                        utils.logger.error(f"使用备用URL连接抖音失败，状态码: {r.status_code}")
                        utils.logger.error(f"响应内容: {r.text}")
    except Exception as e:
        utils.logger.error(f"代理连接抖音异常: {str(e)}")
    
    # 测试代理连接小红书
    utils.logger.info("正在测试代理连接小红书...")
    try:
        # 使用成功的方法测试小红书
        # 小红书特定的请求头
        xiaohongshu_headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
        
        # 合并请求头
        if method == "base64认证头":
            xiaohongshu_headers.update(headers_to_use)
        
        # 添加随机延迟
        time.sleep(random.uniform(1, 3))
        
        r = requests.get("https://www.xiaohongshu.com", proxies=proxies, headers=xiaohongshu_headers, timeout=30)
        if r.status_code == 200:
            utils.logger.info("代理连接小红书成功！")
            utils.logger.info(f"响应内容长度: {len(r.text)}")
        else:
            utils.logger.error(f"代理连接小红书失败，状态码: {r.status_code}")
            utils.logger.error(f"响应内容: {r.text}")
    except Exception as e:
        utils.logger.error(f"代理连接小红书异常: {str(e)}")
    
    # 测试使用项目中的快代理提供者
    utils.logger.info("正在测试项目中的快代理提供者...")
    try:
        # 修改快代理提供者的API调用
        proxy_provider = new_kuai_daili_proxy()
        # 确保API调用格式正确
        proxies = await proxy_provider.get_proxies(1)
        if proxies:
            proxy = proxies[0]
            utils.logger.info(f"成功获取到代理: {proxy.ip}:{proxy.port}")
            utils.logger.info(f"代理过期时间: {proxy.expired_time_ts}")
        else:
            utils.logger.error("未能获取到代理")
    except Exception as e:
        utils.logger.error(f"测试项目中的快代理提供者失败: {str(e)}")
                    
    except Exception as e:
        utils.logger.error(f"代理测试失败: {str(e)}")
        utils.logger.error(f"错误详情: ", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_proxy()) 