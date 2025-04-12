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
        timeout=10,
        proxies=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.headers = headers
        self.user_agent = headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        self._host = "https://edith.xiaohongshu.com"
        self._domain = "https://www.xiaohongshu.com"
        self.IP_ERROR_STR = "网络连接异常，请检查网络设置或重启试试"
        self.IP_ERROR_CODE = 300012
        self.NOTE_ABNORMAL_STR = "笔记状态异常，请稍后查看"
        self.NOTE_ABNORMAL_CODE = -510001
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self.cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

    async def close(self) -> None:
        """关闭客户端资源"""
        try:
            if self.playwright_page:
                await self.playwright_page.close()
            utils.logger.info("[XiaoHongShuClient.close] Successfully closed client resources")
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.close] Error closing client: {e}")

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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def request(self, method, url, **kwargs) -> Union[str, Any]:
        """
        封装httpx的公共请求方法，对请求响应做一些处理
        Args:
            method: 请求方法
            url: 请求的URL
            **kwargs: 其他请求参数，例如请求头、请求体等

        Returns:

        """
        # return response.text
        return_response = kwargs.pop("return_response", False)

        async with httpx.AsyncClient(proxies=self.proxies) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code == 471 or response.status_code == 461:
            # someday someone maybe will bypass captcha
            verify_type = response.headers["Verifytype"]
            verify_uuid = response.headers["Verifyuuid"]
            raise Exception(
                f"出现验证码，请求失败，Verifytype: {verify_type}，Verifyuuid: {verify_uuid}, Response: {response}"
            )

        if return_response:
            return response.text
        data: Dict = response.json()
        if data["success"]:
            return data.get("data", data.get("success", {}))
        elif data["code"] == self.IP_ERROR_CODE:
            raise IPBlockError(self.IP_ERROR_STR)
        else:
            raise DataFetchError(data.get("msg", None))

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
        uri = "/api/sns/web/v1/search/notes"
        data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id,
            "sort": sort.value,
            "note_type": note_type.value,
        }
        return await self.post(uri, data)

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
            if sub_comments and callback:
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
                if callback:
                    await callback(note_id, comments)
                await asyncio.sleep(crawl_interval)
                result.extend(comments)
        return result

    async def get_creator_info(self, user_id: str) -> Dict:
        """获取作者信息"""
        try:
            # 1. 验证Cookie是否有效
            if not self.cookie_str or "web_session" not in self.cookie_str:
                utils.logger.error("[XiaoHongShuClient.get_creator_info] Invalid or missing cookie")
                return None
            
            # 2. 使用网页接口
            url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
            headers = {
                "User-Agent": self.user_agent,
                "Cookie": self.cookie_str,
                "Referer": "https://www.xiaohongshu.com",
            }
            
            utils.logger.info(f"[XiaoHongShuClient.get_creator_info] Requesting creator info for user_id: {user_id}")
            
            # 3. 获取HTML响应
            async with asyncio.timeout(30):
                html_content = await self._make_request(url, headers=headers, expect_json=False)
            
            if html_content:
                # 4. 解析HTML提取作者信息
                try:
                    # 使用正则表达式或其他HTML解析方法提取数据
                    # 这里需要根据实际的HTML结构来提取数据
                    creator_info = self._parse_creator_info_from_html(html_content)
                    if creator_info:
                        utils.logger.info(f"[XiaoHongShuClient.get_creator_info] Successfully got creator info for user_id: {user_id}")
                        return creator_info
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuClient.get_creator_info] Error parsing HTML: {e}")
                    
            utils.logger.warning(f"[XiaoHongShuClient.get_creator_info] Empty response for user_id: {user_id}")
            return None
            
        except asyncio.TimeoutError:
            utils.logger.error(f"[XiaoHongShuClient.get_creator_info] Timeout for user_id: {user_id}")
            return None
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient.get_creator_info] Error: {e}")
            return None

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

    async def get_creators_and_notes(self) -> None:
        """Get creator's notes and retrieve their comment information."""
        utils.logger.info(
            "[XiaoHongShuCrawler.get_creators_and_notes] Begin get xiaohongshu creators"
        )
        
        for user_id in config.XHS_CREATOR_ID_LIST:
            try:
                utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Processing creator: {user_id}")
                
                # 1. 获取作者信息
                createor_info = await self.get_creator_info(user_id=user_id)
                if not createor_info:
                    utils.logger.warning(f"[XiaoHongShuCrawler.get_creators_and_notes] Failed to get creator info for user_id: {user_id}")
                    continue
                    
                # 2. 保存作者信息
                try:
                    await xhs_store.save_creator(user_id, creator=createor_info)
                    utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Successfully saved creator info for user_id: {user_id}")
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Failed to save creator info: {e}")
                    
                # 3. 添加适当的延迟
                await asyncio.sleep(random.uniform(1, 3))
                
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Error processing creator {user_id}: {e}")
                continue

    async def _make_request(self, url: str, headers: Dict[str, str], expect_json: bool = True) -> Union[Dict, str]:
        """
        发送HTTP请求
        Args:
            url: 请求URL
            headers: 请求头
            expect_json: 是否期望返回JSON格式，默认为True
        Returns:
            Union[Dict, str]: 返回JSON对象或HTML文本
        """
        try:
            async with httpx.AsyncClient(
                proxies=self.proxies,
                timeout=self.timeout,
                follow_redirects=True,
                verify=False
            ) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code in [200, 302]:
                    try:
                        # 如果是重定向，获取重定向后的URL
                        if response.status_code == 302:
                            redirect_url = response.headers.get('Location')
                            if redirect_url:
                                utils.logger.info(f"[XiaoHongShuClient._make_request] Following redirect to: {redirect_url}")
                                response = await client.get(redirect_url, headers=headers)
                        
                        # 根据expect_json参数决定返回格式
                        if expect_json:
                            return response.json()
                        else:
                            return response.text
                        
                    except json.JSONDecodeError as e:
                        if expect_json:
                            utils.logger.error(f"[XiaoHongShuClient._make_request] Invalid JSON response: {response.text[:200]}")
                            return None
                        else:
                            return response.text
                        
                else:
                    utils.logger.error(f"[XiaoHongShuClient._make_request] Request failed with status code: {response.status_code}")
                    return None
                
        except httpx.TimeoutException:
            utils.logger.error(f"[XiaoHongShuClient._make_request] Request timeout for URL: {url}")
            return None
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient._make_request] Error: {e}")
            return None

    def _parse_creator_info_from_html(self, html_content: str) -> Dict:
        """从HTML中解析作者信息"""
        try:
            # 使用正则表达式或其他HTML解析方法提取数据
            # 这里需要根据实际的HTML结构来提取数据
            # 示例：
            import re
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取作者信息
            creator_info = {
                "user_id": None,
                "nickname": None,
                "avatar": None,
                "description": None,
                "follower_count": None,
                "following_count": None,
                "note_count": None
            }
            
            # 根据实际的HTML结构提取数据
            # 这里需要根据实际的HTML结构来修改
            script_content = soup.find('script', text=re.compile('window.__INITIAL_STATE__'))
            if script_content:
                # 提取JSON数据
                json_str = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', script_content.string, re.DOTALL)
                if json_str:
                    data = json.loads(json_str.group(1))
                    # 从data中提取作者信息
                    # ...
                    
            return creator_info
            
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuClient._parse_creator_info_from_html] Error parsing HTML: {e}")
            return None

