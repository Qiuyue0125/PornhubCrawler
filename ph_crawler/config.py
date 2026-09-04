import os
import sys
import json
from urllib.request import getproxies


# ==================== 默认配置模板 ====================
DEFAULT_CONFIG_TEMPLATE = {
    # 界面模式：0 只显示文件序号和大小，1 显示完整文件管理功能
    "_UI_MODE": 1,
    "download": {
        "DEFAULT_MAX_GLOBAL_RETRIES": 3,
        "DEFAULT_MAX_WORKERS": 20,
        "DEFAULT_BATCH_INTERVAL": 10,
        "DEFAULT_MAX_RETRIES": 5,
        "DEFAULT_TS_TIMEOUT_CONNECT": 15,
        "DEFAULT_TS_TIMEOUT_READ": 60,
        "DEFAULT_CHUNK_SIZE": 2097152,
        "DEFAULT_DOWNLOAD_TIMEOUT": 20,
        "DEFAULT_M3U8_MAX_RETRIES": 7,
        "DEFAULT_M3U8_TIMEOUT": 30,
        "DEFAULT_M3U8_RETRY_DELAY": 3,
        "DEFAULT_DOWNLOAD_PAGE": 1,
        "DEFAULT_JUMP_PAGE": 0,
        "DEFAULT_VIDEO_MAX_RETRIES": 5,
        "DEFAULT_VIDEO_TIMEOUT": 20,
        "DEFAULT_VIDEO_RETRY_DELAY": 3
    },
    "paths": {
        "OUTPUT_DIR_ABSOLUTE": os.path.join(os.path.expanduser("~"), "Desktop", "VideoDownloader_Output")  # 默认输出到桌面
    },
    "urls": {
        "BATCH_VIDEO_LINKS": [],
        "DEFAULT_SINGLE_VIDEO_URL": "",
        "LAST_BATCH_URL": ""
    }
}


# ==================== 配置文件读取逻辑 ====================
def get_config_file_path():
    """
    获取配置文件路径（兼容开发环境和打包后环境）
    打包后：从Bin目录读取
    开发环境：从项目根目录读取
    """
    config_filename = "config.json"

    # 优先检查打包后的路径
    if hasattr(sys, '_MEIPASS'):
        # 打包后：sys._MEIPASS 是临时解压目录
        config_path = os.path.join(sys._MEIPASS, "Bin", config_filename)
        if os.path.exists(config_path):
            return config_path

    # 开发环境：从当前文件的上级目录查找
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))
    dev_config_path = os.path.join(project_root, config_filename)
    if os.path.exists(dev_config_path):
        return dev_config_path

    # 最后尝试当前目录
    current_config_path = os.path.join(current_dir, config_filename)
    if os.path.exists(current_config_path):
        return current_config_path

    raise FileNotFoundError(f"配置文件 {config_filename} 未找到！请检查文件是否存在")


def load_config():
    """
    加载配置文件，若文件不存在或解析失败则使用默认配置
    返回完整的配置字典
    """
    try:
        config_path = get_config_file_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, RuntimeError):
        # 使用默认配置模板
        return DEFAULT_CONFIG_TEMPLATE.copy()


# 加载配置文件
try:
    CONFIG_FILE_PATH = get_config_file_path()
    CONFIG = load_config()  # 使用新的加载函数
except Exception as e:
    # 加载失败时直接使用默认配置
    CONFIG = DEFAULT_CONFIG_TEMPLATE.copy()
    raise RuntimeError(f"加载配置文件失败，已使用默认配置: {str(e)}")


# ==================== 工具函数 ====================
def get_adapted_bin_path(filename):
    """获取Bin目录文件路径（兼容打包后）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, "Bin", filename)
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Bin", filename)


def get_resource_path(relative_path):
    """获取资源路径（兼容打包后）"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ==================== 从配置文件加载常量 ====================
