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
import signal
from typing import Dict, List

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


# 全局变量存储爬虫实例
crawlers = []

async def cleanup():
    """
    清理资源
    """
    try:
        # 关闭所有爬虫实例
        for crawler in crawlers:
            try:
                await crawler.close()
                utils.logger.info("爬虫已关闭")
            except Exception as e:
                utils.logger.error(f"关闭爬虫时发生错误: {str(e)}")
        
        # 关闭缓存
        try:
            from cache.local_cache import ExpiringLocalCache
            cache = ExpiringLocalCache()
            await cache.close()
            utils.logger.info("缓存已关闭")
        except Exception as e:
            utils.logger.error(f"关闭缓存时发生错误: {str(e)}")
            
        # 关闭数据库连接
        try:
            await db.close()
            utils.logger.info("数据库连接已关闭")
        except Exception as e:
            utils.logger.error(f"关闭数据库连接时发生错误: {str(e)}")
            
    except Exception as e:
        utils.logger.error(f"清理资源时发生错误: {str(e)}")

def signal_handler(signum, frame):
    """
    信号处理函数
    """
    utils.logger.info("\nReceived signal to terminate. Cleaning up...")
    asyncio.create_task(cleanup())
    sys.exit(0)

async def main():
    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 初始化日志
    utils.init_loging_config()

    # 解析命令行参数
    args = parse_args()
    platform = args.platform
    login_type = args.lt
    crawler_type = args.type

    # 设置全局变量
    crawler_type_var.set(crawler_type)
    if hasattr(args, 'keyword') and args.keyword:
        source_keyword_var.set(args.keyword)

    try:
        # 初始化数据库连接
        await init_db()
        utils.logger.info("Database connection initialized successfully")

        # 设置全局配置
        config.PLATFORM = platform
        config.LOGIN_TYPE = login_type
        config.CRAWLER_TYPE = crawler_type
        if args.keyword:
            config.KEYWORDS = args.keyword
            
        utils.logger.info(f"配置已更新 - 平台: {config.PLATFORM}, 登录类型: {config.LOGIN_TYPE}, 爬虫类型: {config.CRAWLER_TYPE}, 关键词: {config.KEYWORDS}")

        # 创建并启动爬虫
        if platform == 'xhs':
            crawler = XiaoHongShuCrawler()
            await crawler._init_browser()  # 显式调用异步初始化方法
            crawlers.append(crawler)
            await crawler.start()
        elif platform == 'douyin':
            crawler = DouYinCrawler()
            crawlers.append(crawler)
            # 添加抖音相关的处理逻辑
        else:
            utils.logger.error(f"不支持的平台: {platform}")
            return

    except Exception as e:
        utils.logger.error(f"主程序执行出错: {str(e)}")
    finally:
        # 清理资源
        await cleanup()


if __name__ == '__main__':
    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 运行主程序
        loop.run_until_complete(main())
        
    except KeyboardInterrupt:
        utils.logger.info("程序被用户中断")
    except Exception as e:
        utils.logger.error(f"程序执行出错: {str(e)}")
    finally:
        # 关闭事件循环
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            loop.close()
