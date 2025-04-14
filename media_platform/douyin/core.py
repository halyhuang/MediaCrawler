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
import os
import random
import json
from asyncio import Task
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import (BrowserContext, BrowserType, Page,
                                  async_playwright)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import douyin as douyin_store
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import DOUYINClient
from .exception import DataFetchError
from .field import PublishTimeType
from .login import DouYinLogin
from .cache import ExpiringLocalCache


class DouYinCrawler(AbstractCrawler):
    context_page: Page
    dy_client: DOUYINClient
    browser_context: BrowserContext
    playwright: Any
    local_cache: ExpiringLocalCache

    def __init__(self) -> None:
        self.index_url = "https://www.douyin.com"
        self.playwright = None
        self.cookie_file = "douyin_cookies.json"  # Cookie文件路径
        self.local_cache = ExpiringLocalCache()

    def load_cookies_from_file(self) -> List[Dict]:
        """从文件加载Cookie"""
        try:
            if os.path.exists(self.cookie_file):
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                # 转换Cookie格式
                formatted_cookies = []
                for cookie in cookies:
                    formatted_cookie = {
                        'name': cookie.get('name', ''),
                        'value': cookie.get('value', ''),
                        'domain': cookie.get('domain', '.douyin.com'),
                        'path': cookie.get('path', '/'),
                        'sameSite': 'Lax',  # 设置sameSite属性
                        'secure': cookie.get('secure', True),
                        'httpOnly': cookie.get('httpOnly', True)
                    }
                    formatted_cookies.append(formatted_cookie)
                utils.logger.info(f"成功从{self.cookie_file}加载Cookie")
                return formatted_cookies
            else:
                utils.logger.warning(f"Cookie文件{self.cookie_file}不存在")
                return []
        except Exception as e:
            utils.logger.error(f"加载Cookie文件失败: {str(e)}")
            return []

    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        # 启动本地缓存清理任务
        await self.local_cache.start()

        self.playwright = await async_playwright().start()
        # Launch a browser context.
        chromium = self.playwright.chromium
        self.browser_context = await self.launch_browser(
            chromium,
            None,
            user_agent=None,
            headless=config.HEADLESS
        )
        # stealth.min.js is a js script to prevent the website from detecting the crawler.
        await self.browser_context.add_init_script(path="libs/stealth.min.js")
        
        # 加载Cookie
        cookies = self.load_cookies_from_file()
        if cookies:
            await self.browser_context.add_cookies(cookies)
            utils.logger.info("已成功加载Cookie")
            
        self.context_page = await self.browser_context.new_page()
        await self.context_page.goto(self.index_url)

        self.dy_client = await self.create_douyin_client(httpx_proxy_format)
        if not await self.dy_client.pong(browser_context=self.browser_context):
            login_obj = DouYinLogin(
                login_type=config.LOGIN_TYPE,
                login_phone="",  # you phone number
                browser_context=self.browser_context,
                context_page=self.context_page,
                cookie_str=config.COOKIES
            )
            await login_obj.begin()
            await self.dy_client.update_cookies(browser_context=self.browser_context)
            
            # 保存Cookie到文件
            cookies = await self.browser_context.cookies()
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            utils.logger.info(f"已保存Cookie到{self.cookie_file}")

        utils.logger.info("[DouYinCrawler.start] Douyin Crawler started successfully...")

        crawler_type_var.set(config.CRAWLER_TYPE)
        if config.CRAWLER_TYPE == "search":
            # Search for notes and retrieve their comment information.
            await self.search()
        elif config.CRAWLER_TYPE == "detail":
            # Get the information and comments of the specified post
            await self.get_specified_awemes()
        elif config.CRAWLER_TYPE == "creator":
            # Get the information and comments of the specified creator
            await self.get_creators_and_videos()

    async def search(self) -> None:
        utils.logger.info("[DouYinCrawler.search] Begin search douyin keywords")
        dy_limit_count = 10  # douyin limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < dy_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = dy_limit_count
        start_page = config.START_PAGE  # start page number
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[DouYinCrawler.search] Current keyword: {keyword}")
            aweme_list: List[str] = []
            page = 0
            dy_search_id = ""
            while (page - start_page + 1) * dy_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[DouYinCrawler.search] Skip {page}")
                    page += 1
                    continue
                try:
                    utils.logger.info(f"[DouYinCrawler.search] search douyin keyword: {keyword}, page: {page}")
                    posts_res = await self.dy_client.search_info_by_keyword(keyword=keyword,
                                                                            offset=page * dy_limit_count - dy_limit_count,
                                                                            publish_time=PublishTimeType(config.PUBLISH_TIME_TYPE),
                                                                            search_id=dy_search_id
                                                                            )
                except DataFetchError:
                    utils.logger.error(f"[DouYinCrawler.search] search douyin keyword: {keyword} failed")
                    break

                page += 1
                if "data" not in posts_res:
                    utils.logger.error(
                        f"[DouYinCrawler.search] search douyin keyword: {keyword} failed，账号也许被风控了。")
                    break
                dy_search_id = posts_res.get("extra", {}).get("logid", "")
                for post_item in posts_res.get("data"):
                    try:
                        aweme_info: Dict = post_item.get("aweme_info") or \
                                           post_item.get("aweme_mix_info", {}).get("mix_items")[0]
                    except TypeError:
                        continue
                    aweme_list.append(aweme_info.get("aweme_id", ""))
                    await douyin_store.update_douyin_aweme(aweme_item=aweme_info)
            utils.logger.info(f"[DouYinCrawler.search] keyword:{keyword}, aweme_list:{aweme_list}")
            await self.batch_get_note_comments(aweme_list)

    async def get_specified_awemes(self):
        """Get the information and comments of the specified post"""
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_aweme_detail(aweme_id=aweme_id, semaphore=semaphore) for aweme_id in config.DY_SPECIFIED_ID_LIST
        ]
        aweme_details = await asyncio.gather(*task_list)
        for aweme_detail in aweme_details:
            if aweme_detail is not None:
                await douyin_store.update_douyin_aweme(aweme_detail)
        await self.batch_get_note_comments(config.DY_SPECIFIED_ID_LIST)

    async def get_aweme_detail(self, aweme_id: str, semaphore: asyncio.Semaphore) -> Any:
        """Get note detail"""
        async with semaphore:
            try:
                return await self.dy_client.get_video_by_id(aweme_id)
            except DataFetchError as ex:
                utils.logger.error(f"[DouYinCrawler.get_aweme_detail] Get aweme detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[DouYinCrawler.get_aweme_detail] have not fund note detail aweme_id:{aweme_id}, err: {ex}")
                return None

    async def batch_get_note_comments(self, aweme_list: List[str]) -> None:
        """
        Batch get note comments
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[DouYinCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        task_list: List[Task] = []
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        for aweme_id in aweme_list:
            task = asyncio.create_task(
                self.get_comments(aweme_id, semaphore), name=aweme_id)
            task_list.append(task)
        if len(task_list) > 0:
            await asyncio.wait(task_list)

    async def get_comments(self, aweme_id: str, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            try:
                # 将关键词列表传递给 get_aweme_all_comments 方法
                await self.dy_client.get_aweme_all_comments(
                    aweme_id=aweme_id,
                    crawl_interval=random.random(),
                    is_fetch_sub_comments=config.ENABLE_GET_SUB_COMMENTS,
                    callback=douyin_store.batch_update_dy_aweme_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
                )
                utils.logger.info(
                    f"[DouYinCrawler.get_comments] aweme_id: {aweme_id} comments have all been obtained and filtered ...")
            except DataFetchError as e:
                utils.logger.error(f"[DouYinCrawler.get_comments] aweme_id: {aweme_id} get comments failed, error: {e}")

    async def get_creators_and_videos(self) -> None:
        """
        Get the information and videos of the specified creator
        """
        utils.logger.info("[DouYinCrawler.get_creators_and_videos] Begin get douyin creators")
        for user_id in config.DY_CREATOR_ID_LIST:
            creator_info: Dict = await self.dy_client.get_user_info(user_id)
            if creator_info:
                await douyin_store.save_creator(user_id, creator=creator_info)

            # Get all video information of the creator
            all_video_list = await self.dy_client.get_all_user_aweme_posts(
                sec_user_id=user_id,
                callback=self.fetch_creator_video_detail
            )

            video_ids = [video_item.get("aweme_id") for video_item in all_video_list]
            await self.batch_get_note_comments(video_ids)

    async def fetch_creator_video_detail(self, video_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_aweme_detail(post_item.get("aweme_id"), semaphore) for post_item in video_list
        ]

        note_details = await asyncio.gather(*task_list)
        for aweme_item in note_details:
            if aweme_item is not None:
                await douyin_store.update_douyin_aweme(aweme_item)

    @staticmethod
    def format_proxy_info(ip_proxy_info: IpInfoModel) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_douyin_client(self, httpx_proxy: Optional[str]) -> DOUYINClient:
        """Create douyin client"""
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())  # type: ignore
        douyin_client = DOUYINClient(
            proxies=httpx_proxy,
            headers={
                "User-Agent": await self.context_page.evaluate("() => navigator.userAgent"),
                "Cookie": cookie_str,
                "Host": "www.douyin.com",
                "Origin": "https://www.douyin.com/",
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8"
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return douyin_client

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 2560, "height": 1440},  # 增加窗口大小
                user_agent=user_agent,
                args=[
                    '--start-maximized',  # 最大化窗口
                    '--disable-blink-features=AutomationControlled',  # 禁用自动化控制检测
                    '--disable-infobars',  # 禁用信息栏
                    '--window-size=2560,1440'  # 设置窗口大小
                ]
            )  # type: ignore
            return browser_context
        else:
            browser = await chromium.launch(
                headless=headless, 
                proxy=playwright_proxy,
                args=[
                    '--start-maximized',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=2560,1440'
                ]
            )  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 2560, "height": 1440},
                user_agent=user_agent
            )
            return browser_context

    async def close(self) -> None:
        """Close browser context"""
        try:
            # 关闭本地缓存清理任务
            await self.local_cache.stop()
            
            if hasattr(self, 'browser_context') and self.browser_context:
                await self.browser_context.close()
            if hasattr(self, 'playwright') and self.playwright:
                await self.playwright.stop()
            utils.logger.info("[DouYinCrawler.close] Browser context closed ...")
        except Exception as e:
            utils.logger.error(f"[DouYinCrawler.close] Error closing crawler: {e}")

    async def search_and_follow_user(self, user_keyword: str) -> None:
        """
        搜索用户并关注
        :param user_keyword: 用户关键词
        """
        utils.logger.info(f"[DouYinCrawler.search_and_follow_user] Begin search douyin user: {user_keyword}")
        try:
            search_res = await self.dy_client.search_user_by_keyword(keyword=user_keyword)
            if "user_list" not in search_res:
                utils.logger.error(f"[DouYinCrawler.search_and_follow_user] search user failed, response: {search_res}")
                return
            
            user_list = search_res.get("user_list", [])
            if not user_list:
                utils.logger.info(f"[DouYinCrawler.search_and_follow_user] No user found for keyword: {user_keyword}")
                return
                
            # 获取第一个用户
            first_user = user_list[0]
            user_info = first_user.get("user_info", {})
            sec_user_id = user_info.get("sec_uid", "")
            nickname = user_info.get("nickname", "")
            
            if not sec_user_id:
                utils.logger.error(f"[DouYinCrawler.search_and_follow_user] Cannot get sec_user_id for user: {nickname}")
                return
                
            # 关注用户
            utils.logger.info(f"[DouYinCrawler.search_and_follow_user] Following user: {nickname}")
            follow_res = await self.dy_client.follow_user(sec_user_id)
            utils.logger.info(f"[DouYinCrawler.search_and_follow_user] Follow result: {follow_res}")
            
        except DataFetchError as e:
            utils.logger.error(f"[DouYinCrawler.search_and_follow_user] Error: {e}")
            return

    async def follow_user_by_sec_uid(self, sec_uid: str):
        """
        通过sec_uid关注用户并发送私信
        :param sec_uid: 用户sec_uid
        :return: 关注结果
        """
        try:
            # 1. 获取用户信息
            user_info = await self.dy_client.get_user_info(sec_uid)
            if not user_info:
                utils.logger.error("获取用户信息失败")
                return None
            
            # 2. 获取用户昵称
            nickname = user_info.get("user", {}).get("nickname")
            if not nickname:
                utils.logger.error("获取用户昵称失败")
                return None
            
            utils.logger.info(f"开始处理用户: {nickname}")
            
            # 3. 访问用户主页
            profile_url = f"https://www.douyin.com/user/{sec_uid}"
            utils.logger.info(f"访问用户主页: {profile_url}")
            
            try:
                await self.context_page.goto(profile_url, timeout=5000)
                utils.logger.info("页面导航完成")
            except Exception as e:
                utils.logger.warning(f"页面导航超时，继续执行: {str(e)}")
            
            try:
                await self.context_page.wait_for_load_state("domcontentloaded", timeout=3000)
                utils.logger.info("DOM加载完成")
            except Exception as e:
                utils.logger.warning(f"DOM加载超时，继续执行: {str(e)}")
            
            await asyncio.sleep(1)
            
            # 4. 检查关注状态
            utils.logger.info("检查用户关注状态")
            is_following = await self.dy_client.check_follow_status(sec_uid)
            
            if is_following:
                utils.logger.info("用户已经关注，直接发送私信")
                try:
                    utils.logger.info("开始发送私信")
                    message_result = await self.dy_client.send_private_message(sec_uid)
                    if message_result:
                        utils.logger.info("私信发送成功")
                    else:
                        utils.logger.error("私信发送失败")
                except Exception as msg_e:
                    utils.logger.error(f"发送私信时发生异常: {str(msg_e)}")
                return {"status_code": 0, "status_msg": "already followed"}
            
            # 5. 如果未关注，执行关注操作
            utils.logger.info("用户未关注，开始执行关注操作")
            follow_result = await self.dy_client.follow_user(sec_uid)
            
            if follow_result:
                if follow_result.get("status_msg") == "success":
                    utils.logger.info("关注成功，准备发送私信")
                    await asyncio.sleep(1)  # 等待关注状态生效
                    
                    try:
                        utils.logger.info("开始发送私信")
                        message_result = await self.dy_client.send_private_message(sec_uid)
                        if message_result:
                            utils.logger.info("私信发送成功")
                        else:
                            utils.logger.error("私信发送失败")
                    except Exception as msg_e:
                        utils.logger.error(f"发送私信时发生异常: {str(msg_e)}")
                        
                return follow_result
            else:
                utils.logger.error("关注失败")
                return None
                
        except Exception as e:
            utils.logger.error(f"关注用户时发生异常: {str(e)}")
            return None

    async def test_search_user_by_sec_uid(self, sec_uid: str) -> None:
        """
        测试通过sec_uid搜索用户
        :param sec_uid: 用户的sec_uid
        """
        utils.logger.info(f"[DouYinCrawler.test_search_user_by_sec_uid] Begin test search user for sec_uid: {sec_uid}")
        try:
            # 先获取用户信息
            user_info = await self.dy_client.get_user_info(sec_uid)
            if not user_info:
                utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Cannot get user info for sec_uid: {sec_uid}")
                return
                
            if "user" not in user_info:
                utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Invalid user info response: {user_info}")
                return
                
            user = user_info.get("user", {})
            nickname = user.get("nickname", "")
            
            if not nickname:
                utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Cannot get nickname for sec_uid: {sec_uid}")
                return
            
            # 通过昵称搜索用户
            utils.logger.info(f"[DouYinCrawler.test_search_user_by_sec_uid] Searching user by nickname: {nickname}")
            search_res = await self.dy_client.search_user_by_keyword(keyword=nickname)
            
            if "user_list" not in search_res:
                utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Search failed, response: {search_res}")
                return
                
            user_list = search_res.get("user_list", [])
            if not user_list:
                utils.logger.info(f"[DouYinCrawler.test_search_user_by_sec_uid] No user found for nickname: {nickname}")
                return
            
            # 验证搜索结果中是否包含目标用户
            target_user_found = False
            for user_item in user_list:
                user_info = user_item.get("user_info", {})
                if user_info.get("sec_uid") == sec_uid:
                    target_user_found = True
                    utils.logger.info(f"[DouYinCrawler.test_search_user_by_sec_uid] Found target user in search results: {nickname}")
                    break
            
            if not target_user_found:
                utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Target user not found in search results: {nickname}")
                return
                
            utils.logger.info(f"[DouYinCrawler.test_search_user_by_sec_uid] Test completed successfully")
            
        except DataFetchError as e:
            utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Error: {e}")
            return
        except Exception as e:
            utils.logger.error(f"[DouYinCrawler.test_search_user_by_sec_uid] Unexpected error: {e}")
            return
