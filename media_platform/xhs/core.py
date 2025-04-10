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
import time
import json
from asyncio import Task
from typing import Dict, List, Optional, Tuple
import sys

from playwright.async_api import BrowserContext, BrowserType, Page, async_playwright
from tenacity import RetryError

import config
from base.base_crawler import AbstractCrawler
from config import CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
from model.m_xiaohongshu import NoteUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import xhs as xhs_store
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import XiaoHongShuClient
from .exception import DataFetchError
from .field import SearchSortType, NoteType, SearchNoteType
from .help import parse_note_info_from_note_url, get_search_id
from .login import XiaoHongShuLogin


class XiaoHongShuCrawler(AbstractCrawler):
    context_page: Page
    xhs_client: XiaoHongShuClient
    browser_context: BrowserContext
    _is_running: bool
    client: XiaoHongShuClient
    browser: BrowserType
    playwright: async_playwright

    def __init__(self) -> None:
        super().__init__()
        self.index_url = "https://www.xiaohongshu.com"
        # self.user_agent = utils.get_user_agent()
        self.user_agent = config.UA if config.UA else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self.cookie_file = "xhs_cookies.json"  # Cookie文件路径
        self._is_running = True
        self.client = None
        self.browser_context = None
        self.browser = None
        self.playwright = None
        self._init_browser()

    async def _init_browser(self):
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=config.HEADLESS,  # 使用配置文件中的HEADLESS设置
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--disable-notifications",
                    "--disable-extensions",
                    "--force-color-profile=srgb",
                    "--mute-audio",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                    "--disable-ipc-flooding-protection",
                    "--disable-renderer-backgrounding",
                    "--enable-features=NetworkService,NetworkServiceInProcess",
                    "--metrics-recording-only",
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--password-store=basic",
                    "--use-gl=swiftshader",
                    "--use-mock-keychain",
                ],
            )
            self.browser_context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            utils.logger.info("[XiaoHongShuCrawler._init_browser] Browser initialized successfully")
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuCrawler._init_browser] Failed to initialize browser: {str(e)}")
            raise

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
                        'domain': cookie.get('domain', '.xiaohongshu.com'),
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
            ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium, None, self.user_agent, headless=config.HEADLESS
            )
            
            # 加载Cookie
            cookies = self.load_cookies_from_file()
            if cookies:
                await self.browser_context.add_cookies(cookies)
                utils.logger.info("已成功加载Cookie")
            
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            # add a cookie attribute webId to avoid the appearance of a sliding captcha on the webpage
            await self.browser_context.add_cookies(
                [
                    {
                        "name": "webId",
                        "value": "xxx123",  # any value
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                    }
                ]
            )
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            # Create a client to interact with the xiaohongshu website.
            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            if not await self.xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.xhs_client.update_cookies(
                    browser_context=self.browser_context
                )

            utils.logger.info(f"[XiaoHongShuCrawler.start] Current config values - PLATFORM: {config.PLATFORM}, CRAWLER_TYPE: {config.CRAWLER_TYPE}, KEYWORDS: {config.KEYWORDS}")
            
            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            else:
                pass

            utils.logger.info("[XiaoHongShuCrawler.start] Xhs Crawler finished ...")

    async def search(self) -> None:
        """搜索笔记并获取评论信息"""
        utils.logger.info("[XiaoHongShuCrawler.search] 开始搜索小红书关键词")
        
        # 预热阶段
        try:
            await self.context_page.goto("https://www.xiaohongshu.com", timeout=60000)
            await asyncio.sleep(random.uniform(3, 5))
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuCrawler.search] 访问主页失败: {str(e)}")
            return
        
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[XiaoHongShuCrawler.search] 当前搜索关键词: {keyword}")
            page = config.START_PAGE
            
            while True:
                retry_count = 0
                max_retries = 3
                
                while retry_count < max_retries:
                    try:
                        utils.logger.info(f"[XiaoHongShuCrawler.search] 开始搜索第{page}页")
                        notes_res = await self.xhs_client.get_note_by_keyword(
                            keyword=keyword,
                            search_id=get_search_id(),
                            page=page,
                            page_size=20,
                            sort=SearchSortType.GENERAL
                        )
                        
                        if not notes_res or not notes_res.get("items", []):
                            utils.logger.warning(f"[XiaoHongShuCrawler.search] 第{page}页未获取到数据")
                            retry_count += 1
                            await asyncio.sleep(5)
                            continue
                        
                        valid_items = [
                            item for item in notes_res.get("items", [])
                            if item.get("model_type") not in ("rec_query", "hot_query")
                        ]
                        
                        if not valid_items:
                            utils.logger.warning("[XiaoHongShuCrawler.search] 没有找到有效的笔记")
                            return
                        
                        utils.logger.info(f"[XiaoHongShuCrawler.search] 找到{len(valid_items)}条有效笔记")
                        
                        # 创建信号量控制并发
                        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                        
                        # 分批处理笔记，每批5个
                        batch_size = 5
                        for i in range(0, len(valid_items), batch_size):
                            batch_items = valid_items[i:i + batch_size]
                            utils.logger.info(f"[XiaoHongShuCrawler.search] 开始处理第{i//batch_size + 1}批笔记，共{len(batch_items)}条")
                            
                            # 创建任务列表
                            tasks = []
                            for item in batch_items:
                                task = self.process_note_and_comments(
                                    note_id=item.get("id"),
                                    xsec_source=item.get("xsec_source"),
                                    xsec_token=item.get("xsec_token"),
                                    semaphore=semaphore
                                )
                                tasks.append(task)
                            
                            # 并发执行当前批次的任务
                            try:
                                results = await asyncio.wait_for(
                                    asyncio.gather(*tasks, return_exceptions=True),
                                    timeout=180  # 3分钟超时
                                )
                                
                                # 处理结果
                                processed_count = 0
                                for result in results:
                                    if isinstance(result, Exception):
                                        utils.logger.error(f"[XiaoHongShuCrawler.search] 处理笔记失败: {str(result)}")
                                        continue
                                        
                                    if result:
                                        note_detail, comments = result
                                        try:
                                            # 保存笔记信息
                                            await xhs_store.update_xhs_note(note_detail)
                                            
                                            # 保存作者信息
                                            user = note_detail.get("user", {})
                                            user_id = user.get("user_id")
                                            if user_id:
                                                await self.get_and_store_user(user_id)
                                            
                                            # 保存评论信息
                                            if comments:
                                                await self.batch_update_xhs_note_comments_and_store_user(
                                                    note_id=note_detail.get("note_id"),
                                                    comments=comments
                                                )
                                            
                                            # 获取媒体文件
                                            await self.get_notice_media(note_detail)
                                            
                                            processed_count += 1
                                        except Exception as e:
                                            utils.logger.error(f"[XiaoHongShuCrawler.search] 保存数据失败: {str(e)}")
                                            continue
                                
                                utils.logger.info(f"[XiaoHongShuCrawler.search] 成功处理第{i//batch_size + 1}批笔记，成功{processed_count}条")
                                
                                # 批次间增加随机延迟
                                await asyncio.sleep(random.uniform(2, 4))
                                
                            except asyncio.TimeoutError:
                                utils.logger.error(f"[XiaoHongShuCrawler.search] 处理第{i//batch_size + 1}批笔记超时")
                                continue
                            except Exception as e:
                                utils.logger.error(f"[XiaoHongShuCrawler.search] 处理第{i//batch_size + 1}批笔记失败: {str(e)}")
                                continue
                        
                        break  # 成功处理数据，跳出重试循环
                        
                    except DataFetchError as e:
                        utils.logger.error(f"[XiaoHongShuCrawler.search] 数据获取错误: {str(e)}")
                        retry_count += 1
                        await asyncio.sleep(10)
                    except Exception as e:
                        utils.logger.error(f"[XiaoHongShuCrawler.search] 意外错误: {str(e)}")
                        retry_count += 1
                        await asyncio.sleep(10)
                
                if retry_count >= max_retries:
                    utils.logger.error(f"[XiaoHongShuCrawler.search] 在{max_retries}次重试后仍然失败")
                    break
                
                page += 1
                await asyncio.sleep(random.uniform(config.REQUEST_MIN_INTERVAL, config.REQUEST_MAX_INTERVAL))

    async def process_note_and_comments(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore
    ) -> Tuple[Optional[Dict], Optional[List[Dict]]]:
        """处理笔记详情和评论
        
        Args:
            note_id: 笔记ID
            xsec_source: 来源
            xsec_token: 令牌
            semaphore: 并发控制信号量
            
        Returns:
            Tuple[Optional[Dict], Optional[List[Dict]]]: 笔记详情和评论列表
        """
        async with semaphore:
            try:
                utils.logger.info(f"[XiaoHongShuCrawler.process_note_and_comments] 开始处理笔记: {note_id}")
                
                # 设置获取笔记详情的超时时间
                try:
                    note_detail = await asyncio.wait_for(
                        self.get_note_detail_async_task(
                            note_id=note_id,
                            xsec_source=xsec_source,
                            xsec_token=xsec_token,
                            semaphore=semaphore
                        ),
                        timeout=30  # 30秒超时
                    )
                except asyncio.TimeoutError:
                    utils.logger.error(f"[XiaoHongShuCrawler.process_note_and_comments] 获取笔记详情超时: {note_id}")
                    return None, None
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.process_note_and_comments] 获取笔记详情失败: {note_id}, 错误: {str(e)}")
                    return None, None
                
                if not note_detail:
                    utils.logger.warning(f"[XiaoHongShuCrawler.process_note_and_comments] 未获取到笔记详情: {note_id}")
                    return None, None
                
                utils.logger.info(f"[XiaoHongShuCrawler.process_note_and_comments] 成功获取笔记详情: {note_id}")
                
                # 获取评论前增加延迟
                await asyncio.sleep(random.uniform(3, 5))
                
                # 获取评论
                comments = []
                if config.ENABLE_GET_COMMENTS:
                    try:
                        # 设置获取评论的超时时间
                        comments = await asyncio.wait_for(
                            self.get_comments_with_retry(
                                note_id=note_id,
                                xsec_token=xsec_token,
                                semaphore=semaphore
                            ),
                            timeout=60  # 60秒超时
                        )
                        utils.logger.info(f"[XiaoHongShuCrawler.process_note_and_comments] 成功获取评论: {note_id}, 评论数: {len(comments)}")
                    except asyncio.TimeoutError:
                        utils.logger.error(f"[XiaoHongShuCrawler.process_note_and_comments] 获取评论超时: {note_id}")
                    except Exception as e:
                        utils.logger.error(f"[XiaoHongShuCrawler.process_note_and_comments] 获取评论失败: {note_id}, 错误: {str(e)}")
                
                return note_detail, comments
                
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuCrawler.process_note_and_comments] 处理笔记和评论失败: {note_id}, 错误: {str(e)}")
                return None, None
            finally:
                # 确保释放信号量
                try:
                    semaphore.release()
                except Exception:
                    pass

    async def get_comments_with_retry(
        self,
        note_id: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore,
        max_retries: int = 3
    ) -> List[Dict]:
        """获取评论（带重试机制）
        
        Args:
            note_id: 笔记ID
            xsec_token: 令牌
            semaphore: 并发控制信号量
            max_retries: 最大重试次数
            
        Returns:
            List[Dict]: 评论列表
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                utils.logger.info(f"[XiaoHongShuCrawler.get_comments_with_retry] 开始获取评论: {note_id}, 第{retry_count + 1}次尝试")
                
                # 获取新的代理
                if config.ENABLE_IP_PROXY:
                    try:
                        ip_proxy_pool = await create_ip_pool(
                            config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
                        )
                        ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
                        _, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)
                        
                        # 更新客户端的代理
                        self.xhs_client.proxies = httpx_proxy_format
                        utils.logger.info(f"[XiaoHongShuCrawler.get_comments_with_retry] 已更新代理: {httpx_proxy_format}")
                    except Exception as e:
                        utils.logger.error(f"[XiaoHongShuCrawler.get_comments_with_retry] 更新代理失败: {str(e)}")
                
                # 更新请求头
                try:
                    # 获取新的签名数据
                    await self.xhs_client.update_signature_data()
                    # 更新User-Agent
                    await self.xhs_client._rotate_user_agent()
                    utils.logger.info("[XiaoHongShuCrawler.get_comments_with_retry] 已更新请求头和签名数据")
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.get_comments_with_retry] 更新请求头失败: {str(e)}")
                
                # 增加随机延迟
                await asyncio.sleep(random.uniform(2, 4))
                
                comments = []
                await self.xhs_client.get_note_all_comments(
                    note_id=note_id,
                    xsec_token=xsec_token,
                    crawl_interval=random.uniform(1, config.CRAWLER_MAX_SLEEP_SEC),
                    callback=None,  # 不使用回调，直接返回评论列表
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
                )
                
                utils.logger.info(f"[XiaoHongShuCrawler.get_comments_with_retry] 成功获取评论: {note_id}, 评论数: {len(comments)}")
                return comments
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    utils.logger.error(f"[XiaoHongShuCrawler.get_comments_with_retry] 获取评论失败，已重试{max_retries}次: {note_id}, 错误: {str(e)}")
                    return []
                    
                wait_time = random.uniform(5, 10)  # 增加重试等待时间
                utils.logger.warning(f"[XiaoHongShuCrawler.get_comments_with_retry] 获取评论失败，等待{wait_time}秒后重试: {note_id}, 错误: {str(e)}")
                await asyncio.sleep(wait_time)

    async def get_creators_and_notes(self):
        """获取创作者笔记和评论"""
        utils.logger.info(
            "[XiaoHongShuCrawler.get_creators_and_notes] Begin get xiaohongshu creators"
        )
        
        utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 配置文件中的关键词: {config.KEYWORDS}")
        utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 当前使用的关键词来源: {'命令行参数' if len(sys.argv) > 1 and '--keywords' in sys.argv else '配置文件'}")
        
        # 用于存储已处理的创作者信息
        processed_creators = {}
        
        xhs_limit_count = 20  # xhs limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < xhs_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = xhs_limit_count
        start_page = config.START_PAGE
        
        # 确保使用配置文件中设置的关键词
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 使用配置的关键词: {keyword}")
            
            page = 1
            search_id = get_search_id()
            while (page - start_page + 1) * xhs_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(
                        f"[XiaoHongShuCrawler.get_creators_and_notes] search xhs keyword: {keyword}, page: {page}"
                    )
                    
                    # 直接使用配置的关键词进行搜索
                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,  # 确保使用配置的关键词
                        search_id=search_id,
                        page=page,
                        sort=(
                            SearchSortType(config.SORT_TYPE)
                            if config.SORT_TYPE != ""
                            else SearchSortType.GENERAL
                        ),
                        note_type=SearchNoteType.ALL,  # 使用SearchNoteType.ALL来获取所有类型的笔记
                    )
                    
                    utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Current page: {page}, Search ID: {search_id}")
                    
                    if not notes_res:
                        utils.logger.warning("[XiaoHongShuCrawler.get_creators_and_notes] Empty search response")
                        break
                        
                    if not notes_res.get("has_more", False):
                        utils.logger.info("[XiaoHongShuCrawler.get_creators_and_notes] No more content!")
                        break
                    
                    items = notes_res.get("items", [])
                    utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Found {len(items)} items")
                    
                    if not items:
                        utils.logger.warning("[XiaoHongShuCrawler.get_creators_and_notes] No items in search response")
                        break
                    
                    # 直接处理搜索结果中的笔记
                    for post_item in items:
                        if post_item.get("model_type") in ("rec_query", "hot_query"):
                            utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Skipping item with model_type: {post_item.get('model_type')}")
                            continue
                            
                        # 获取作者信息 - 修复获取用户ID的逻辑
                        note_card = post_item.get("note_card", {})
                        user_info = note_card.get("user", {})
                        user_id = user_info.get("user_id")
                        
                        utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Processing post_item: {post_item}")
                        
                        if not user_id:
                            # 尝试从其他位置获取user_id
                            user_id = note_card.get("user_id") or post_item.get("user_id")
                            if not user_id:
                                utils.logger.warning(f"[XiaoHongShuCrawler.get_creators_and_notes] No user_id found in post item: {post_item}")
                                continue
                            
                        utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Found user_id: {user_id}")
                        
                        # 构建笔记信息
                        image_list = note_card.get("image_list", [])
                        
                        # 构建笔记信息
                        note_info = {
                            "note_id": post_item.get("id"),
                            "type": note_card.get("type", ""),
                            "title": note_card.get("display_title", "") or note_card.get("desc", "")[:255],
                            "desc": note_card.get("desc", ""),
                            "video_url": note_card.get("video", {}).get("url", ""),
                            "time": note_card.get("time", 0),  # 发布时间戳
                            "last_update_time": note_card.get("last_update_time", 0),  # 最后更新时间戳
                            "user_id": user_id,  # 确保 user_id 是字符串类型
                            "nickname": user_info.get("nickname", ""),
                            "avatar": user_info.get("avatar", ""),
                            "ip_location": note_card.get("ip_location", ""),
                            "liked_count": str(note_card.get("interact_info", {}).get("liked_count", "0")),
                            "collected_count": str(note_card.get("interact_info", {}).get("collected_count", "0")),
                            "comment_count": str(note_card.get("interact_info", {}).get("comment_count", "0")),
                            "share_count": str(note_card.get("interact_info", {}).get("shared_count", "0")),
                            "image_list": ",".join([
                                f"https://sns-img-qc.xhscdn.com/{img.get('trace_id', '')}"
                                for img in image_list
                                if isinstance(img, dict) and img.get('trace_id')
                            ]) if isinstance(image_list, list) else "",
                            "tag_list": ",".join([
                                tag.get("name", "") 
                                for tag in note_card.get("tag_list", []) 
                                if isinstance(tag, dict) and tag.get("type") == "topic"
                            ]),
                            "xsec_token": post_item.get("xsec_token", ""),
                            "source_keyword": source_keyword_var.get(),
                            "add_ts": utils.get_current_timestamp(),
                            "last_modify_ts": utils.get_current_timestamp()
                        }
                        
                        # 验证必要字段
                        if not note_info["note_id"] or not note_info["user_id"]:
                            utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Missing required fields in note_info: {note_info}")
                            continue
                        
                        # 保存笔记信息到数据库
                        try:
                                
                            # 直接使用note_info，不要修改它
                            await xhs_store.update_xhs_note(note_info)
                            utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 成功保存笔记信息: {note_info['note_id']}")
                        except Exception as e:
                            utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 保存笔记信息失败: {str(e)}")
                            utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 失败的笔记信息: {note_info}")
                            continue
                        
                        # 立即保存作者信息，不再等待
                        try:
                            # 构建作者基本信息
                            creator_info = {
                                "user_id": user_id,
                                "nickname": user_info.get("nickname", ""),
                                "avatar": user_info.get("avatar", ""),
                                "desc": user_info.get("desc", ""),
                                "ip_location": user_info.get("ip_location", ""),
                                "gender": user_info.get("gender", ""),
                                "age": user_info.get("age", ""),
                                "followers": user_info.get("followers", 0),
                                "following": user_info.get("following", 0),
                                "notes": []  # 初始化为空列表
                            }
                            
                            # 获取完整作者信息
                            try:
                                full_creator_info = await self.xhs_client.get_creator_info(user_id=user_id)
                                if full_creator_info:
                                    # 更新完整信息
                                    creator_info.update(full_creator_info)
                                    utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 成功获取作者完整信息: {user_id}")
                                else:
                                    utils.logger.warning(f"[XiaoHongShuCrawler.get_creators_and_notes] 获取作者完整信息失败，使用基本信息: {user_id}")
                            except Exception as e:
                                utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 获取作者完整信息失败: {str(e)}")
                            
                            # 创建简化的笔记信息
                            simplified_note = {
                                "title": note_info["title"],
                                "desc": note_info["desc"],
                                "note_id": note_info["note_id"]}
                            
                            # 更新笔记列表
                            if user_id in processed_creators:
                                # 如果作者已存在，更新笔记列表（限制最多3篇）
                                current_notes = processed_creators[user_id].get("notes", [])  
                                current_notes.append(simplified_note)
                                creator_info["notes"] = current_notes
                                utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 为已存在作者添加笔记: {user_id}, 当前笔记数: {len(current_notes)}")
                            else:
                                # 如果是新作者，初始化笔记列表
                                creator_info["notes"] = [simplified_note]
                                utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 为新作者创建笔记列表: {user_id}")
                            
                            # 立即保存作者信息到数据库
                            utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 开始保存作者信息到数据库: {user_id}")
                            try:
                                # 确保notes字段是JSON字符串
                                creator_info["notes"] = json.dumps(creator_info["notes"], ensure_ascii=False)
                                await xhs_store.save_creator(user_id, creator=creator_info)
                                utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] 成功保存作者信息: {user_id}, notes: {creator_info['notes']}")
                            except Exception as e:
                                utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 保存作者信息到数据库失败: {str(e)}")
                                # 打印更详细的错误信息
                                import traceback
                                utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 错误详情: {traceback.format_exc()}")
                            
                            # 更新已处理作者列表
                            processed_creators[user_id] = creator_info
                        except Exception as e:
                            utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] 处理作者信息失败: {str(e)}")
                            continue
                            
                    page += 1
                    await asyncio.sleep(2)  # 增加延迟，避免请求过快
                    
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Error: {str(e)}")
                    break
                    
        utils.logger.info(
            f"[XiaoHongShuCrawler.get_creators_and_notes] End get xiaohongshu creators, total: {len(processed_creators)}"
        )
    
    async def get_and_store_user(self, user_id: str):
        """
        保存用户信息
        """
        # 获取完整作者信息
        try:
            creator_info = await self.xhs_client.get_creator_info(user_id=user_id)
            utils.logger.info(f"[XiaoHongShuCrawler.get_and_store_user] 成功获取作者完整信息: {creator_info}")
            
            await xhs_store.save_creator(user_id, creator=creator_info)
            utils.logger.info(f"[XiaoHongShuCrawler.get_and_store_user] 成功保存作者信息: {user_id}")
        
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuCrawler.get_and_store_user] 获取作者完整信息失败: {str(e)}")
            # 打印更详细的错误信息
            import traceback
            utils.logger.error(f"[XiaoHongShuCrawler.get_and_store_user] 错误详情: {traceback.format_exc()}")
            
             
    async def get_specified_notes(self):
        """
        Get the information and comments of the specified post
        must be specified note_id, xsec_source, xsec_token⚠️⚠️⚠️
        Returns:

        """
        get_note_detail_task_list = []
        for full_note_url in config.XHS_SPECIFIED_NOTE_URL_LIST:
            note_url_info: NoteUrlInfo = parse_note_info_from_note_url(full_note_url)
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_specified_notes] Parse note url info: {note_url_info}"
            )
            crawler_task = self.get_note_detail_async_task(
                note_id=note_url_info.note_id,
                xsec_source=note_url_info.xsec_source,
                xsec_token=note_url_info.xsec_token,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_note_ids = []
        xsec_tokens = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for note_detail in note_details:
            if note_detail:
                need_get_comment_note_ids.append(note_detail.get("note_id", ""))
                xsec_tokens.append(note_detail.get("xsec_token", ""))
                await xhs_store.update_xhs_note(note_detail)
        await self.batch_get_note_comments(need_get_comment_note_ids, xsec_tokens)

    async def get_note_detail_async_task(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict]:
        """Get note detail

        Args:
            note_id:
            xsec_source:
            xsec_token:
            semaphore:

        Returns:
            Dict: note detail
        """
        note_detail_from_html, note_detail_from_api = None, None
        async with semaphore:
            # When proxy is not enabled, increase the crawling interval
            if config.ENABLE_IP_PROXY:
                crawl_interval = random.random()
            else:
                crawl_interval = random.uniform(1, config.CRAWLER_MAX_SLEEP_SEC)
            try:
                # 尝试直接获取网页版笔记详情，携带cookie
                note_detail_from_html: Optional[Dict] = (
                    await self.xhs_client.get_note_by_id_from_html(
                        note_id, xsec_source, xsec_token, enable_cookie=True
                    )
                )
                time.sleep(crawl_interval)
                if not note_detail_from_html:
                    # 如果网页版笔记详情获取失败，则尝试不使用cookie获取
                    note_detail_from_html = (
                        await self.xhs_client.get_note_by_id_from_html(
                            note_id, xsec_source, xsec_token, enable_cookie=False
                        )
                    )
                    utils.logger.error(
                        f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error, note_id: {note_id}"
                    )
                if not note_detail_from_html:
                    # 如果网页版笔记详情获取失败，则尝试API获取
                    note_detail_from_api: Optional[Dict] = (
                        await self.xhs_client.get_note_by_id(
                            note_id, xsec_source, xsec_token
                        )
                    )
                note_detail = note_detail_from_html or note_detail_from_api
                if note_detail:
                    note_detail.update(
                        {"xsec_token": xsec_token, "xsec_source": xsec_source}
                    )
                    return note_detail
            except DataFetchError as ex:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error: {ex}"
                )
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_async_task] have not fund note detail note_id:{note_id}, err: {ex}"
                )
                return None

    async def batch_get_note_comments(
        self, note_list: List[str], xsec_tokens: List[str]
    ):
        """Batch get note comments"""
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[XiaoHongShuCrawler.batch_get_note_comments] Crawling comment mode is not enabled"
            )
            return

        utils.logger.info(
            f"[XiaoHongShuCrawler.batch_get_note_comments] Begin batch get note comments, note list: {note_list}"
        )
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for index, note_id in enumerate(note_list):
            task = asyncio.create_task(
                self.get_comments(
                    note_id=note_id, xsec_token=xsec_tokens[index], semaphore=semaphore
                ),
                name=note_id,
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def batch_update_xhs_note_comments_and_store_user(self, note_id: str, comments: List[Dict]):
        """
        批量更新小红书笔记评论和保存用户
        Args:
            note_id:
            comments:

        Returns:

        """
        if not comments:
            return
        # 批量更新
        xhs_store.batch_update_xhs_note_comments(note_id, comments)
        for comment_item in comments:
            await self.get_and_store_user(comment_item.get("user_id"))


    async def get_comments(
        self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore
    ):
        """Get note comments with keyword filtering and quantity limitation"""
        async with semaphore:
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_comments] Begin get note id comments {note_id}"
            )
            # When proxy is not enabled, increase the crawling interval
            if config.ENABLE_IP_PROXY:
                crawl_interval = random.random()
            else:
                crawl_interval = random.uniform(1, config.CRAWLER_MAX_SLEEP_SEC)
            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=self.batch_update_xhs_note_comments_and_store_user,
                max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
            )

    @staticmethod
    def format_proxy_info(
        ip_proxy_info: IpInfoModel,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
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

    async def create_xhs_client(self, httpx_proxy: Optional[str]) -> XiaoHongShuClient:
        """Create xhs client"""
        utils.logger.info(
            "[XiaoHongShuCrawler.create_xhs_client] Begin create xiaohongshu API client ..."
        )
        cookie_str, cookie_dict = utils.convert_cookies(
            await self.browser_context.cookies()
        )
        xhs_client_obj = XiaoHongShuClient(
            proxies=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://www.xiaohongshu.com",
                "Referer": "https://www.xiaohongshu.com",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return xhs_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
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
                viewport={"width": 1024, "height": 768},  # 使用更合理的窗口大小
                user_agent=user_agent,
                args=[
                    '--disable-blink-features=AutomationControlled',  # 禁用自动化控制检测
                    '--disable-infobars',  # 禁用信息栏
                    '--no-sandbox',  # 禁用沙箱模式
                    '--disable-setuid-sandbox',  # 禁用setuid沙箱
                    '--disable-dev-shm-usage',  # 禁用/dev/shm使用
                    '--disable-accelerated-2d-canvas',  # 禁用加速2D画布
                    '--disable-gpu'  # 禁用GPU加速
                ]
            )  # type: ignore
            return browser_context
        else:
            browser = await chromium.launch(
                headless=headless, 
                proxy=playwright_proxy,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu'
                ]
            )  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1024, "height": 768},
                user_agent=user_agent
            )
            return browser_context

    async def close(self):
        """关闭浏览器和清理资源"""
        try:
            if self.client:
                self.client = None
                utils.logger.info("[XiaoHongShuCrawler.close] Client closed")

            if self.browser_context:
                try:
                    await asyncio.wait_for(self.browser_context.close(), timeout=30)  # 增加超时时间到30秒
                    utils.logger.info("[XiaoHongShuCrawler.close] Browser context closed")
                except asyncio.TimeoutError:
                    utils.logger.error("[XiaoHongShuCrawler.close] Timeout while closing browser context")
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.close] Error closing browser context: {str(e)}")
                finally:
                    self.browser_context = None

            if self.browser:
                try:
                    await asyncio.wait_for(self.browser.close(), timeout=30)  # 增加超时时间到30秒
                    utils.logger.info("[XiaoHongShuCrawler.close] Browser closed")
                except asyncio.TimeoutError:
                    utils.logger.error("[XiaoHongShuCrawler.close] Timeout while closing browser")
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.close] Error closing browser: {str(e)}")
                finally:
                    self.browser = None

            if self.playwright:
                try:
                    await self.playwright.stop()
                    utils.logger.info("[XiaoHongShuCrawler.close] Playwright stopped")
                except Exception as e:
                    utils.logger.error(f"[XiaoHongShuCrawler.close] Error stopping playwright: {str(e)}")
                finally:
                    self.playwright = None

        except Exception as e:
            utils.logger.error(f"[XiaoHongShuCrawler.close] Error during cleanup: {str(e)}")
            raise

    async def get_notice_media(self, note_detail: Dict):
        if not config.ENABLE_GET_IMAGES:
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_notice_media] Crawling image mode is not enabled"
            )
            return
        await self.get_note_images(note_detail)
        await self.get_notice_video(note_detail)

    async def get_note_images(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")
        image_list: List[Dict] = note_item.get("image_list", [])

        for img in image_list:
            if img.get("url_default") != "":
                img.update({"url": img.get("url_default")})

        if not image_list:
            return
        picNum = 0
        for pic in image_list:
            url = pic.get("url")
            if not url:
                continue
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{picNum}.jpg"
            picNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)

    async def get_notice_video(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")

        videos = xhs_store.get_video_url_arr(note_item)

        if not videos:
            return
        videoNum = 0
        for url in videos:
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{videoNum}.mp4"
            videoNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)
