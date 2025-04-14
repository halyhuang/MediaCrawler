# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# 基础配置
PLATFORM = "dy"
##  KEYWORDS = "香港优才，香港专才，香港移民，香港留学"  # 设置抖音搜索关键词
KEYWORDS = "在职研究生"  # 设置抖音搜索关键词 '深圳创业修行','深圳创业求带','深圳创业求搭子','创业修行','创业求带','深圳AI创业'
# 设置抖音搜索关键词 '在职研究生'
LOGIN_TYPE = "cookie"  # qrcode or phone or cookie
COOKIES = ""
# 登录超时时间设置（秒）
LOGIN_TIMEOUT = 300
# 具体值参见media_platform.xxx.field下的枚举值，暂时只支持小红书
SORT_TYPE = "popularity_descending"
# 具体值参见media_platform.xxx.field下的枚举值，暂时只支持抖音
PUBLISH_TIME_TYPE = 0
CRAWLER_TYPE = (
    "creator"  # 爬取类型，search(关键词搜索) | detail(帖子详情)| creator(创作者主页数据)
)
# 自定义User Agent（暂时仅对XHS有效）
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'

# 是否开启 IP 代理
ENABLE_IP_PROXY = True

# 未启用代理时的最大爬取间隔，单位秒（暂时仅对XHS有效）
CRAWLER_MAX_SLEEP_SEC = 2

# 代理IP池数量
IP_PROXY_POOL_COUNT = 1

# 代理IP提供商名称
IP_PROXY_PROVIDER_NAME = "kuaidaili"

# 设置为True不会打开浏览器（无头浏览器）
# 设置False会打开一个浏览器
# 小红书如果一直扫码登录不通过，打开浏览器手动过一下滑动验证码
# 抖音如果一直提示失败，打开浏览器看下是否扫码登录之后出现了手机号验证，如果出现了手动过一下再试。
HEADLESS = False  # 设置为False，方便查看登录状态

# 是否保存登录状态
SAVE_LOGIN_STATE = True

# 数据库配置
RELATION_DB_HOST = "localhost"
RELATION_DB_PORT = 3306
RELATION_DB_USER = "root"
RELATION_DB_PWD = "123456"
RELATION_DB_NAME = "media_crawler"
RELATION_DB_CHARSET = "utf8mb4"

# 数据保存类型选项配置,支持三种类型：csv、db、json, 最好保存到DB，有排重的功能。
SAVE_DATA_OPTION = "db"  # csv or db or json

# 用户浏览器缓存的浏览器文件配置
USER_DATA_DIR = "%s_user_data_dir"  # %s will be replaced by platform name

# 爬取开始页数 默认从第一页开始
START_PAGE = 1

# 爬取视频/帖子的数量控制
CRAWLER_MAX_NOTES_COUNT = 50  # 减少数量避免被限制

# 并发爬虫数量控制
MAX_CONCURRENCY_NUM = 1

# 是否开启爬图片模式, 默认不开启爬图片
ENABLE_GET_IMAGES = False

# 是否开启爬评论模式, 默认开启爬评论
ENABLE_GET_COMMENTS = True

# 爬取一级评论的数量控制(单视频/帖子)
CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 20

# 是否开启爬二级评论模式, 默认不开启爬二级评论
# 老版本项目使用了 db, 则需参考 schema/tables.sql line 287 增加表字段
ENABLE_GET_SUB_COMMENTS = False

# 已废弃⚠️⚠️⚠️指定小红书需要爬虫的笔记ID列表
# 已废弃⚠️⚠️⚠️ 指定笔记ID笔记列表会因为缺少xsec_token和xsec_source参数导致爬取失败
# XHS_SPECIFIED_ID_LIST = [
#     "66fad51c000000001b0224b8",
#     # ........................
# ]

# 指定小红书需要爬虫的笔记URL列表, 目前要携带xsec_token和xsec_source参数
XHS_SPECIFIED_NOTE_URL_LIST = [
    "https://www.xiaohongshu.com/explore/66fad51c000000001b0224b8?xsec_token=AB3rO-QopW5sgrJ41GwN01WCXh6yWPxjSoFI9D5JIMgKw=&xsec_source=pc_search"
    # ........................
]