class ExpiringLocalCache:
    def __init__(self, expire_seconds: int = 600):
        self.cache = {}
        self.expire_seconds = expire_seconds
        self._clear_task = None
        
    async def start(self):
        """启动清理任务"""
        if self._clear_task is None:
            self._clear_task = asyncio.create_task(self._start_clear_cron())
            
    async def stop(self):
        """停止清理任务"""
        if self._clear_task:
            self._clear_task.cancel()
            try:
                await self._clear_task
            except asyncio.CancelledError:
                pass
            self._clear_task = None
            
    async def _start_clear_cron(self) -> None:
        """启动定时清理任务"""
        try:
            while True:
                await asyncio.sleep(self.expire_seconds)
                await self.clear_expired()
        except asyncio.CancelledError:
            utils.logger.info("[ExpiringLocalCache._start_clear_cron] Clear cron task cancelled")
        except Exception as e:
            utils.logger.error(f"[ExpiringLocalCache._start_clear_cron] Error: {e}")

async def main():
    crawler = None
    try:
        # 初始化爬虫
        crawler = XiaoHongShuCrawler()
        await crawler.start()
        
        # 获取作者信息
        await crawler.get_creators_and_notes()
        
    except Exception as e:
        utils.logger.error(f"Error in main: {e}")
    finally:
        try:
            if crawler:
                await crawler.close()
        except Exception as e:
            utils.logger.error(f"Error closing crawler: {e}")

if __name__ == "__main__":
    asyncio.run(main())
