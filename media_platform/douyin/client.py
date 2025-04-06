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
import copy
import json
import urllib.parse
from typing import Any, Callable, Dict, Optional, List
import random
import time

import requests
from playwright.async_api import BrowserContext

from base.base_crawler import AbstractApiClient
from tools import utils
from var import request_keyword_var

from .exception import *
from .field import *
from .help import *


class DOUYINClient(AbstractApiClient):
    def __init__(
            self,
            timeout=30,
            proxies=None,
            *,
            headers: Dict,
            playwright_page: Optional[Page],
            cookie_dict: Dict
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.headers = headers
        self._host = "https://www.douyin.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict

    async def __process_req_params(
            self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None,
            request_method="GET"
    ):

        if not params:
            return
        headers = headers or self.headers
        local_storage: Dict = await self.playwright_page.evaluate("() => window.localStorage")  # type: ignore
        common_params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "MacIntel",
            "browser_name": "Chrome",
            "browser_version": "125.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Mac OS",
            "os_version": "10.15.7",
            "cpu_core_num": "8",
            "device_memory": "8",
            "engine_version": "109.0",
            "platform": "PC",
            "screen_width": "2560",
            "screen_height": "1440",
            'effective_type': '4g',
            "round_trip_time": "50",
            "webid": get_web_id(),
            "msToken": local_storage.get("xmst"),
        }
        params.update(common_params)
        query_string = urllib.parse.urlencode(params)

        # 20240927 a-bogus更新（JS版本）
        post_data = {}
        if request_method == "POST":
            post_data = params
        a_bogus = await get_a_bogus(uri, query_string, post_data, headers["User-Agent"], self.playwright_page)
        params["a_bogus"] = a_bogus

    async def request(self, method, url, **kwargs):
        """
        发送请求
        :param method: 请求方法
        :param url: 请求URL
        :param kwargs: 请求参数
        :return: 响应结果
        """
        try:
            # 设置更长的超时时间
            kwargs['timeout'] = 60  # 增加到60秒
            
            # 使用requests发送请求
            response = requests.request(method, url, **kwargs)
            
            # 检查响应状态
            if response.status_code != 200:
                utils.logger.error(f"请求失败: {response.status_code} - {response.text}")
                return None
            
            # 检查响应内容
            if not response.text:
                utils.logger.error("响应内容为空")
                return None
            
            # 尝试解析JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                utils.logger.error(f"JSON解析失败: {response.text}")
                return None
            
        except requests.Timeout:
            utils.logger.error("请求超时")
            return None
        except requests.RequestException as e:
            utils.logger.error(f"请求异常: {str(e)}")
            return None
        except Exception as e:
            utils.logger.error(f"未知异常: {str(e)}")
            return None

    async def get(self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None):
        """
        GET请求
        """
        await self.__process_req_params(uri, params, headers)
        headers = headers or self.headers
        return await self.request(method="GET", url=f"{self._host}{uri}", params=params, headers=headers)

    async def post(self, uri: str, data: dict, headers: Optional[Dict] = None):
        await self.__process_req_params(uri, data, headers)
        headers = headers or self.headers
        return await self.request(method="POST", url=f"{self._host}{uri}", data=data, headers=headers)

    async def pong(self, browser_context: BrowserContext) -> bool:
        local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        if local_storage.get("HasUserLogin", "") == "1":
            return True

        _, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        return cookie_dict.get("LOGIN_STATUS") == "1"

    async def update_cookies(self, browser_context: BrowserContext):
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_info_by_keyword(
            self,
            keyword: str,
            offset: int = 0,
            search_channel: SearchChannelType = SearchChannelType.GENERAL,
            sort_type: SearchSortType = SearchSortType.GENERAL,
            publish_time: PublishTimeType = PublishTimeType.UNLIMITED,
            search_id: str = ""
    ):
        """
        DouYin Web Search API
        :param keyword:
        :param offset:
        :param search_channel:
        :param sort_type:
        :param publish_time: ·
        :param search_id: ·
        :return:
        """
        query_params = {
            'search_channel': search_channel.value,
            'enable_history': '1',
            'keyword': keyword,
            'search_source': 'tab_search',
            'query_correct_type': '1',
            'is_filter_search': '0',
            'from_group_id': '7378810571505847586',
            'offset': offset,
            'count': '15',
            'need_filter_settings': '1',
            'list_type': 'multi',
            'search_id': search_id,
        }
        if sort_type.value != SearchSortType.GENERAL.value or publish_time.value != PublishTimeType.UNLIMITED.value:
            query_params["filter_selected"] = json.dumps({
                "sort_type": str(sort_type.value),
                "publish_time": str(publish_time.value)
            })
            query_params["is_filter_search"] = 1
            query_params["search_source"] = "tab_search"
        referer_url = f"https://www.douyin.com/search/{keyword}?aid=f594bbd9-a0e2-4651-9319-ebe3cb6298c1&type=general"
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=':/')
        return await self.get("/aweme/v1/web/general/search/single/", query_params, headers=headers)

    async def get_video_by_id(self, aweme_id: str) -> Any:
        """
        DouYin Video Detail API
        :param aweme_id:
        :return:
        """
        params = {
            "aweme_id": aweme_id
        }
        headers = copy.copy(self.headers)
        del headers["Origin"]
        res = await self.get("/aweme/v1/web/aweme/detail/", params, headers)
        return res.get("aweme_detail", {})

    async def get_aweme_comments(self, aweme_id: str, cursor: int = 0):
        """get note comments

        """
        uri = "/aweme/v1/web/comment/list/"
        params = {
            "aweme_id": aweme_id,
            "cursor": cursor,
            "count": 20,
            "item_type": 0
        }
        keywords = request_keyword_var.get()
        referer_url = "https://www.douyin.com/search/" + keywords + '?aid=3a3cec5a-9e27-4040-b6aa-ef548c2c1138&publish_time=0&sort_type=0&source=search_history&type=general'
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=':/')
        return await self.get(uri, params)

    async def get_sub_comments(self, comment_id: str, cursor: int = 0):
        """
            获取子评论
        """
        uri = "/aweme/v1/web/comment/list/reply/"
        params = {
            'comment_id': comment_id,
            "cursor": cursor,
            "count": 20,
            "item_type": 0,
        }
        keywords = request_keyword_var.get()
        referer_url = "https://www.douyin.com/search/" + keywords + '?aid=3a3cec5a-9e27-4040-b6aa-ef548c2c1138&publish_time=0&sort_type=0&source=search_history&type=general'
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=':/')
        return await self.get(uri, params)

    async def get_aweme_all_comments(
            self,
            aweme_id: str,
            crawl_interval: float = 1.0,
            is_fetch_sub_comments=False,
            callback: Optional[Callable] = None,
            max_count: int = 10,
    ):
        """
        获取帖子的所有评论，包括子评论
        :param aweme_id: 帖子ID
        :param crawl_interval: 抓取间隔
        :param is_fetch_sub_comments: 是否抓取子评论
        :param callback: 回调函数，用于处理抓取到的评论
        :param max_count: 一次帖子爬取的最大评论数量
        :return: 评论列表
        """
        result = []
        comments_has_more = 1
        comments_cursor = 0
        while comments_has_more and len(result) < max_count:
            comments_res = await self.get_aweme_comments(aweme_id, comments_cursor)
            comments_has_more = comments_res.get("has_more", 0)
            comments_cursor = comments_res.get("cursor", 0)
            comments = comments_res.get("comments", [])
            if not comments:
                continue
            if len(result) + len(comments) > max_count:
                comments = comments[:max_count - len(result)]
            result.extend(comments)
            if callback:  # 如果有回调函数，就执行回调函数
                await callback(aweme_id, comments)

            await asyncio.sleep(crawl_interval)
            if not is_fetch_sub_comments:
                continue
            # 获取二级评论
            for comment in comments:
                reply_comment_total = comment.get("reply_comment_total")

                if reply_comment_total > 0:
                    comment_id = comment.get("cid")
                    sub_comments_has_more = 1
                    sub_comments_cursor = 0

                    while sub_comments_has_more:
                        sub_comments_res = await self.get_sub_comments(comment_id, sub_comments_cursor)
                        sub_comments_has_more = sub_comments_res.get("has_more", 0)
                        sub_comments_cursor = sub_comments_res.get("cursor", 0)
                        sub_comments = sub_comments_res.get("comments", [])

                        if not sub_comments:
                            continue
                        result.extend(sub_comments)
                        if callback:  # 如果有回调函数，就执行回调函数
                            await callback(aweme_id, sub_comments)
                        await asyncio.sleep(crawl_interval)
        return result

    async def get_user_info(self, sec_user_id: str):
        uri = "/aweme/v1/web/user/profile/other/"
        params = {
            "sec_user_id": sec_user_id,
            "publish_video_strategy_type": 2,
            "personal_center_strategy": 1,
        }
        return await self.get(uri, params)

    async def get_user_aweme_posts(self, sec_user_id: str, max_cursor: str = "") -> Dict:
        uri = "/aweme/v1/web/aweme/post/"
        params = {
            "sec_user_id": sec_user_id,
            "count": 18,
            "max_cursor": max_cursor,
            "locate_query": "false",
            "publish_video_strategy_type": 2,
            'verifyFp': 'verify_lx901cuk_K7kaK4dK_bn2E_4dgk_BxAA_E0XS1VtUi130',
            'fp': 'verify_lx901cuk_K7kaK4dK_bn2E_4dgk_BxAA_E0XS1VtUi130'
        }
        return await self.get(uri, params)

    async def get_all_user_aweme_posts(self, sec_user_id: str, callback: Optional[Callable] = None):
        posts_has_more = 1
        max_cursor = ""
        result = []
        while posts_has_more == 1:
            aweme_post_res = await self.get_user_aweme_posts(sec_user_id, max_cursor)
            posts_has_more = aweme_post_res.get("has_more", 0)
            max_cursor = aweme_post_res.get("max_cursor")
            aweme_list = aweme_post_res.get("aweme_list") if aweme_post_res.get("aweme_list") else []
            utils.logger.info(
                f"[DOUYINClient.get_all_user_aweme_posts] got sec_user_id:{sec_user_id} video len : {len(aweme_list)}")
            if callback:
                await callback(aweme_list)
            result.extend(aweme_list)
        return result

    async def search_user_by_keyword(
            self,
            keyword: str,
            offset: int = 0,
            search_id: str = ""
    ):
        """
        搜索抖音用户
        :param keyword: 搜索关键词
        :param offset: 偏移量
        :param search_id: 搜索ID
        :return: 搜索结果
        """
        query_params = {
            'search_channel': SearchChannelType.USER.value,
            'keyword': keyword,
            'search_source': 'tab_search',
            'query_correct_type': '1',
            'is_filter_search': '0',
            'offset': offset,
            'count': '15',
            'publish_time': 0,
            'sort_type': 0,
            'enter_from': 'search_result',
            'search_id': search_id
        }
        referer_url = f"https://www.douyin.com/search/{keyword}?aid=f594bbd9-a0e2-4651-9319-ebe3cb6298c1&type=user"
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=':/')
        return await self.get("/aweme/v1/web/discover/search/", query_params, headers=headers)

    async def follow_user(self, sec_user_id: str):
        """
        关注用户
        :param sec_user_id: 用户ID
        :return: 关注结果
        """
        try:
            utils.logger.info("开始关注用户流程")
            
            # 先检查用户是否已关注
            utils.logger.info("检查用户是否已关注")
            follow_status_selectors = [
                'button:has-text("已关注")',
                '.semi-button:has-text("已关注")',
                '.semi-button-tertiary:has-text("已关注")',
                '[data-e2e="user-info-follow-btn"]:has-text("已关注")'
            ]
            
            # 等待页面加载完成，使用更短的超时时间
            try:
                await self.playwright_page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                utils.logger.info(f"等待页面加载完成超时，继续执行: {str(e)}")
            
            await asyncio.sleep(1)  # 短暂等待
            
            # 检查是否已关注，使用更短的超时时间
            for selector in follow_status_selectors:
                try:
                    follow_status = await self.playwright_page.wait_for_selector(
                        selector,
                        state="visible",
                        timeout=2000  # 每个选择器最多等待2秒
                    )
                    if follow_status:
                        utils.logger.info("检测到已关注状态")
                        return {"status_code": 0, "status_msg": "already followed"}
                except Exception:
                    continue
            
            utils.logger.info("用户未关注，开始执行关注操作")
            
            # 尝试多种选择器查找关注按钮
            selectors = [
                # 优先使用最精确的选择器
                'button.semi-button-primary:has-text("关注")',  # 根据实际class定位红色关注按钮
                '.semi-button.semi-button-primary:has-text("关注")',  # 备用选择器
                '.ajC8cNxV.I4tJiW0Q:has-text("关注")',  # 使用特定class组合
                '[data-e2e="user-info-follow-btn"]',  # 用户信息区域的关注按钮
                '.user-info button.semi-button-primary',  # 用户信息区域内的主要按钮
                '.profile-info button.semi-button-primary',  # 用户资料区域内的主要按钮
                '.semi-button.semi-button-primary[data-e2e="user-info-follow-btn"]'  # 组合选择器
            ]
            
            utils.logger.info("开始查找关注按钮")
            follow_button = None
            original_button = None
            
            # 遍历所有选择器
            for selector in selectors:
                try:
                    utils.logger.info(f"尝试使用选择器: {selector}")
                    # 先检查元素是否存在
                    elements = await self.playwright_page.query_selector_all(selector)
                    for element in elements:
                        # 检查元素是否可见
                        is_visible = await element.is_visible()
                        if not is_visible:
                            continue
                            
                        # 获取元素的位置信息
                        box = await element.bounding_box()
                        if not box:
                            continue
                            
                        # 检查是否是左侧菜单栏的按钮
                        if box["x"] < 200:  # 左侧菜单栏通常在屏幕左侧
                            utils.logger.info(f"跳过左侧菜单栏按钮: x={box['x']}")
                            continue
                        
                        # 检查按钮文本和class
                        button_text = await element.text_content()
                        button_class = await element.get_attribute("class")
                        
                        if not button_text or "已关注" in button_text or "关注中" in button_text:
                            continue
                            
                        utils.logger.info(f"找到可见的关注按钮，位置: x={box['x']}, y={box['y']}, class={button_class}")
                        follow_button = element
                        original_button = {
                            "selector": selector,
                            "x": box["x"],
                            "y": box["y"],
                            "class": button_class
                        }
                        break
                        
                    if follow_button:
                        break
                except Exception as e:
                    utils.logger.info(f"选择器 {selector} 查找失败: {str(e)}")
                    continue
            
            if not follow_button:
                utils.logger.error("未找到可见的关注按钮")
                # 输出页面内容以供调试
                page_content = await self.playwright_page.content()
                utils.logger.info(f"页面内容: {page_content[:500]}...")  # 只记录前500个字符
                return None
            
            # 确保按钮可见和可点击
            try:
                # 滚动到按钮位置
                await follow_button.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                utils.logger.info("按钮已滚动到可见位置")
                
                # 获取按钮位置
                button_box = await follow_button.bounding_box()
                if button_box:
                    # 随机移动到按钮附近
                    x_offset = random.randint(-10, 10)
                    y_offset = random.randint(-5, 5)
                    await self.playwright_page.mouse.move(
                        button_box["x"] + button_box["width"] / 2 + x_offset,
                        button_box["y"] + button_box["height"] / 2 + y_offset
                    )
                    utils.logger.info("鼠标已移动到按钮附近")
                    
                    # 模拟人类移动到按钮中心
                    await self.playwright_page.mouse.move(
                        button_box["x"] + button_box["width"] / 2,
                        button_box["y"] + button_box["height"] / 2,
                        steps=5  # 分5步移动，更像人类操作
                    )
                    utils.logger.info("鼠标已移动到按钮中心")
            except Exception as e:
                utils.logger.error(f"准备点击按钮时出错: {str(e)}")
                return None
            
            # 记录点击前的按钮状态和属性
            try:
                button_text_before = await follow_button.text_content()
                button_class = await follow_button.get_attribute("class")
                utils.logger.info(f"点击前按钮状态: {button_text_before}")
                utils.logger.info(f"按钮class: {button_class}")
                
                # 检查按钮是否已经是关注状态
                if "已关注" in button_text_before or "关注中" in button_text_before:
                    utils.logger.info("按钮已经是关注状态")
                    return {"status_code": 0, "status_msg": "already followed"}
            except Exception as e:
                utils.logger.error(f"获取按钮信息时出错: {str(e)}")
                return None
            
            # 设置网络请求监听
            follow_request_seen = False
            follow_success = False
            
            def handle_request(request):
                nonlocal follow_request_seen
                if "relation/follow" in request.url:
                    follow_request_seen = True
                    utils.logger.info("检测到关注请求发出")
            
            # 添加请求监听（不需要await）
            self.playwright_page.on("request", handle_request)
            
            # 定义检查按钮状态的函数
            async def check_button_status(button):
                try:
                    if not button:
                        return False
                    current_text = await button.text_content()
                    current_class = await button.get_attribute("class")
                    utils.logger.info(f"按钮状态 - 文本: {current_text}, class: {current_class}")
                    return "已关注" in current_text or "关注中" in current_text
                except:
                    return False
            
            # 尝试点击
            try:
                # 使用evaluate进行一次完整的点击操作
                await self.playwright_page.evaluate("""(button) => {
                    return new Promise((resolve) => {
                        // 模拟真实的鼠标事件序列
                        const rect = button.getBoundingClientRect();
                        const centerX = rect.left + rect.width / 2;
                        const centerY = rect.top + rect.height / 2;
                        
                        const events = [
                            new MouseEvent('mouseenter', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: centerX,
                                clientY: centerY
                            }),
                            new MouseEvent('mousedown', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: centerX,
                                clientY: centerY,
                                buttons: 1
                            }),
                            new MouseEvent('mouseup', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: centerX,
                                clientY: centerY
                            }),
                            new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: centerX,
                                clientY: centerY
                            })
                        ];
                        
                        // 按顺序触发事件
                        events.forEach((event, index) => {
                            setTimeout(() => {
                                button.dispatchEvent(event);
                                if (index === events.length - 1) {
                                    resolve();
                                }
                            }, index * 50);  // 每个事件间隔50ms
                        });
                    });
                }""", follow_button)
                utils.logger.info("JavaScript事件模拟完成")
                
                # 等待一小段时间看是否有响应
                await asyncio.sleep(1)
                
                # 检查按钮状态
                if await check_button_status(follow_button):
                    utils.logger.info("JavaScript点击后检测到关注成功")
                    return {"status_code": 0, "status_msg": "success"}
                
                # 如果JavaScript点击不成功，尝试使用Playwright的click
                if not follow_success and not follow_request_seen:
                    await follow_button.click(force=True, delay=100)
                    utils.logger.info("Playwright click完成")
                    await asyncio.sleep(1)
                    
                    # 再次检查状态
                    if await check_button_status(follow_button):
                        utils.logger.info("Playwright click后检测到关注成功")
                        return {"status_code": 0, "status_msg": "success"}
                
                # 如果还是不成功，最后尝试mouse.click
                if not follow_success and not follow_request_seen:
                    await self.playwright_page.mouse.click(
                        button_box["x"] + button_box["width"] / 2,
                        button_box["y"] + button_box["height"] / 2,
                        delay=100
                    )
                    utils.logger.info("鼠标点击完成")
                    
                    # 等待并检查结果
                    start_time = asyncio.get_event_loop().time()
                    while not follow_request_seen and (asyncio.get_event_loop().time() - start_time) < 5:  # 减少等待时间到5秒
                        await asyncio.sleep(0.5)
                        if await check_button_status(follow_button):
                            utils.logger.info("鼠标点击后检测到关注成功")
                            return {"status_code": 0, "status_msg": "success"}
                
                # 如果UI操作都失败了，尝试API调用
                if not follow_success and not follow_request_seen:
                    utils.logger.info("尝试使用API发送关注请求")
                    try:
                        uri = "/aweme/v1/web/commit/follow/user/"
                        params = {
                            "sec_user_id": sec_user_id,
                            "from": "0",
                            "from_pre": "0",
                            "enter_from": "homepage",
                            "type": "1"
                        }
                        headers = copy.copy(self.headers)
                        headers["Referer"] = f"https://www.douyin.com/user/{sec_user_id}"
                        headers["Content-Type"] = "application/x-www-form-urlencoded"
                        headers["Accept"] = "application/json, text/plain, */*"
                        
                        csrf_token = await self.playwright_page.evaluate("""() => {
                            const match = document.cookie.match(/csrf_session_id=([^;]+)/);
                            return match ? match[1] : '';
                        }""")
                        
                        if csrf_token:
                            headers["X-Secsdk-Csrf-Token"] = csrf_token
                        
                        api_result = await self.post(uri, params, headers)
                        if api_result and api_result.get("status_code") == 0:
                            utils.logger.info("API关注请求成功")
                            return {"status_code": 0, "status_msg": "success"}
                        else:
                            utils.logger.warning(f"API关注请求失败: {api_result}")
                    except Exception as api_e:
                        utils.logger.error(f"API关注请求异常: {str(api_e)}")
                
                # 最后检查一次按钮状态
                await asyncio.sleep(1)
                current_button = await self.playwright_page.query_selector(original_button["selector"])
                if not current_button:
                    utils.logger.info("无法找到关注按钮，可能已变为已关注状态")
                    return {"status_code": 0, "status_msg": "success"}
                
                if await check_button_status(current_button):
                    utils.logger.info("最终检查时发现关注成功")
                    return {"status_code": 0, "status_msg": "success"}
                
                utils.logger.error("所有尝试都失败，未能完成关注操作")
                return None
                
            except Exception as e:
                utils.logger.error(f"点击或验证过程出错: {str(e)}")
                return None
            finally:
                # 移除请求监听
                self.playwright_page.remove_listener("request", handle_request)
            
        except Exception as e:
            utils.logger.error(f"关注用户时发生异常: {str(e)}")
            return None

    async def send_private_message(self, sec_user_id: str, message: str = "你好"):
        """
        发送私聊消息
        :param sec_user_id: 用户ID
        :param message: 要发送的消息
        :return: 发送结果
        """
        try:
            utils.logger.info("开始发送私聊消息流程")
            
            # 刷新页面以确保状态正确
            try:
                await self.playwright_page.reload(timeout=5000)
                await asyncio.sleep(1)
            except Exception as e:
                utils.logger.warning(f"页面刷新超时，继续执行: {str(e)}")
            
            # 设置视窗大小以确保能看到右侧按钮
            await self.playwright_page.set_viewport_size({"width": 2560, "height": 1440})
            
            # 尝试查找私信按钮
            selectors = [
                'button:has-text("私信")',
                '[data-e2e="user-info-message-btn"]',
                '.semi-button:has-text("私信")',
                '.message-btn',
                '.semi-button.semi-button-tertiary:has-text("私信")',
                '.semi-button-tertiary:has-text("私信")',
                '.semi-button.semi-button-tertiary',
                '[data-e2e="user-info-message"]'
            ]
            
            utils.logger.info("开始查找私信按钮")
            message_button = None
            
            # 确保页面加载完成
            try:
                await self.playwright_page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                utils.logger.warning(f"等待页面加载完成超时，继续执行: {str(e)}")
            
            # 滚动到页面顶部
            await self.playwright_page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            # 遍历所有选择器尝试查找按钮
            for selector in selectors:
                try:
                    elements = await self.playwright_page.query_selector_all(selector)
                    utils.logger.info(f"选择器 {selector} 找到 {len(elements)} 个元素")
                    
                    for element in elements:
                        if not await element.is_visible():
                            continue
                            
                        box = await element.bounding_box()
                        if not box:
                            continue
                        
                        button_text = await element.text_content()
                        if not button_text or "私信" not in button_text:
                            continue
                            
                        utils.logger.info(f"找到可见的私信按钮，位置: x={box['x']}, y={box['y']}, 文本: {button_text}")
                        message_button = element
                        break
                        
                    if message_button:
                        break
                except Exception as e:
                    utils.logger.info(f"选择器 {selector} 查找失败: {str(e)}")
                    continue
            
            if not message_button:
                utils.logger.error("未找到私信按钮")
                return None
                
            # 点击私信按钮
            try:
                await message_button.click()
                utils.logger.info("已点击私信按钮")
                await asyncio.sleep(2)  # 等待对话框加载
                
                try:
                    # 获取当前活动元素（焦点元素）
                    active_element = await self.playwright_page.evaluate("""() => {
                        const active = document.activeElement;
                        return {
                            tagName: active.tagName.toLowerCase(),
                            isContentEditable: active.isContentEditable,
                            placeholder: active.getAttribute('placeholder'),
                            className: active.className
                        };
                    }""")
                    
                    utils.logger.info(f"当前焦点元素信息: {active_element}")
                    
                    # 直接在活动元素上输入
                    await self.playwright_page.keyboard.type(message, delay=50)
                    utils.logger.info("使用键盘输入消息")
                    
                    # 等待一下确保消息输入完成
                    await asyncio.sleep(0.5)
                    
                    # 按回车发送消息
                    await self.playwright_page.keyboard.press('Enter')
                    utils.logger.info("按回车发送消息")
                    
                    # 等待消息发送
                    await asyncio.sleep(1)
                    
                    return {"status": "success", "message": "私信发送成功"}
                    
                except Exception as e:
                    utils.logger.error(f"使用活动元素输入消息失败: {str(e)}")
                    return None
                    
            except Exception as e:
                utils.logger.error(f"发送私信过程中出错: {str(e)}")
                return None
                
        except Exception as e:
            utils.logger.error(f"发送私信时发生异常: {str(e)}")
            return None

    async def check_follow_status(self, sec_user_id: str):
        """
        检查是否已关注用户
        :param sec_user_id: 用户ID
        :return: 是否已关注
        """
        try:
            uri = "/aweme/v1/web/user/following/list/"
            params = {
                "sec_user_id": sec_user_id,
                "count": 1,
                "offset": 0,
                "min_time": 0,
                "max_time": int(time.time()),
                "source_type": 1,
                "gps_access": 0,
                "address_book_access": 0
            }
            headers = copy.copy(self.headers)
            headers["Referer"] = f"https://www.douyin.com/user/{sec_user_id}"
            
            # 先尝试API检查
            try:
                result = await self.get(uri, params, headers)
                if result and result.get("status_code") == 0:
                    utils.logger.info("API检查关注状态成功")
                    return True
            except Exception as e:
                utils.logger.info(f"API检查关注状态失败: {str(e)}")
            
            # 如果API检查失败，尝试从用户信息中获取关注状态
            user_info = await self.get_user_info(sec_user_id)
            if user_info and "user" in user_info:
                follow_status = user_info["user"].get("follow_status", 0)
                utils.logger.info(f"从用户信息获取关注状态: {follow_status}")
                return follow_status == 1  # 1表示已关注
            
            return False
            
        except Exception as e:
            utils.logger.error(f"检查关注状态时发生异常: {str(e)}")
            return False

    async def get_messages(self) -> List[Dict]:
        """获取用户收到的消息"""
        try:
            # 这里需要实现具体的消息获取API调用
            # 示例实现，实际需要根据抖音的API进行调整
            response = await self.session.get(
                "https://www.douyin.com/aweme/v1/web/im/fetch/",
                headers=self.headers
            )
            data = await response.json()
            
            if data.get("status_code") == 0:
                return data.get("messages", [])
            else:
                utils.logger.error(f"Failed to get messages: {data}")
                return []
        except Exception as e:
            utils.logger.error(f"Error getting messages: {e}")
            return []