# 指定抖音需要爬取的ID列表
DY_SPECIFIED_ID_LIST = [
    "3597200769165390"
    # ........................
]

# 指定快手平台需要爬取的ID列表
KS_SPECIFIED_ID_LIST = ["3xf8enb8dbj6uig", "3x6zz972bchmvqe"]

# 指定B站平台需要爬取的视频bvid列表
BILI_SPECIFIED_ID_LIST = [
    "BV1d54y1g7db",
    "BV1Sz4y1U77N",
    "BV14Q4y1n7jz",
    # ........................
]

# 指定微博平台需要爬取的帖子列表
WEIBO_SPECIFIED_ID_LIST = [
    "4982041758140155",
    # ........................
]

# 指定weibo创作者ID列表
WEIBO_CREATOR_ID_LIST = [
    "5533390220",
    # ........................
]

# 指定贴吧需要爬取的帖子列表
TIEBA_SPECIFIED_ID_LIST = []

# 指定贴吧名称列表，爬取该贴吧下的帖子
TIEBA_NAME_LIST = [
    # "盗墓笔记"
]

# 指定贴吧创作者URL列表
TIEBA_CREATOR_URL_LIST = [
    "https://tieba.baidu.com/home/main/?id=tb.1.7f139e2e.6CyEwxu3VJruH_-QqpCi6g&fr=frs",
    # ........................
]