# 下载相关配置
DEFAULT_MAX_GLOBAL_RETRIES = CONFIG['download']['DEFAULT_MAX_GLOBAL_RETRIES']
DEFAULT_MAX_WORKERS = CONFIG['download']['DEFAULT_MAX_WORKERS']
DEFAULT_BATCH_INTERVAL = CONFIG['download']['DEFAULT_BATCH_INTERVAL']
DEFAULT_MAX_RETRIES = CONFIG['download']['DEFAULT_MAX_RETRIES']
DEFAULT_TS_TIMEOUT = (
    CONFIG['download']['DEFAULT_TS_TIMEOUT_CONNECT'],
    CONFIG['download']['DEFAULT_TS_TIMEOUT_READ']
)
DEFAULT_CHUNK_SIZE = CONFIG['download']['DEFAULT_CHUNK_SIZE']
DEFAULT_DOWNLOAD_TIMEOUT = CONFIG['download']['DEFAULT_DOWNLOAD_TIMEOUT']
DEFAULT_M3U8_MAX_RETRIES = CONFIG['download']['DEFAULT_M3U8_MAX_RETRIES']
DEFAULT_M3U8_TIMEOUT = CONFIG['download']['DEFAULT_M3U8_TIMEOUT']
DEFAULT_M3U8_RETRY_DELAY = CONFIG['download']['DEFAULT_M3U8_RETRY_DELAY']
DEFAULT_DOWNLOAD_PAGE = CONFIG['download']['DEFAULT_DOWNLOAD_PAGE']
DEFAULT_JUMP_PAGE = CONFIG['download']['DEFAULT_JUMP_PAGE']
DEFAULT_VIDEO_MAX_RETRIES = CONFIG['download']['DEFAULT_VIDEO_MAX_RETRIES']
DEFAULT_VIDEO_TIMEOUT = CONFIG['download']['DEFAULT_VIDEO_TIMEOUT']
DEFAULT_VIDEO_RETRY_DELAY = CONFIG['download']['DEFAULT_VIDEO_RETRY_DELAY']

# 路径相关配置
CURRENT_DIR = os.getcwd()
CONFIG_DIR = os.path.dirname(CONFIG_FILE_PATH) if 'CONFIG_FILE_PATH' in locals() else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_DIR = os.path.join(CONFIG_DIR, "build_dir")  #始终与配置文件同级
OUTPUT_DIR = CONFIG['paths']['OUTPUT_DIR_ABSOLUTE']  #绝对路径

FFMPEG_RELATIVE_PATH = get_adapted_bin_path("ffmpeg.exe")
CHROME_DRIVER_RELATIVE_PATH = get_adapted_bin_path("chromedriver.exe")
CHROME_BINARY_RELATIVE_PATH = get_adapted_bin_path("chrome.exe")

BATCH_FAILED_LOG_PATH = os.path.join(CONFIG_DIR, "batch_failed_links.txt")
# ===========================================================
# 链接相关配置
BATCH_VIDEO_LINKS = CONFIG['urls'].get('BATCH_VIDEO_LINKS', [])
DEFAULT_SINGLE_VIDEO_URL = CONFIG['urls'].get('DEFAULT_SINGLE_VIDEO_URL', "")
LAST_BATCH_URL = CONFIG['urls'].get('LAST_BATCH_URL', "")
DEFAULT_BATCH_VIDEO_URL = LAST_BATCH_URL

# 界面模式由配置文件控制，不再通过点击界面切换。
# _UI_MODE=1 显示完整界面，_UI_MODE=0 显示简化界面。
# 兼容旧版本的 SMD 配置，但新配置优先使用隐藏字段 _UI_MODE。
ui_mode = CONFIG.get("_UI_MODE")
if ui_mode is None and "SMD" in CONFIG:
    ui_mode = 1 if str(CONFIG.get("SMD")) == "1416179884" else 0
try:
    ui_mode = int(ui_mode)
except (TypeError, ValueError):
    ui_mode = 1
SAFE_MODE = ui_mode != 1

# ==================== 全局变量初始化 ====================
# 代理配置
system_proxies = getproxies()
GAL_PROXIES = {
    "http": system_proxies.get("http", ""),
    "https": system_proxies.get("http", "")
}

# 动态配置
dynamic_config = {
    "max_retries": DEFAULT_MAX_RETRIES,
    "max_global_retries": DEFAULT_MAX_GLOBAL_RETRIES,
    "max_workers": DEFAULT_MAX_WORKERS,
    "batch_interval": DEFAULT_BATCH_INTERVAL,
    "download_timeout": DEFAULT_DOWNLOAD_TIMEOUT,
    "ts_timeout_connect": DEFAULT_TS_TIMEOUT[0],
    "ts_timeout_read": DEFAULT_TS_TIMEOUT[1],
    "chunk_size": DEFAULT_CHUNK_SIZE,
    "default_download_page": DEFAULT_DOWNLOAD_PAGE,
    "default_jump_page": DEFAULT_JUMP_PAGE,
    "m3u8_max_retries": DEFAULT_M3U8_MAX_RETRIES,
    "m3u8_timeout": DEFAULT_M3U8_TIMEOUT,
    "m3u8_retry_delay": DEFAULT_M3U8_RETRY_DELAY,
    "video_max_retries": DEFAULT_VIDEO_MAX_RETRIES,
    "video_timeout": DEFAULT_VIDEO_TIMEOUT,
    "video_retry_delay": DEFAULT_VIDEO_RETRY_DELAY
}
