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
    return parser.parse_args()


async def main():
    args = parse_args()
    config.PLATFORM = args.platform
    config.LOGIN_TYPE = args.lt
    config.CRAWLER_TYPE = args.type

    # 初始化数据库连接
    await init_db()

    if args.type == "follow" and not (args.user or args.sec_uid):
        print("Error: either --user or --sec-uid parameter is required for follow type")
        return
        
    if args.type == "test" and not args.sec_uid:
        print("Error: --sec-uid parameter is required for test type")
        return

    crawler = None
    try:
        if config.PLATFORM == "xhs":
            crawler = XiaoHongShuCrawler()
        elif config.PLATFORM == "dy":
            crawler = DouYinCrawler()
        elif config.PLATFORM == "ks":
            crawler = KuaishouCrawler()
        elif config.PLATFORM == "bili":
            crawler = BilibiliCrawler()
        elif config.PLATFORM == "weibo":
            crawler = WeiboCrawler()
        elif config.PLATFORM == "tieba":
            crawler = TieBaCrawler()
        elif config.PLATFORM == "zhihu":
            crawler = ZhihuCrawler()
        else:
            print("Error: Invalid platform")
            return

        await crawler.start()
        
        if args.type == "follow" and isinstance(crawler, DouYinCrawler):
            if args.sec_uid:
                await crawler.follow_user_by_sec_uid(args.sec_uid)
            else:
                await crawler.search_and_follow_user(args.user)
        elif args.type == "test" and isinstance(crawler, DouYinCrawler):
            await crawler.test_search_user_by_sec_uid(args.sec_uid)
            
    except Exception as e:
        utils.logger.error(f"Crawler error: {e}")
        traceback.print_exc()
    finally:
        if crawler:
            await crawler.close()


if __name__ == '__main__':
    try:
        # asyncio.run(main())
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        sys.exit()