# 指定小红书创作者ID列表
XHS_CREATOR_ID_LIST = [
    "67023470000000001d02286c",
"67fc7100000000000601f402",
"5c41e4cc0000000006035175",
"5f5cdf140000000001004be4",
"64f1dfca0000000005000deb",
"58eaf7a082ec396fa995eff9",
"5ea65249000000000100268e",
"6108b160000000000100bcfe",
"5dd5fc8d0000000001007299",
"5fbdc77d000000000100a440",
"5a695d0011be10644b8bdd3f",
"5a695d0011be10644b8bdd3f",
"5e19bc8b0000000001001b3b",
"5b8175896d8bc80001891199",
"5ba1a66a5b6f470001f54024",
"5b65cc0f4eacab686fe12a71",
"674cfdce000000001d02e759",
"5ffacf37000000000101e212",
"5b8354ecdaf0480001c9a991",
"5b1be1bf11be10742722b17f",
"5c9c114a0000000016011a3c",
"63e602240000000027029bfc",
"59b9fe246a6a691fe0458e75",
"5a893095e8ac2b10af595f05",
"5e739f2a000000000100bb70",
"629a0d59000000001b02b97e",
"5c927a7a0000000011031ae9",
"5a0f0bb011be106d3102e9ff",
"64108ab600000000140104c8",
"59e42ddb6eea8803b71527d0",
"59e42ddb6eea8803b71527d0",
"59c5441bb1da145f481e3aed",
"6355dbc0000000001802c4bf",
"57d7f87382ec391b49c10c24",
"5574364062a60c3ec16b0c3c",
"5fd87d4b0000000001007400",
"636275ca000000001f01b399",
"5a6eb0f54eacab23511a1347",
"59dff4b46eea885d47dd1987",
"552fccb32e1d934198eaaea0",
"56584ca19eb57870abe2bdb1",
"5f7dbf15000000000101ebff",
"5f67f0730000000001000302",
"554258b9b203d957eebfefd1",
"6041c1e80000000001001fe5",
"5a6708b511be1065cc98e9d4",
"5759686050c4b468de137330",
"5e5a4db5000000000100a8e0",
"5ed5c438000000000101ffe2",
"671ca501000000001d020779",
"5b00bfcf11be107571b85ca2",
"5909ae1282ec3958aa60d4be",
"64a3df4d000000002b009393",
"64d3882e000000001001d884",
"5e044757000000000100be5c",
"60c4a4160000000001007c7a",
"5818280b82ec393b7bb6a6d0",
"5f8edd530000000001001d38",
"5dcce72a0000000001000d8f",
"5c3aa9bc00000000060275ce",
"5e856a3c000000000100b892",
"5a8932b74eacab1330475c1e",
"63d63af7000000002702a8c8",
"5fb498b90000000001001f60",
"5b5e923611be101a521b7536",
"5c8a01e3000000001200e078",
"64804fdd0000000012037790",
"67397938000000001c019b37",
"5efdaddd000000000101d40e",
"5efdaddd000000000101d40e",
"66456d5600000000070049d1",
"67e6510d00000000100269eb",
"5f151eae0000000001007a23",
"5636bdf582718c23a155087a",
"6390a021000000001f01fee0",
"6390a021000000001f01fee0",
"624abcc400000000210275a5",
"5cfb8286000000001201a48a",
"5c6ab74c0000000010009542",
"618766a80000000010005883",
"5c530aa4000000001102288e",
"608cd6e00000000001001899",
"5c67744800000000100158a1",
"5d397f6e0000000011034b91",
"5db0fe880000000001009a3c",
"5e908f140000000001004fa7",
"557228323f0f3c5c48a5a7ed",
"5acda3964eacab2a20c50633",
"663c1bb1000000000700658d",
"5c848e3a000000001103fb84",
"5b11528411be101fc05fd450",
"572acedf6a6a696fccb6ceba",
"58f3e2326a6a690a320ba8ea",
"5c2835f9000000000600b047",
"565ff2a8b8ce1a7fc4622f00",
"647dd070000000001001e690",
"54c901182e1d930f1008d43b",
"5e5f10c50000000001009637",
"5925b66782ec3906a6151021",
"641c3fef00000000110237a3",
"610de5a6000000000100a905",
"616b915b000000000202291a",
"61b484dc000000001000eea3",
"61b484dc000000001000eea3",
"609257360000000001000a2e",
"631c032900000000230391e6",
"5bf0dca5c69a560001091a4c",
"59ed9dda11be105ddf707e94",
"5c57b6db000000001102662a",
"63ff6b38000000001001d7b6",
"5d383e1c000000001003dae5",
"5b3f7218e8ac2b6f21aed4ed",
"5e43898e0000000001003b53",
"66fa29fd000000001d030f70",
"5ca0c9780000000016020fcb",
"5cf66c42000000001002878b",
"6615428400000000030325d9",
"5e79e8aa0000000001005beb",
"5b5f32a64eacab7896f3fc54",
"67e37534000000000e01e615",
"60f7a6f60000000001006c13",
"5d365767000000001003eb0b",
"63de667500000000260107c7",
"63d6c5460000000028019dcd",
"5c5c2838000000001802d6f8",
"5cfc77aa000000000603f1e8",
"5f5b3b240000000001003e50",
"5f37807b000000000100aef0",
"5b1bf3f94eacab09f60c70d3",
"5d1ddf9000000000110385eb",
"6243148f000000001000ed8d",
"64266b7c000000000801ba4f",
"653289fc000000002a01b28f",
"5fbf926a0000000001006e41",
"643f6e420000000029013c9f",
"5c81f09c000000001601e375",
"673415d2000000001c01a8bc",
"5937dc7d5e87e779ddc137c0",
"5a3517cee8ac2b1eff800f34",
"5b3d9edd6b58b76883959974",
"6103cd8f000000000101e590",
"5defaa850000000001003198",
"572e10716a6a695ddcdea2a9",
"5f7442cb0000000001005e1a",
"6321933100000000190208d4",
"592b60ed50c4b461c55a711f",
"5e9b2d5600000000010070d8",
"67f4bfc7000000000e02f2e3",
"5c28dc4900000000050343bd",
"603cff4200000000010056b3",
"5fbf83b90000000001006172",
"5fa0e5d30000000001001a13",
"5bce68b44dedcc000175b64e",
"5a8a6ed54eacab2bd6cab12c",
"609aa13d000000000100af16",
"601d531e000000000101c3fe",
"66731bad00000000070071c8",
"668a0307000000000f0353ff",
"5af4fd14e8ac2b2f5d77784d",
"6766824f0000000018017ef0",
"5f66002b000000000101e652",
"67dfb080000000000a03f8db",
"67dfb080000000000a03f8db",
"5dc3674b000000000100215b",
"66b47feb000000001d0314e7",
"623667ee0000000002019451",
"58aff7a56a6a691813cbc52a",
"5acf04e14eacab4636e01993",
"5bc74b0cf89a9279fb12c215",
"5f27e120000000000100a406",
"5b1633ce6b58b725bfdadec2",
"614b6d010000000002025de6",
"5b5964ca11be10247f51624c",
"5f48bd4200000000010051fc",
"5c8d21fd000000001603edbe",
"64ae2c5b000000001f00406a",
"5f79e51f0000000001004882",
"63b845d10000000027028b0b",
"5d0396b1000000001003ba29",
"6235e9a5000000001000b364",
"602f2bd0000000000101d35b",
"6791c30b000000000a03f217",
"67f4bfc7000000000e02f2e3",
"5aebae0e11be1063c2202cb9",
"6130cc830000000002020d0b",
"598d4ff9db2e605db88d25ad",
"54d8b7b7b4c4d6136c8a7516",
"5b6e5b46a914fd0001e7fd22",
"66f2554a000000001d020ac0",
"5c395dea000000000703e089",
"5eaa8d5e0000000001003261",
"5e46945a00000000010095c9",
"5c71351d00000000110319b5",
"5a59f8ee4eacab72701f8981"
    # ........................
]

