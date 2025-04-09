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
        Args:
            url:
            data:

        Returns:

        """
        encrypt_params = await self.playwright_page.evaluate(
            "([url, data]) => window._webmsxyw(url,data)", [url, data]
        )
        local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        signs = sign(
            a1=self.cookie_dict.get("a1", ""),
            b1=local_storage.get("b1", ""),
            x_s=encrypt_params.get("X-s", ""),
            x_t=str(encrypt_params.get("X-t", "")),
        )

        headers = {
            "X-S": signs["x-s"],
            "X-T": signs["x-t"],
            "x-S-Common": signs["x-s-common"],
            "X-B3-Traceid": signs["x-b3-traceid"],
        }
        self.headers.update(headers)
        return self.headers

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
        Args:
            keyword: 关键词参数
            page: 分页第几页
            page_size: 分页数据长度
            sort: 搜索结果排序指定
            note_type: 搜索的笔记类型

        Returns:

        """
        # 先访问搜索页面
        try:
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
            await self.playwright_page.goto(search_url)
            await asyncio.sleep(random.uniform(2, 4))
            
            # 模拟滚动
            for _ in range(random.randint(1, 3)):
                await self.playwright_page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(random.uniform(1, 2))
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] Failed to visit search page: {str(e)}")

        uri = "/api/sns/web/v1/search/notes"
        data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id,
            "sort": sort.value,
            "note_type": note_type.value,
            "image_formats": ["jpg", "webp", "avif"]
        }
        utils.logger.info(f"[XiaoHongShuClient.get_note_by_keyword] Searching with params: {data}")
        try:
            response = await self.post(uri, data)
            utils.logger.info(f"[XiaoHongShuClient.get_note_by_keyword] Search response: {response}")
            
            # 检查响应内容
            if not response or (isinstance(response, dict) and not response.get("items")):
                utils.logger.warning("[XiaoHongShuClient.get_note_by_keyword] Empty response or no items found")
                # 尝试重新获取cookie
                await self.update_cookies(self.playwright_page.context)
                # 重试请求
                response = await self.post(uri, data)
                
            return response
        except IPBlockError as e:
            utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] IP blocked: {str(e)}")
            raise
        except DataFetchError as e:
            utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] Data fetch error: {str(e)}")
            raise
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.get_note_by_keyword] Unexpected error: {str(e)}")
            raise

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
