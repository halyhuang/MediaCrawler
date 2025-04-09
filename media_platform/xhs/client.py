# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import asyncio
import json
import re
import random
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlencode

import httpx
from playwright.async_api import BrowserContext, Page
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_result

import config
from base.base_crawler import AbstractApiClient
from tools import utils
from html import unescape

from .exception import DataFetchError, IPBlockError
from .field import SearchNoteType, SearchSortType
from .help import get_search_id, sign


class XiaoHongShuClient(AbstractApiClient):
    def __init__(
        self,
        timeout=30,
        proxies=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.headers = headers
        self._host = "https://edith.xiaohongshu.com"
        self._domain = "https://www.xiaohongshu.com"
        self.IP_ERROR_STR = "网络连接异常，请检查网络设置或重启试试"
        self.IP_ERROR_CODE = 300012
        self.NOTE_ABNORMAL_STR = "笔记状态异常，请稍后查看"
        self.NOTE_ABNORMAL_CODE = -510001
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self.last_request_time = time.time()
        self.request_count = 0
        self.last_reset_time = time.time()
        self.request_limit = 50  # 每5分钟最多50个请求
        self.reset_interval = 300  # 5分钟重置一次
        self.last_user_agent_change = time.time()
        self.user_agent_change_interval = 60  # 每60秒更换一次UA
        
        # 补充必要的请求头
        self.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site"
        })

    async def _check_rate_limit(self):
        """检查请求频率限制"""
        current_time = time.time()
        
        # 重置计数器
        if current_time - self.last_reset_time >= self.reset_interval:
            self.request_count = 0
            self.last_reset_time = current_time
            
        # 检查是否超过限制
        if self.request_count >= self.request_limit:
            wait_time = self.reset_interval - (current_time - self.last_reset_time)
            if wait_time > 0:
                utils.logger.info(f"[XiaoHongShuClient._check_rate_limit] Rate limit reached, waiting for {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
                self.request_count = 0
                self.last_reset_time = time.time()
        
        self.request_count += 1

    async def _manage_user_agent(self):
        """管理User-Agent的更换"""
        current_time = time.time()
        if current_time - self.last_user_agent_change >= self.user_agent_change_interval:
            await self._rotate_user_agent()
            self.last_user_agent_change = current_time

    async def _handle_request_error(self, response, retry_count, max_retries):
        """处理请求错误"""
        if response.status_code == 406:
            utils.logger.warning(f"[XiaoHongShuClient._handle_request_error] 406 error encountered, retry {retry_count}/{max_retries}")
            # 更新cookie和headers
            await self.update_cookies(self.playwright_page.context)
            await self._manage_user_agent()
            # 增加延迟
            await asyncio.sleep(random.uniform(10, 15))
            return True
            
        return False

    async def _rotate_user_agent(self):
        """随机轮换User-Agent"""
        self.headers["User-Agent"] = random.choice(config.USER_AGENTS)
        utils.logger.info(f"[XiaoHongShuClient._rotate_user_agent] Rotated User-Agent: {self.headers['User-Agent']}")

    async def simulate_user_behavior(self):
        """模拟真实用户行为"""
        try:
            random_page = random.choice(config.RANDOM_PAGES)
            utils.logger.info(f"[XiaoHongShuClient.simulate_user_behavior] Visiting random page: {random_page}")
            await self.playwright_page.goto(random_page)
            await asyncio.sleep(random.uniform(2, 5))
            
            # 模拟滚动
            for _ in range(random.randint(2, 5)):
                await self.playwright_page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(random.uniform(1, 3))
                
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.simulate_user_behavior] Error: {str(e)}")

    async def _wait_between_requests(self):
        """控制请求间隔"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < config.REQUEST_MIN_INTERVAL:
            wait_time = random.uniform(
                config.REQUEST_MIN_INTERVAL - time_since_last_request,
                config.REQUEST_MAX_INTERVAL - time_since_last_request
            )
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()

    async def _pre_headers(self, url: str, data=None) -> Dict:
        """
        请求头参数签名
        """
        try:
            # 获取页面上下文中的签名数据
            sign_data = await self.playwright_page.evaluate("""
                () => {
                    const data = {};
                    if (window._XSDATA) {
                        data.xs = window._XSDATA.xs || '';
                        data.xt = window._XSDATA.xt || '';
                        data.xsCommon = window._XSDATA.xsCommon || '';
                    }
                    return data;
                }
            """)
            
            if not sign_data.get("xs"):
                utils.logger.warning("[XiaoHongShuClient._pre_headers] 未获取到签名数据，尝试重新获取")
                # 尝试重新获取签名数据
                await self.playwright_page.reload(wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)
                sign_data = await self.playwright_page.evaluate("() => window._XSDATA || {}")
            
            # 使用页面中的签名数据
            headers = {
                "X-S": sign_data.get("xs", ""),
                "X-T": sign_data.get("xt", str(int(time.time()))),
                "X-S-Common": sign_data.get("xsCommon", ""),
                "X-B3-Traceid": str(random.randint(100000, 999999))
            }
            
            self.headers.update(headers)
            return headers
            
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient._pre_headers] 获取签名数据失败: {str(e)}")
            return await super()._pre_headers(url, data)

    async def request(
        self,
        method: str,
        url: str,
        return_response: bool = False,
        max_retries: int = 3,
        **kwargs,
    ) -> Union[Dict, str]:
        await self._check_rate_limit()  # 检查频率限制
        await self._manage_user_agent()  # 管理User-Agent
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                # 添加随机延迟
                await asyncio.sleep(random.uniform(2, 5))
                
                # 随机添加一些额外的请求头
                temp_headers = self.headers.copy()
                if random.random() < 0.3:  # 30%的概率添加额外header
                    temp_headers.update({
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "Accept-Encoding": "gzip, deflate, br"
                    })
                
                kwargs['headers'] = temp_headers
                
                async with httpx.AsyncClient(proxies=self.proxies, follow_redirects=False) as client:
                    response = await client.request(method, url, timeout=self.timeout, **kwargs)

                # 处理302重定向到验证码页面的情况
                if response.status_code == 302:
                    redirect_url = response.headers.get("Location", "")
                    if "captcha" in redirect_url:
                        utils.logger.warning(f"[XiaoHongShuClient.request] 遇到验证码重定向，尝试处理...")
                        
                        # 解析验证码信息
                        try:
                            from urllib.parse import urlparse, parse_qs
                            parsed_url = urlparse(redirect_url)
                            query_params = parse_qs(parsed_url.query)
                            verify_type = query_params.get("verifyType", [""])[0]
                            verify_uuid = query_params.get("verifyUuid", [""])[0]
                            
                            # 记录验证码信息
                            utils.logger.info(f"[XiaoHongShuClient.request] 验证码类型: {verify_type}, UUID: {verify_uuid}")
                            
                            # 如果是在无头模式下运行
                            if config.HEADLESS:
                                utils.logger.error("[XiaoHongShuClient.request] 在无头模式下无法处理验证码，切换到有界面模式")
                                raise DataFetchError("在无头模式下无法处理验证码")
                            
                            # 使用Playwright打开验证码页面
                            await self.playwright_page.goto(redirect_url)
                            
                            # 等待用户处理验证码
                            max_wait_time = 60
                            check_interval = 5
                            for _ in range(max_wait_time // check_interval):
                                current_url = self.playwright_page.url
                                if "captcha" not in current_url:
                                    utils.logger.info("[XiaoHongShuClient.request] 验证码已处理成功")
                                    # 更新cookie
                                    await self.update_cookies(self.playwright_page.context)
                                    # 重新尝试原始请求
                                    continue
                                
                                await asyncio.sleep(check_interval)
                            
                            utils.logger.error("[XiaoHongShuClient.request] 验证码处理超时")
                            raise DataFetchError("验证码处理超时")
                            
                        except Exception as e:
                            utils.logger.error(f"[XiaoHongShuClient.request] 处理验证码过程中出错: {str(e)}")
                            raise
                
                # 处理其他错误状态码
                if response.status_code != 200:
                    if await self._handle_request_error(response, retry_count, max_retries):
                        retry_count += 1
                        continue
                    else:
                        utils.logger.error(f"[XiaoHongShuClient.request] Request failed with status code: {response.status_code}, response: {response.text}")
                        raise DataFetchError(f"Request failed with status code: {response.status_code}")

                if return_response:
                    return response.text
                    
                try:
                    data: Dict = response.json()
                except json.JSONDecodeError as e:
                    utils.logger.error(f"[XiaoHongShuClient.request] Failed to parse JSON response: {str(e)}, response: {response.text}")
                    retry_count += 1
                    await asyncio.sleep(5)
                    continue

                if data.get("success"):
                    return data.get("data", data.get("success", {}))
                elif data.get("code") == self.IP_ERROR_CODE:
                    raise IPBlockError(self.IP_ERROR_STR)
                else:
                    error_msg = data.get("msg", "Unknown error")
                    utils.logger.error(f"[XiaoHongShuClient.request] API error: {error_msg}")
                    raise DataFetchError(error_msg)
                    
            except httpx.RequestError as e:
                utils.logger.error(f"[XiaoHongShuClient.request] Request error: {str(e)}")
                retry_count += 1
                await asyncio.sleep(random.uniform(5, 10))
                continue
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuClient.request] Unexpected error: {str(e)}")
                raise

        raise DataFetchError(f"Failed after {max_retries} retries")

    async def get(self, uri: str, params=None) -> Dict:
        """
        GET请求，对请求头签名
        Args:
            uri: 请求路由
            params: 请求参数

        Returns:

        """
        final_uri = uri
        if isinstance(params, dict):
            final_uri = f"{uri}?" f"{urlencode(params)}"
        headers = await self._pre_headers(final_uri)
        return await self.request(
            method="GET", url=f"{self._host}{final_uri}", headers=headers
        )

    async def post(self, uri: str, data: dict, **kwargs) -> Dict:
        """
        POST请求，对请求头签名
        Args:
            uri: 请求路由
            data: 请求体参数

        Returns:

        """
        headers = await self._pre_headers(uri, data)
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self.request(
            method="POST",
            url=f"{self._host}{uri}",
            data=json_str,
            headers=headers,
            **kwargs,
        )

    async def get_note_media(self, url: str) -> Union[bytes, None]:
        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request("GET", url, timeout=self.timeout)
            if not response.reason_phrase == "OK":
                utils.logger.error(
                    f"[XiaoHongShuClient.get_note_media] request {url} err, res:{response.text}"
                )
                return None
            else:
                return response.content

    async def pong(self) -> bool:
        """
        用于检查登录态是否失效了
        Returns:

        """
        """get a note to check if login state is ok"""
        utils.logger.info("[XiaoHongShuClient.pong] Begin to pong xhs...")
        ping_flag = False
        try:
            note_card: Dict = await self.get_note_by_keyword(keyword="小红书")
            if note_card.get("items"):
                ping_flag = True
        except Exception as e:
            utils.logger.error(
                f"[XiaoHongShuClient.pong] Ping xhs failed: {e}, and try to login again..."
            )
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        """
        API客户端提供的更新cookies方法，一般情况下登录成功后会调用此方法
        Args:
            browser_context: 浏览器上下文对象

        Returns:

        """
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        search_id: str = get_search_id(),
        page: int = 1,
        page_size: int = 20,
        sort: SearchSortType = SearchSortType.GENERAL,
        note_type: SearchNoteType = SearchNoteType.ALL,
    ) -> Dict:
        """
        根据关键词搜索笔记
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 1. 预热阶段 - 模拟真实用户搜索行为
                try:
                    # 访问首页并等待加载完成
                    await self.playwright_page.goto(
                        "https://www.xiaohongshu.com",
                        wait_until="domcontentloaded",
                        timeout=60000
                    )
                    
                    # 等待页面基本元素加载
                    try:
                        await self.playwright_page.wait_for_selector("body", timeout=10000)
                    except Exception as e:
                        utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 等待body元素超时: {str(e)}")
                    
                    # 等待一段时间让页面继续加载
                    await asyncio.sleep(random.uniform(3, 5))
                    
                    # 注入辅助函数
                    await self.playwright_page.evaluate("""
                        window._waitForXSDATA = function(timeout = 10000) {
                            return new Promise((resolve, reject) => {
                                const startTime = Date.now();
                                const checkXSDATA = () => {
                                    if (window._XSDATA) {
                                        resolve(window._XSDATA);
                                    } else if (Date.now() - startTime > timeout) {
                                        reject(new Error('等待XSDATA超时'));
                                    } else {
                                        setTimeout(checkXSDATA, 100);
                                    }
                                };
                                checkXSDATA();
                            });
                        };
                    """)
                    
                    # 等待XSDATA加载
                    try:
                        xs_data = await self.playwright_page.evaluate("window._waitForXSDATA()")
                        utils.logger.info("[XiaoHongShuClient.get_note_by_keyword] 成功获取XSDATA数据")
                    except Exception as e:
                        utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 等待XSDATA超时: {str(e)}")
                        # 尝试触发页面交互以加载XSDATA
                        await self.playwright_page.mouse.move(random.randint(100, 500), random.randint(100, 500))
                        await asyncio.sleep(2)
                        xs_data = await self.playwright_page.evaluate("window._XSDATA || {}")
                    
                    # 获取初始化数据
                    initial_data = await self.playwright_page.evaluate("""
                        () => {
                            const data = {};
                            try {
                                data.webId = window.localStorage.getItem('webId') || '';
                                data.websiteConfig = window._globalConfig || {};
                                data.extraHeaders = window.__INITIAL_STATE__ || {};
                                data.xsData = window._XSDATA || {};
                                data.cookies = document.cookie;
                            } catch (e) {
                                console.error('获取初始化数据失败:', e);
                            }
                            return data;
                        }
                    """)
                    
                    if not initial_data.get("xsData"):
                        utils.logger.warning("[XiaoHongShuClient.get_note_by_keyword] 未获取到签名数据，尝试重新加载页面")
                        # 清除缓存和cookie
                        await self.playwright_page.context.clear_cookies()
                        await self.playwright_page.evaluate("() => localStorage.clear()")
                        await self.playwright_page.evaluate("() => sessionStorage.clear()")
                        
                        # 重新加载页面
                        await self.playwright_page.reload(wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(random.uniform(2, 4))
                        
                        # 重新等待XSDATA
                        try:
                            xs_data = await self.playwright_page.evaluate("window._waitForXSDATA()")
                            utils.logger.info("[XiaoHongShuClient.get_note_by_keyword] 重新加载后成功获取XSDATA数据")
                        except Exception as e:
                            utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] 重新加载后仍未获取到XSDATA: {str(e)}")
                    
                    # 直接访问搜索结果页
                    encoded_keyword = urllib.parse.quote(keyword)
                    search_url = f"https://www.xiaohongshu.com/search_result?keyword={encoded_keyword}&source=web_search&sort=general"
                    
                    # 使用更宽松的加载策略
                    await self.playwright_page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )
                    
                    # 等待搜索结果加载
                    try:
                        await self.playwright_page.wait_for_selector(".search-result-container", timeout=10000)
                    except Exception as e:
                        utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 等待搜索结果超时: {str(e)}")
                    
                    await asyncio.sleep(random.uniform(2, 4))
                    
                    # 模拟滚动
                    for _ in range(random.randint(2, 4)):
                        await self.playwright_page.evaluate("""
                            () => {
                                const scrollHeight = Math.floor(Math.random() * 300) + 100;
                                window.scrollBy({
                                    top: scrollHeight,
                                    behavior: 'smooth'
                                });
                            }
                        """)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                    # 获取搜索页面的关键数据
                    search_data = await self.playwright_page.evaluate("""
                        () => {
                            const data = {};
                            try {
                                data.searchData = window.__INITIAL_STATE__ || {};
                                data.sign = window._XSDATA || {};
                                data.cookies = document.cookie;
                            } catch (e) {
                                console.error('获取搜索数据失败:', e);
                            }
                            return data;
                        }
                    """)
                    
                    # 更新cookie和localStorage
                    await self.update_cookies(self.playwright_page.context)
                    
                except Exception as e:
                    utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 预热阶段出错: {str(e)}")
                
                # 2. 构建搜索参数
                uri = "/api/sns/web/v1/search/notes"
                
                # 获取必要的参数
                try:
                    local_storage = await self.playwright_page.evaluate("() => window.localStorage")
                    web_session = local_storage.get("web_session", "")
                    device_id = local_storage.get("deviceId", str(random.randint(100000, 999999)))
                    web_id = local_storage.get("webId", "")
                except Exception as e:
                    utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 获取localStorage失败: {str(e)}")
                    web_session = ""
                    device_id = str(random.randint(100000, 999999))
                    web_id = ""
                
                current_timestamp = int(time.time() * 1000)
                data = {
                    "keyword": keyword,
                    "page": page,
                    "page_size": page_size,
                    "search_id": search_id,
                    "sort": "general",
                    "note_type": "0",
                    "image_formats": ["jpg", "webp", "avif"],
                    "device_fingerprint": str(current_timestamp),
                    "source": "web_search",
                    "search_type": "1",
                    "cursor": str((page - 1) * page_size),
                    "api_extra_params": {
                        "aaid": web_id,
                        "did": device_id,
                        "device_id": device_id,
                        "device_fingerprint": str(current_timestamp),
                        "channel": "web",
                        "sid": web_session or str(random.randint(1000000, 9999999)),
                        "t": str(int(current_timestamp / 1000)),
                        "platform": "web",
                        "build_version": "2.20.0",
                        "web_id": web_id
                    }
                }
                
                # 3. 准备请求头
                headers = self.headers.copy()
                headers.update({
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Origin": "https://www.xiaohongshu.com",
                    "Referer": f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(keyword)}",
                    "X-B3-TraceId": f"{random.randint(100000, 999999)}",
                    "X-S": "",
                    "X-T": str(int(current_timestamp / 1000)),
                    "X-Bd-Traceid": str(random.randint(100000, 999999)),
                    "X-Bd-Traceparent": f"00-{random.randint(100000, 999999)}-{random.randint(100000, 999999)}-01",
                    "X-Sign": "",
                    "X-Sign-Version": "1.0",
                    "X-Xsrf-Token": self.cookie_dict.get("xsrf_token", ""),
                })
                
                # 4. 发起搜索请求
                utils.logger.info(f"[XiaoHongShuClient.get_note_by_keyword] 开始搜索关键词: {keyword}, 页码: {page}")
                
                # 获取签名头
                signed_headers = await self._pre_headers(uri, data)
                headers.update(signed_headers)
                
                response = await self.post(uri, data)
                
                # 5. 处理响应
                if not response:
                    utils.logger.warning("[XiaoHongShuClient.get_note_by_keyword] 搜索响应为空")
                    retry_count += 1
                    await self._handle_empty_response()
                    continue
                    
                if isinstance(response, dict):
                    items = response.get("items", [])
                    if not items:
                        utils.logger.warning(f"[XiaoHongShuClient.get_note_by_keyword] 未找到搜索结果，响应: {response}")
                        if retry_count < max_retries - 1:
                            retry_count += 1
                            await self._handle_empty_response()
                            continue
                    else:
                        utils.logger.info(f"[XiaoHongShuClient.get_note_by_keyword] 成功获取到 {len(items)} 条搜索结果")
                        # 处理搜索结果
                        for item in items:
                            if "model_type" in item and item["model_type"] in ("rec_query", "hot_query"):
                                continue
                            # 补充必要的字段
                            item["search_id"] = search_id
                            item["keyword"] = keyword
                            
                        return response
                        
                return response
                
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] 搜索出错: {str(e)}")
                retry_count += 1
                await asyncio.sleep(random.uniform(5, 10))
                continue
                
        return {"has_more": False, "items": []}

    async def _handle_empty_response(self):
        """处理空响应"""
        try:
            # 1. 更新cookie
            await self.update_cookies(self.playwright_page.context)
            
            # 2. 更换User-Agent
            await self._rotate_user_agent()
            
            # 3. 随机延迟
            await asyncio.sleep(random.uniform(5, 10))
            
            # 4. 模拟随机行为
            await self.simulate_user_behavior()
            
            # 5. 清除浏览器缓存和cookie（可选）
            try:
                await self.playwright_page.context.clear_cookies()
                await self.playwright_page.evaluate("() => localStorage.clear()")
                await self.playwright_page.evaluate("() => sessionStorage.clear()")
            except Exception as e:
                utils.logger.warning(f"[XiaoHongShuClient._handle_empty_response] Failed to clear browser data: {str(e)}")
            
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient._handle_empty_response] Error: {str(e)}")

    async def get_note_by_id(
        self, note_id: str, xsec_source: str, xsec_token: str
    ) -> Dict:
        """
        获取笔记详情API
        Args:
            note_id:笔记ID
            xsec_source: 渠道来源
            xsec_token: 搜索关键字之后返回的比较列表中返回的token

        Returns:

        """
        if xsec_source == "":
            xsec_source = "pc_search"

        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        uri = "/api/sns/web/v1/feed"
        res = await self.post(uri, data)
        if res and res.get("items"):
            res_dict: Dict = res["items"][0]["note_card"]
            return res_dict
        # 爬取频繁了可能会出现有的笔记能有结果有的没有
        utils.logger.error(
            f"[XiaoHongShuClient.get_note_by_id] get note id:{note_id} empty and res:{res}"
        )
        return dict()

    async def get_note_comments(
        self, note_id: str, xsec_token: str, cursor: str = ""
    ) -> Dict:
        """
        获取一级评论的API
        Args:
            note_id: 笔记ID
            xsec_token: 验证token
            cursor: 分页游标

        Returns:

        """
        uri = "/api/sns/web/v2/comment/page"
        params = {
            "note_id": note_id,
            "cursor": cursor,
            "top_comment_id": "",
            "image_formats": "jpg,webp,avif",
            "xsec_token": xsec_token,
        }
        return await self.get(uri, params)

    async def get_note_sub_comments(
        self,
        note_id: str,
        root_comment_id: str,
        xsec_token: str,
        num: int = 10,
        cursor: str = "",
    ):
        """
        获取指定父评论下的子评论的API
        Args:
            note_id: 子评论的帖子ID
            root_comment_id: 根评论ID
            xsec_token: 验证token
            num: 分页数量
            cursor: 分页游标

        Returns:

        """
        uri = "/api/sns/web/v2/comment/sub/page"
        params = {
            "note_id": note_id,
            "root_comment_id": root_comment_id,
            "num": num,
            "cursor": cursor,
            "image_formats": "jpg,webp,avif",
            "top_comment_id": "",
            "xsec_token": xsec_token,
        }
        return await self.get(uri, params)

    async def get_note_all_comments(
        self,
        note_id: str,
        xsec_token: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """
        获取指定笔记下的所有一级评论，该方法会一直查找一个帖子下的所有评论信息
        Args:
            note_id: 笔记ID
            xsec_token: 验证token
            crawl_interval: 爬取一次笔记的延迟单位（秒）
            callback: 一次笔记爬取结束后
            max_count: 一次笔记爬取的最大评论数量
        Returns:

        """
        result = []
        comments_has_more = True
        comments_cursor = ""
        
        # 获取笔记详情，用于提取笔记标题
        note_detail = await self.get_note_by_id(note_id, "", xsec_token)
        note_title = note_detail.get("title", "") or note_detail.get("desc", "")[:255] or "未知标题"
        
        while comments_has_more and len(result) < max_count:
            comments_res = await self.get_note_comments(
                note_id=note_id, xsec_token=xsec_token, cursor=comments_cursor
            )
            comments_has_more = comments_res.get("has_more", False)
            comments_cursor = comments_res.get("cursor", "")
            if "comments" not in comments_res:
                utils.logger.info(
                    f"[XiaoHongShuClient.get_note_all_comments] No 'comments' key found in response: {comments_res}"
                )
                break
            comments = comments_res["comments"]
            if len(result) + len(comments) > max_count:
                comments = comments[: max_count - len(result)]
                
            # 为每条评论添加笔记标题
            for comment in comments:
                comment["note_title"] = note_title
                
            if callback:
                await callback(note_id, comments)
            await asyncio.sleep(crawl_interval)
            result.extend(comments)
            sub_comments = await self.get_comments_all_sub_comments(
                comments=comments,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=callback,
            )
            result.extend(sub_comments)
        return result

    async def get_comments_all_sub_comments(
        self,
        comments: List[Dict],
        xsec_token: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取指定一级评论下的所有二级评论, 该方法会一直查找一级评论下的所有二级评论信息
        Args:
            comments: 评论列表
            xsec_token: 验证token
            crawl_interval: 爬取一次评论的延迟单位（秒）
            callback: 一次评论爬取结束后

        Returns:

        """
        if not config.ENABLE_GET_SUB_COMMENTS:
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_comments_all_sub_comments] Crawling sub_comment mode is not enabled"
            )
            return []

        result = []
        for comment in comments:
            note_id = comment.get("note_id")
            sub_comments = comment.get("sub_comments")
            # 获取父评论中的笔记标题
            note_title = comment.get("note_title", "未知标题")
            
            if sub_comments and callback:
                # 为子评论添加笔记标题
                for sub_comment in sub_comments:
                    sub_comment["note_title"] = note_title
                await callback(note_id, sub_comments)

            sub_comment_has_more = comment.get("sub_comment_has_more")
            if not sub_comment_has_more:
                continue

            root_comment_id = comment.get("id")
            sub_comment_cursor = comment.get("sub_comment_cursor")

            while sub_comment_has_more:
                comments_res = await self.get_note_sub_comments(
                    note_id=note_id,
                    root_comment_id=root_comment_id,
                    xsec_token=xsec_token,
                    num=10,
                    cursor=sub_comment_cursor,
                )
                sub_comment_has_more = comments_res.get("has_more", False)
                sub_comment_cursor = comments_res.get("cursor", "")
                if "comments" not in comments_res:
                    utils.logger.info(
                        f"[XiaoHongShuClient.get_comments_all_sub_comments] No 'comments' key found in response: {comments_res}"
                    )
                    break
                comments = comments_res["comments"]
                # 为子评论添加笔记标题
                for sub_comment in comments:
                    sub_comment["note_title"] = note_title
                if callback:
                    await callback(note_id, comments)
                await asyncio.sleep(crawl_interval)
                result.extend(comments)
        return result

    async def get_creator_info(self, user_id: str) -> Dict:
        """
        通过解析网页版的用户主页HTML，获取用户个人简要信息
        PC端用户主页的网页存在window.__INITIAL_STATE__这个变量上的，解析它即可
        eg: https://www.xiaohongshu.com/user/profile/59d8cb33de5fb4696bf17217
        """
        uri = f"/user/profile/{user_id}"
        html_content = await self.request(
            "GET", self._domain + uri, return_response=True, headers=self.headers
        )
        match = re.search(
            r"<script>window.__INITIAL_STATE__=(.+)<\/script>", html_content, re.M
        )

        if match is None:
            return {}

        info = json.loads(match.group(1).replace(":undefined", ":null"), strict=False)
        if info is None:
            return {}
        return info.get("user").get("userPageData")

    async def get_notes_by_creator(
        self, creator: str, cursor: str, page_size: int = 30
    ) -> Dict:
        """
        获取博主的笔记
        Args:
            creator: 博主ID
            cursor: 上一页最后一条笔记的ID
            page_size: 分页数据长度

        Returns:

        """
        uri = "/api/sns/web/v1/user_posted"
        data = {
            "user_id": creator,
            "cursor": cursor,
            "num": page_size,
            "image_formats": "jpg,webp,avif",
        }
        return await self.get(uri, data)

    async def get_all_notes_by_creator(
        self,
        user_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取指定用户下的所有发过的帖子，该方法会一直查找一个用户下的所有帖子信息
        Args:
            user_id: 用户ID
            crawl_interval: 爬取一次的延迟单位（秒）
            callback: 一次分页爬取结束后的更新回调函数

        Returns:

        """
        result = []
        notes_has_more = True
        notes_cursor = ""
        while notes_has_more:
            notes_res = await self.get_notes_by_creator(user_id, notes_cursor)
            if not notes_res:
                utils.logger.error(
                    f"[XiaoHongShuClient.get_notes_by_creator] The current creator may have been banned by xhs, so they cannot access the data."
                )
                break

            notes_has_more = notes_res.get("has_more", False)
            notes_cursor = notes_res.get("cursor", "")
            if "notes" not in notes_res:
                utils.logger.info(
                    f"[XiaoHongShuClient.get_all_notes_by_creator] No 'notes' key found in response: {notes_res}"
                )
                break

            notes = notes_res["notes"]
            utils.logger.info(
                f"[XiaoHongShuClient.get_all_notes_by_creator] got user_id:{user_id} notes len : {len(notes)}"
            )
            if callback:
                await callback(notes)
            await asyncio.sleep(crawl_interval)
            result.extend(notes)
        return result

    async def get_note_short_url(self, note_id: str) -> Dict:
        """
        获取笔记的短链接
        Args:
            note_id: 笔记ID

        Returns:

        """
        uri = f"/api/sns/web/short_url"
        data = {"original_url": f"{self._domain}/discovery/item/{note_id}"}
        return await self.post(uri, data=data, return_response=True)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_note_by_id_from_html(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        enable_cookie: bool = False,
    ) -> Optional[Dict]:
        """
        通过解析网页版的笔记详情页HTML，获取笔记详情, 该接口可能会出现失败的情况，这里尝试重试3次
        copy from https://github.com/ReaJason/xhs/blob/eb1c5a0213f6fbb592f0a2897ee552847c69ea2d/xhs/core.py#L217-L259
        thanks for ReaJason
        Args:
            note_id:
            xsec_source:
            xsec_token:
            enable_cookie:

        Returns:

        """

        def camel_to_underscore(key):
            return re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()

        def transform_json_keys(json_data):
            data_dict = json.loads(json_data)
            dict_new = {}
            for key, value in data_dict.items():
                new_key = camel_to_underscore(key)
                if not value:
                    dict_new[new_key] = value
                elif isinstance(value, dict):
                    dict_new[new_key] = transform_json_keys(json.dumps(value))
                elif isinstance(value, list):
                    dict_new[new_key] = [
                        (
                            transform_json_keys(json.dumps(item))
                            if (item and isinstance(item, dict))
                            else item
                        )
                        for item in value
                    ]
                else:
                    dict_new[new_key] = value
            return dict_new

        url = (
            "https://www.xiaohongshu.com/explore/"
            + note_id
            + f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
        )
        copy_headers = self.headers.copy()
        if not enable_cookie:
            del copy_headers["Cookie"]

        html = await self.request(
            method="GET", url=url, return_response=True, headers=copy_headers
        )

        def get_note_dict(html):
            state = re.findall(r"window.__INITIAL_STATE__=({.*})</script>", html)[
                0
            ].replace("undefined", '""')

            if state != "{}":
                note_dict = transform_json_keys(state)
                return note_dict["note"]["note_detail_map"][note_id]["note"]
            return {}

        try:
            return get_note_dict(html)
        except:
            return None
