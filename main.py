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
import sys
import argparse
import traceback

import cmd_arg
import config
import db
from tools import utils
from base.base_crawler import AbstractCrawler
from media_platform.bilibili import BilibiliCrawler
from media_platform.douyin import DouYinCrawler
from media_platform.kuaishou import KuaishouCrawler
from media_platform.tieba import TieBaCrawler
from media_platform.weibo import WeiboCrawler
from media_platform.xhs import XiaoHongShuCrawler
from media_platform.zhihu import ZhihuCrawler
from store.douyin.douyin_store_sql import media_crawler_db_var
from media_platform.douyin.message_listener import DouYinMessageListener
from var import crawler_type_var, source_keyword_var


class CrawlerFactory:
    CRAWLERS = {
        "xhs": XiaoHongShuCrawler,
        "dy": DouYinCrawler,
        "ks": KuaishouCrawler,
        "bili": BilibiliCrawler,
        "wb": WeiboCrawler,
        "tieba": TieBaCrawler,
        "zhihu": ZhihuCrawler
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError("Invalid Media Platform Currently only supported xhs or dy or ks or bili ...")
        return crawler_class()


async def init_db():
    """初始化数据库连接"""
    try:
        await db.init_db()
        utils.logger.info("Database connection initialized successfully")
    except Exception as e:
        utils.logger.error(f"Failed to initialize database connection: {e}")
        raise


def parse_args():
    parser = argparse.ArgumentParser(description="A crawler for media platforms")
    parser.add_argument("--platform", type=str, required=True, help="Platform to crawl (xhs/dy/ks/bili/weibo/tieba/zhihu)")
    parser.add_argument("--lt", type=str, required=True, help="Login type (qrcode/phone/cookie)")
    parser.add_argument("--type", type=str, required=True, help="Crawler type (search/detail/creator/follow/test)")
    parser.add_argument("--user", type=str, help="User keyword to search and follow (only for follow type)")
    parser.add_argument("--sec-uid", type=str, help="User sec_uid to directly follow or test (only for follow/test type)")
    parser.add_argument("--keyword", type=str, help="Keyword for search (optional)")
    return parser.parse_args()


async def main():
    # 初始化数据库连接
    await init_db()
    utils.logger.info("Database connection initialized successfully")

    # 解析命令行参数
    args = parse_args()
    platform = args.platform
    login_type = args.lt
    crawler_type = args.type

    # 设置全局变量
    crawler_type_var.set(crawler_type)
    if hasattr(args, 'keyword') and args.keyword:
        source_keyword_var.set(args.keyword)

    # 创建爬虫实例
    crawler = None
    message_listener = None
    try:
        if platform == "xhs":
            crawler = XiaoHongShuCrawler()
        elif platform == "dy":
            crawler = DouYinCrawler()
            # 创建消息监听器
            message_listener = DouYinMessageListener()
        elif platform == "ks":
            crawler = KuaishouCrawler()
        elif platform == "bili":
            crawler = BilibiliCrawler()
        elif platform == "weibo":
            crawler = WeiboCrawler()
        elif platform == "tieba":
            crawler = TieBaCrawler()
        elif platform == "zhihu":
            crawler = ZhihuCrawler()
        else:
            utils.logger.error(f"Unsupported platform: {platform}")
            return

        # 启动爬虫
        await crawler.start()
        
        # 如果是抖音平台，启动消息监听
        if platform == "dy" and message_listener:
            # 创建消息监听任务
            message_task = asyncio.create_task(message_listener.start_listening(crawler.dy_client))
            
        if crawler_type == "follow" and isinstance(crawler, DouYinCrawler):
            if args.sec_uid:
                await crawler.follow_user_by_sec_uid(args.sec_uid)
            else:
                await crawler.search_and_follow_user(args.user)
        elif crawler_type == "test" and isinstance(crawler, DouYinCrawler):
            await crawler.test_search_user_by_sec_uid(args.sec_uid)
            
    except Exception as e:
        utils.logger.error(f"Crawler error: {str(e)}")
        traceback.print_exc()
    finally:
        # 关闭爬虫
        if crawler:
            try:
                await crawler.close()
            except Exception as e:
                utils.logger.error(f"Error closing crawler: {str(e)}")
                traceback.print_exc()


if __name__ == '__main__':
    try:
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        sys.exit()