# 指定Dy创作者ID列表(sec_id)
DY_CREATOR_ID_LIST = [
    "MS4wLjABAAAATJPY7LAlaa5X-c8uNdWkvz0jUGgpw4eeXIwu_8BhvqE",
    # ........................
]

# 指定bili创作者ID列表(sec_id)
BILI_CREATOR_ID_LIST = [
    "20813884",
    # ........................
]

# 指定快手创作者ID列表
KS_CREATOR_ID_LIST = [
    "3x4sm73aye7jq7i",
    # ........................
]


# 指定知乎创作者主页url列表
ZHIHU_CREATOR_URL_LIST = [
    "https://www.zhihu.com/people/yd1234567",
    # ........................
]

# 指定知乎需要爬取的帖子ID列表
ZHIHU_SPECIFIED_ID_LIST = [
    "https://www.zhihu.com/question/826896610/answer/4885821440", # 回答
    "https://zhuanlan.zhihu.com/p/673461588", # 文章
    "https://www.zhihu.com/zvideo/1539542068422144000" # 视频
]

# 词云相关
# 是否开启生成评论词云图
ENABLE_GET_WORDCLOUD = False
# 自定义词语及其分组
# 添加规则：xx:yy 其中xx为自定义添加的词组，yy为将xx该词组分到的组名。
CUSTOM_WORDS = {
    "零几": "年份",  # 将"零几"识别为一个整体
    "高频词": "专业术语",  # 示例自定义词
}

# 停用(禁用)词文件路径
STOP_WORDS_FILE = "./docs/hit_stopwords.txt"

# 中文字体文件路径
FONT_PATH = "./docs/STZHONGS.TTF"

# 爬取开始的天数，仅支持 bilibili 关键字搜索，YYYY-MM-DD 格式，若为 None 则表示不设置时间范围，按照默认关键字最多返回 1000 条视频的结果处理
START_DAY = '2024-01-01'

# 爬取结束的天数，仅支持 bilibili 关键字搜索，YYYY-MM-DD 格式，若为 None 则表示不设置时间范围，按照默认关键字最多返回 1000 条视频的结果处理
END_DAY = '2024-01-01'

# 是否开启按每一天进行爬取的选项，仅支持 bilibili 关键字搜索
# 若为 False，则忽略 START_DAY 与 END_DAY 设置的值
# 若为 True，则按照 START_DAY 至 END_DAY 按照每一天进行筛选，这样能够突破 1000 条视频的限制，最大程度爬取该关键词下的所有视频
ALL_DAY = False

# 关注功能相关配置
# 关注操作前的随机延迟范围(秒)
FOLLOW_DELAY_MIN = 2
FOLLOW_DELAY_MAX = 5

# 关注操作失败后的重试次数
FOLLOW_MAX_RETRIES = 3

# 关注操作失败后的重试延迟(秒)
FOLLOW_RETRY_DELAY = 10

# 是否在关注前先搜索用户
FOLLOW_WITH_SEARCH = True

# 是否在关注前模拟浏览用户主页
FOLLOW_WITH_PROFILE_VISIT = True

# 是否在关注前模拟鼠标移动
FOLLOW_WITH_MOUSE_MOVE = True

# 关注操作的超时时间(秒)
FOLLOW_TIMEOUT = 30