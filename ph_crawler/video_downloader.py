import os
import re
import json
import time
import requests
import subprocess
import urllib3
import threading
import ast
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置导入
from config import (
    GAL_PROXIES, dynamic_config,
    get_resource_path, CHROME_DRIVER_RELATIVE_PATH,
    CHROME_BINARY_RELATIVE_PATH, FFMPEG_RELATIVE_PATH,
)

# 忽略SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class VideoDownloader:
    """
    视频下载核心类
    功能：解析视频页面、提取m3u8链接、下载TS分片、合并为MP4文件
    """

    def __init__(self, proxy=None, progress_callback=None):
        """
        初始化下载器
        :param proxy: 代理服务器地址（可选）
        :param progress_callback: 进度回调函数，格式：callback(text, progress, status_type)
        """
        # Chrome浏览器配置
        self.chrome_options = Options()
        self.progress_callback = progress_callback

        # Chrome无头模式配置
        self.chrome_options.add_argument("--headless=new")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1920x1080")
        self.chrome_options.add_argument("--window-position=-32000,-32000")
        self.chrome_options.add_argument("--start-minimized")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--no-first-run")
        self.chrome_options.add_argument("--no-default-browser-check")
        self.chrome_options.add_argument("--disable-background-mode")
        self.chrome_options.add_argument("--disable-breakpad")
        self.chrome_options.add_argument("--disable-crash-reporter")
        self.chrome_options.add_argument("--disable-notifications")
        self.chrome_options.add_argument("--disable-extensions")
        self.chrome_options.add_experimental_option(
            "prefs",
            {"profile.default_content_setting_values.popups": 2},
        )
        # ChromeDriver 默认追加 --enable-logging=stderr。窗口版 EXE 没有 stderr
        # 控制台，会导致每个 Chrome 子进程各自弹出黑色输出窗口。
        self.chrome_options.add_experimental_option(
            "excludeSwitches",
            ["enable-logging", "disable-popup-blocking"],
        )

        # 驱动和浏览器路径配置
        self.driver_path = get_resource_path(CHROME_DRIVER_RELATIVE_PATH)
        self.chrome_options.binary_location = get_resource_path(CHROME_BINARY_RELATIVE_PATH)

        # 代理配置
        if proxy:
            self.chrome_options.add_argument(f'--proxy-server={proxy}')

        # 窗口版 EXE 没有可继承的控制台，必须从创建阶段禁止 ChromeDriver
        # 分配控制台，否则批量下载时会反复闪出黑色窗口。
        service_kwargs = {}
        if os.name == "nt":
            service_kwargs["popen_kw"] = {
                "creation_flags": subprocess.CREATE_NO_WINDOW,
            }
        chrome_service = Service(self.driver_path, **service_kwargs)
        self.driver = webdriver.Chrome(
            service=chrome_service,
            options=self.chrome_options
        )

        # 下载控制变量
        self.stop_event = threading.Event()
        self.current_url = None
        self.total_segments = 0

        # 下载速度计算相关锁和变量
        self.lock = threading.Lock()
        self.download_start_time = None
        self.total_downloaded_bytes = 0
        self.speed_calculation_interval = 1
        self.last_speed_check_time = None
        self.last_downloaded_bytes = 0
        self.current_speed = 0.0
        self.speed_history = []  # 存储最近3次速度，稳定波动
        self.last_byte_update = time.time()  # 最后一次字节更新时间，检测卡顿

        # m3u8解析相关变量
        self.parsed_urls = set()  # 用于检测m3u8循环引用

    def wait_for_page_load(self, timeout=30):
        """
        等待页面完全加载
        :param timeout: 超时时间（秒）
        :return: 加载成功返回True，超时返回False
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            return True
        except:
            return False

    def find_player_scripts(self):
        """
        查找播放器相关的脚本标签
        优先查找播放器容器内的特定script，找不到则返回页面所有script
        :return: 脚本元素列表，失败返回空列表
        """
        try:
            # 优先查找播放器容器内的脚本
            player_div = self.driver.find_element(By.CSS_SELECTOR, 'div.original.mainPlayerDiv')
            target_scripts = player_div.find_elements(By.XPATH, './/script[@type="text/javascript"]')

            if target_scripts:
                return target_scripts

            print("未找到播放器容器内的script，返回页面所有script")
            all_scripts = self.driver.find_elements(By.XPATH, '//script')
            return all_scripts

        except Exception as e:
            print(f"查找播放器脚本时出错: {e}，返回页面所有script")
            try:
                all_scripts = self.driver.find_elements(By.XPATH, '//script')
                return all_scripts
            except Exception as e2:
                print(f"查找所有script也出错: {e2}")
                return []

    def handle_age_verification(self):
        """
        自动处理年龄验证页面
        :return: 成功点击验证按钮返回True，未找到返回False
        """
        try:
            # 年龄验证按钮选择器列表
            selectors = [
                "button[name='age_confirm']", "button.age-confirm", "input[name='age_confirm']",
                "a.age-confirm", "button[class*='age']", "a[class*='age']",
                "button:contains('Confirm')", "a:contains('Confirm')", "button:contains('继续')",
                "a:contains('继续')", "button:contains('进入')", "a:contains('进入')",
                "button:contains('我已满18岁')", "a:contains('我已满18岁')",
                "#age-verification button", ".age-gate button"
            ]

            # 遍历选择器查找并点击验证按钮
            for selector in selectors:
                try:
                    if ":contains" in selector:
                        # 处理包含文本的选择器
                        text = selector.split("'")[1] if "'" in selector else selector.split('"')[1]
                        elements = self.driver.find_elements(By.XPATH,
                                                             f"//button[contains(text(), '{text}')] | //a[contains(text(), '{text}')]")
                        for element in elements:
                            if element.is_displayed():
                                element.click()
                                print(f"点击了年龄确认按钮: {text}")
                                time.sleep(1)
                                return True
                    else:
                        # 处理普通CSS选择器
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            if element.is_displayed():
                                element.click()
                                print(f"点击了年龄确认按钮，选择器: {selector}")
                                time.sleep(2)
                                return True
                except:
                    continue

            # 备用XPath选择器
            xpaths = [
                "//button[contains(@class, 'btn') and contains(text(), 'Confirm')]",
                "//a[contains(@class, 'btn') and contains(text(), 'Confirm')]",
                "//button[contains(text(), 'Enter')]", "//a[contains(text(), 'Enter')]",
                "//button[contains(text(), 'I agree')]", "//button[contains(text(), '同意')]",
                "//button[contains(text(), '确认')]", "//button[contains(@onclick, 'age')]",
                "//a[contains(@onclick, 'age')]", "//input[@type='submit' and contains(@value, 'Confirm')]",
                "//input[@type='submit' and contains(@value, '确认')]"
            ]

            # 遍历XPath选择器
            for xpath in xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for element in elements:
                        if element.is_displayed():
                            element.click()
                            print(f"通过XPath点击了年龄确认按钮: {xpath}")
                            time.sleep(2)
                            return True
                except:
                    continue

            print("未找到年龄确认按钮，可能不需要验证或页面结构不同")
            return False
        except Exception as e:
            print(f"处理年龄验证时出错: {e}")
            return False

    def clean_js_for_json(self, js_str):
        """
        纯内置模块清理JS字符串为合法JSON格式
        :param js_str: 原始JS对象字符串
        :return: 清理后的JSON字符串
        """
        # 移除单行注释
        clean_str = re.sub(r'//.*?$', '', js_str, flags=re.MULTILINE)
        # 移除多行注释
        clean_str = re.sub(r'/\*[\s\S]*?\*/', '', clean_str)
        # 移除末尾逗号
        clean_str = re.sub(r',\s*([}\]])', r'\1', clean_str)
        # 转换布尔值和空值
        clean_str = clean_str.replace("true", "True").replace("false", "False")
        clean_str = clean_str.replace("undefined", "None")
        clean_str = clean_str.replace("NaN", "0").replace("Infinity", "0")
        # 添加属性引号
        clean_str = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', clean_str)
        # 移除函数定义
        clean_str = re.sub(r'\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*function\s*\([^)]*\)\s*{[\s\S]*?}', '', clean_str)
        # 压缩空格
        clean_str = re.sub(r'\s+', ' ', clean_str).strip()

        return clean_str

    def extract_video_urls_directly(self, raw_fragment):
        """
        直接从原始片段中提取所有videoUrl和对应的画质，不依赖完整解析
        :param raw_fragment: 原始mediaDefinitions片段
        :return: 包含videoUrl和quality的字典列表
        """
        video_info_list = []

        # 模式1：匹配完整的视频对象
        video_obj_pattern = r'\{"group":\d+,"height":\d+,"width":\d+,[^}]*?"videoUrl":"([^"]+)"[^}]*?"quality":"([^"]+)"[^}]*?\}'
        video_matches = re.findall(video_obj_pattern, raw_fragment, re.DOTALL)

        if video_matches:
            for video_url, quality in video_matches:
                quality = f"{quality}P" if not quality.endswith('P') else quality
                video_info_list.append({
                    "videoUrl": video_url.replace("\\/", "/"),
                    "quality": quality,
                    "height": re.search(r'"height":(\d+)', raw_fragment).group(1) if re.search(r'"height":(\d+)',
                                                                                               raw_fragment) else "unknown"
                })
            return video_info_list

        # 模式2：直接匹配videoUrl
        url_pattern = r'"videoUrl"\s*:\s*["\']([^"\']+master\.m3u8[^"\']*)["\']'
        url_matches = re.findall(url_pattern, raw_fragment, re.IGNORECASE)

        # 匹配height
        height_pattern = r'"height":(\d+)'
        height_matches = re.findall(height_pattern, raw_fragment)

        # 画质映射表
        height_to_quality = {
            "2160": "2160P", "1440": "1440P", "1080": "1080P",
            "720": "720P", "480": "480P", "240": "240P", "180": "180P"
        }

        # 构建视频信息列表
        for idx, video_url in enumerate(url_matches):
            height = height_matches[idx] if idx < len(height_matches) else "unknown"
            quality = height_to_quality.get(height, f"{height}P" if height.isdigit() else "unknown")

            video_info_list.append({
                "videoUrl": video_url.replace("\\/", "/"),
                "quality": quality,
                "height": height
            })

        return video_info_list

    def extract_video_info(self, url, wait_time=5):
        """
        解析视频页面，提取最高画质m3u8链接和视频名称
        :param url: 视频页面URL
        :param wait_time: 脚本加载等待时间（秒）
        :return: 元组 (m3u8链接, 视频名称)，失败返回 (None, 视频名称/兜底名称)
        """
        # 获取配置参数
        max_retries = dynamic_config.get("video_max_retries", 5)
        retry_delay = dynamic_config.get("video_timeout", 3)
        max_timeout = dynamic_config.get("video_retry_delay", 30)

        # 初始化视频名称变量
        merge_output_name = ""

        # 重试循环
        for retry_count in range(max_retries):
            try:
                self.current_url = url
                print(f"【第 {retry_count + 1}/{max_retries} 次尝试】正在访问: {url}")
                self.driver.get(url)

                # 处理年龄验证
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH,
                             "//*[contains(text(), 'Age') or contains(@id, 'age') or contains(@class, 'age-verification')]")
                        )
                    )
                    self.handle_age_verification()
                except:
                    pass

                # 等待页面加载
                if not self.wait_for_page_load(timeout=max_timeout):
                    raise TimeoutError("页面加载超时")

                # 等待脚本加载
                try:
                    WebDriverWait(self.driver, max_timeout).until(
                        EC.presence_of_element_located((By.XPATH, "//script"))
                    )
                except:
                    raise RuntimeError("页面脚本加载超时")

                # 查找播放器脚本
                scripts = self.find_player_scripts()
                if not scripts:
                    raise RuntimeError("未找到目标script标签")

                # 读取脚本内容
                script_contents = []
                for script in scripts:
                    src = script.get_attribute("src")
                    if src:
                        try:
                            response = requests.get(
                                src,
                                timeout=(5, max_timeout),
                                verify=False,
                                proxies=self.GAL_PROXIES if hasattr(self, 'GAL_PROXIES') else {}
                            )
                            content = response.text if response.status_code == 200 else ""
                        except Exception as e:
                            content = ""
                    else:
                        content = script.get_attribute("innerHTML") or ""

                    if content:
                        script_contents.append(content)

                if not script_contents:
                    raise RuntimeError("脚本内容为空")

                # 提取视频名称
                merge_output_name = ""
                meta_tags = self.driver.find_elements(By.XPATH, '//meta[@property="og:title"]')
                og_titles = [tag.get_attribute("content") for tag in meta_tags if tag.get_attribute("content")]
                if len(og_titles) == 1:
                    merge_output_name = str(og_titles[0])
                    print(f"从og:title找到视频名称: {merge_output_name}")
                else:
                    try:
                        title_tag = self.driver.find_element(By.XPATH, '//head/title')
                        title_text = title_tag.get_attribute("textContent") or title_tag.text
                        if title_text:
                            merge_output_name = title_text.strip()
                            print(f"从title标签找到视频名称: {merge_output_name}")
                    except:
                        merge_output_name = time.strftime("StartAt_%Y%m%d_%H.%M.%S")
                        print(f"未找到og:title和title标签，使用默认名称: {merge_output_name}")

                # 提取mediaDefinitions片段
                media_pattern = r'"mediaDefinitions"\s*:\s*\[([\s\S]*)\](?=\s*[,;}\]])'
                all_media_fragments = []

                for idx, content in enumerate(script_contents):
                    matches = re.findall(media_pattern, content, re.DOTALL)
                    if matches:
                        print(f"在第 {idx + 1} 个脚本中找到 {len(matches)} 个 mediaDefinitions 片段")
                        all_media_fragments.extend(matches)

                if not all_media_fragments:
                    raise RuntimeError("全局未找到 mediaDefinitions 字段")

                # 处理第一个media片段
                target_fragment = all_media_fragments[0].strip()
                media_definitions = None

                # 直接提取视频链接
                media_definitions = self.extract_video_urls_directly(target_fragment)
                if media_definitions and len(media_definitions) > 0:
                    print(f"直接提取到 {len(media_definitions)} 个视频链接")
                else:
                    # 尝试JSON解析
                    try:
                        clean_fragment = self.clean_js_for_json(target_fragment)
                        media_json = f"[{clean_fragment}]"
                        media_definitions = json.loads(media_json)
                    except json.JSONDecodeError:
                        # 尝试AST解析
                        try:
                            clean_fragment = self.clean_js_for_json(target_fragment)
                            media_str = f"[{clean_fragment}]"
                            media_definitions = ast.literal_eval(media_str)
                        except Exception as e2:
                            raise RuntimeError(f"所有解析方案均失败！\n原始片段前500字符: {target_fragment[:500]}...")

                if not media_definitions or len(media_definitions) == 0:
                    raise RuntimeError("未提取到任何视频链接")

                # 选择最高画质
                quality_priority = ["2160P", "1440P", "1080P", "720P", "480P", "240P", "180P", "unknown"]
                highest_quality_m3u8 = None
                highest_quality_name = None

                for quality in quality_priority:
                    for video in media_definitions:
                        video_url = video.get("videoUrl", "")
                        video_quality = video.get("quality", "").upper()
                        if video_url and (quality in video_quality or
                                          (quality.replace("P", "") in video_quality and video_quality.isdigit())):
                            highest_quality_m3u8 = video_url
                            highest_quality_name = quality
                            break
                    if highest_quality_m3u8:
                        break

                # 兜底：查找包含master.m3u8的链接
                if not highest_quality_m3u8:
                    for video in media_definitions:
                        video_url = video.get("videoUrl", "")
                        if video_url and "master.m3u8" in video_url:
                            highest_quality_m3u8 = video_url
                            highest_quality_name = "未知画质"
                            break
                    if not highest_quality_m3u8:
                        raise RuntimeError("未找到任何m3u8链接")

                # 清理URL
                highest_quality_m3u8 = highest_quality_m3u8.replace("\\/", "/")

                if "exp=" in highest_quality_m3u8:
                    exp_match = re.search(r'exp=(\d+)', highest_quality_m3u8)
                    if exp_match:
                        exp_time = int(exp_match.group(1))
                        current_time = int(time.time())
                        if exp_time - current_time < 60:
                            print(f"m3u8链接即将过期（剩余{exp_time - current_time}秒），重新提取...")
                            self.driver.refresh()
                            time.sleep(2)
                            continue  # 重新进入重试循环

                # 进度回调
                if self.progress_callback:
                    self.progress_callback(f"最高画质为{highest_quality_name},正在分析数据", 0, "info")

                print(f"【第 {retry_count + 1} 次尝试成功】提取到最高画质m3u8: {highest_quality_m3u8}")
                return highest_quality_m3u8, merge_output_name

            except Exception as e:
                # 最后一次重试失败
                if retry_count >= max_retries - 1:
                    error_msg = f"解析视频信息失败（已重试{max_retries}次）: {str(e)}"
                    print(error_msg)
                    if self.progress_callback:
                        self.progress_callback(error_msg, 0, "error")
                    return None, merge_output_name if merge_output_name else time.strftime(
                        "StartAt_%Y%m%d_%H.%M.%S")

                # 重试提示
                error_msg = f"【第 {retry_count + 1} 次尝试失败】{str(e)}，{retry_delay}秒后重试..."
                print(error_msg)
                if self.progress_callback:
                    self.progress_callback(error_msg, 0, "warning")
                time.sleep(retry_delay)
                try:
                    self.driver.refresh()
                except:
                    pass

    def recursive_parse_m3u8(self, url):
        """
        递归解析m3u8文件（强化重试和状态处理，解决偶发性解析失败）
        :param url: m3u8文件URL
        :return: 元组 (TS链接列表, 解析结果信息)，失败返回 (None, 错误信息)
        """
        # 检测循环引用
        if url in self.parsed_urls:
            return None, "检测到m3u8循环引用"
        self.parsed_urls.add(url)

        # 获取配置参数
        max_retries = dynamic_config["m3u8_max_retries"]
        timeout = dynamic_config["m3u8_timeout"]
        retry_delay = dynamic_config["m3u8_retry_delay"]

        last_error_msg = ""

        try:
            # 刷新当前视频页面，确保Cookie是最新的
            if self.current_url and hasattr(self, 'driver'):
                self.driver.get(self.current_url)
                time.sleep(1)  # 给Cookie加载时间
        except Exception as e:
            print(f"刷新Cookie时警告: {str(e)}")
            pass

        # 重试循环（优化重试策略）
        for retry_count in range(max_retries):
            try:
                cookies = self.driver.get_cookies()
                cookie_dict = {c['name']: c['value'] for c in cookies}

                # 构建请求头（增加缓存控制，避免拿到过期内容）
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Referer': self.current_url,
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-site',
                    'Cache-Control': 'no-cache',  # 关键：禁用缓存
                    'Pragma': 'no-cache'
                }

                if retry_count > 0:
                    random_sleep = 0.5 + retry_count * 0.2  # 递增随机延迟
                    time.sleep(random_sleep)

                # 请求m3u8文件（优化超时处理）
                response = requests.get(
                    url,
                    headers=headers,
                    cookies=cookie_dict,
                    proxies=GAL_PROXIES,
                    timeout=(timeout, timeout * 2),  # 读写超时分开
                    verify=False,
                    stream=False,
                    allow_redirects=True  # 关键：允许重定向
                )
                response.raise_for_status()
                m3u8_content = response.content.decode('utf-8', errors='ignore').strip()
                print(f"解析m3u8（层级{len(self.parsed_urls)}，重试{retry_count}）: {url[:80]}...")

                # 解析m3u8内容
                lines = m3u8_content.split('\n')

                # 计算基础URL（保留你的逻辑）
                if '?' in url:
                    base_url = url.rsplit('?', 1)[0].rsplit('/', 1)[0] + '/'
                else:
                    base_url = url.rsplit('/', 1)[0] + '/'

                ts_urls = []
                sub_m3u8_urls = []
                is_ts_playlist = False

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # 检测TS分片列表标记
                    if line.startswith('#EXTINF'):
                        is_ts_playlist = True

                    # 匹配TS分片
                    elif (('seg-' in line and '.ts' in line) or
                          (line.startswith('seg-') and ('?' in line))):
                        ts_url = line if line.startswith('http') else base_url + line
                        if ts_url and ts_url not in ts_urls:
                            ts_urls.append(ts_url)

                    elif '.m3u8' in line and not line.startswith('#'):
                        if 'iframes' in line:
                            continue
                        sub_m3u8 = line if line.startswith('http') else base_url + line
                        # 修复重定向后的URL拼接
                        sub_m3u8 = sub_m3u8.replace('//', '/').replace(':/', '://')  # 修复双斜杠问题
                        sub_m3u8_urls.append(sub_m3u8)

                # 找到TS分片直接返回
                if ts_urls:
                    return ts_urls, f"成功解析到 {len(ts_urls)} 个ts分片"

                # TS列表但未找到TS链接，尝试正则兜底
                if is_ts_playlist and not ts_urls:
                    ts_pattern = r'(seg-\d+-v1-a1\.ts\?[^"\n\r]+|seg-\d+\.ts\?[^"\n\r]+|\d+\.ts\?[^"\n\r]+)'
                    match_ts = re.findall(ts_pattern, m3u8_content)
                    if match_ts:
                        ts_urls_fix = []
                        for ts in match_ts:
                            ts_url = base_url + ts
                            ts_url = ts_url.replace('//', '/').replace(':/', '://')
                            ts_urls_fix.append(ts_url)
                        return ts_urls_fix, f"通过正则兜底解析到 {len(ts_urls_fix)} 个ts分片"
                    last_error_msg = f"是ts分片列表但未找到ts链接\n{m3u8_content[:500]}"

                if sub_m3u8_urls:
                    for sub_url in sub_m3u8_urls:
                        result, msg = self.recursive_parse_m3u8(sub_url)
                        if result:
                            return result, msg
                        last_error_msg = f"子m3u8 {sub_url[:50]} 解析失败: {msg}"

                # 未找到有效内容
                if not last_error_msg:
                    last_error_msg = f"未找到ts分片或有效子m3u8\n{m3u8_content[:300]}"

            except requests.exceptions.RequestException as e:
                last_error_msg = f"解析m3u8异常: {str(e)}"
                print(f"解析m3u8异常（重试{retry_count + 1}/{max_retries}）: {last_error_msg}")

            except Exception as e:
                last_error_msg = f"解析m3u8未知异常: {str(e)}"
                print(last_error_msg)
                return None, last_error_msg

            if retry_count < max_retries - 1 and last_error_msg:
                sleep_time = min(retry_delay * (2 ** retry_count) + random.random(), 10)
                print(f"等待{sleep_time:.1f}秒后进行第{retry_count + 2}次重试...")
                time.sleep(sleep_time)

        # 所有重试失败前的最后尝试：重新提取m3u8链接
        try:
            print("最后尝试：重新提取m3u8链接...")
            new_m3u8, _ = self.extract_video_info(self.current_url, wait_time=5)
            if new_m3u8 and new_m3u8 != url:
                self.parsed_urls = set()
                return self.recursive_parse_m3u8(new_m3u8)
        except Exception as e:
            print(f"最后尝试重新提取m3u8失败: {str(e)}")
            pass

        # 所有重试失败
        return None, f"m3u8解析失败（已重试{max_retries}次）: {last_error_msg}\nURL: {url}"

    def parse_m3u8(self, m3u8_url):
        """
        解析多级m3u8文件，提取TS分片链接（带重试机制）
        :param m3u8_url: m3u8文件URL
        :return: 元组 (TS链接列表, 解析结果信息)，失败返回 (None, 错误信息)
        """
        # 重置解析记录
        self.parsed_urls = set()

        # 调用递归解析方法
        result = self.recursive_parse_m3u8(m3u8_url)

        # 返回结果
        return (result[0], result[1]) if result[0] else (None, f"解析m3u8失败: {result[1]}")

    def calculate_download_speed(self, downloaded_bytes):
        """
        计算实时下载速度
        :param downloaded_bytes: 本次下载的字节数
        """
        current_time = time.time()

        with self.lock:
            # 更新总下载字节数
            if downloaded_bytes > 0:
                self.total_downloaded_bytes += downloaded_bytes
                self.last_byte_update = current_time

            # 初始化计时
            if self.download_start_time is None:
                self.download_start_time = current_time
                self.last_speed_check_time = current_time
                self.last_downloaded_bytes = self.total_downloaded_bytes
                self.last_byte_update = current_time
                self.speed_history = []  # 初始化速度历史
                return

            # 达到计算间隔，更新速度
            if current_time - self.last_speed_check_time >= self.speed_calculation_interval:
                time_diff = current_time - self.last_speed_check_time
                bytes_diff = self.total_downloaded_bytes - self.last_downloaded_bytes

                # 计算瞬时速度 + 3次滑动平均
                instant_speed = (bytes_diff / (1024 * 1024)) / time_diff if time_diff > 0 else 0.0
                self.speed_history.append(instant_speed)
                if len(self.speed_history) > 3:  # 仅保留最近3次，减少波动
                    self.speed_history.pop(0)
                self.current_speed = sum(self.speed_history) / len(self.speed_history) if self.speed_history else 0.0

                # 8秒无更新则速度置0（检测卡顿）
                if current_time - self.last_byte_update > 8:
                    self.current_speed = 0.0

                # 更新检查时间和字节数
                self.last_speed_check_time = current_time
                self.last_downloaded_bytes = self.total_downloaded_bytes

    def download_ts_segment(self, url, output_dir, segment_num):
        """
        下载单个TS分片（带重试机制）
        :param url: 分片URL
        :param output_dir: 输出目录
        :param segment_num: 分片序号（用于命名）
        :return: 下载成功返回True，失败返回False
        """
        # 检查是否停止下载
        if self.stop_event.is_set():
            return False

        # 构建请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': self.current_url,
            'Accept': '*/*',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-site',
        }

        # 获取cookies
        cookies = self.driver.get_cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}

        # 初始化重试参数
        retry_count = 0
        max_retries = dynamic_config["max_retries"]
        ts_timeout = (dynamic_config["ts_timeout_connect"], dynamic_config["ts_timeout_read"])
        chunk_size = dynamic_config["chunk_size"]
        file_path = os.path.join(output_dir, f"seg-{segment_num}.ts")

        # 删除已存在的文件
        if os.path.exists(file_path):
            os.remove(file_path)

        # 重试循环
        while retry_count < max_retries and not self.stop_event.is_set():
            try:
                # 重试等待
                if retry_count > 0:
                    sleep_time = min(2 ** retry_count, 6)
                    print(f"分片 {segment_num} 下载失败，{sleep_time}秒后重试（{retry_count + 1}/{max_retries}）...")
                    time.sleep(sleep_time)

                # 下载分片
                response = requests.get(
                    url,
                    stream=True,
                    timeout=ts_timeout,
                    proxies=GAL_PROXIES,
                    headers=headers,
                    cookies=cookie_dict,
                    verify=False
                )

                # 检查状态码
                if response.status_code not in [200, 206]:
                    print(f"分片 {segment_num} 下载失败，状态码：{response.status_code}")
                    retry_count += 1
                    continue

                # 确保输出目录存在
                os.makedirs(output_dir, exist_ok=True)

                # 写入文件
                downloaded_bytes = 0
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if self.stop_event.is_set():
                            raise Exception("下载被中断")
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            self.calculate_download_speed(len(chunk))

                # 强制触发速度计算
                self.calculate_download_speed(0)

                # 检查文件大小
                file_size = os.path.getsize(file_path)
                if file_size > 0:
                    print(f"分片 {segment_num} 下载成功（大小：{file_size / 1024 / 1024:.2f}MB）")
                    return True
                else:
                    os.remove(file_path)
                    print(f"分片 {segment_num} 下载后文件为空")

            except requests.exceptions.RequestException as e:
                print(f"分片 {segment_num} 下载异常（重试{retry_count + 1}）: {str(e)}")
            except Exception as e:
                print(f"分片 {segment_num} 下载中断: {str(e)}")
                return False

            retry_count += 1

        # 所有重试失败
        print(f"分片 {segment_num} 下载失败（已重试{max_retries}次）")
        return False

    def download_all_ts_segments(self, ts_urls, output_dir):
        """
        批量下载所有TS分片（失败自动重试）
        :param ts_urls: TS分片URL列表
        :param output_dir: 输出目录
        :return: 元组 (是否全部成功, 结果消息)
        """
        # 检查停止状态或空列表
        if self.stop_event.is_set() or not ts_urls:
            return False, "无分片可下载"

        # 重置下载统计
        self.download_start_time = None
        self.total_downloaded_bytes = 0
        self.last_speed_check_time = None
        self.last_downloaded_bytes = 0
        self.current_speed = 0.0

        # 初始化变量
        total = len(ts_urls)
        max_global_retries = dynamic_config["max_global_retries"]
        global_retry_count = 0

        # 构建分片信息列表
        segment_info = [
            {"url": url, "seg_num": i + 1, "success": False}
            for i, url in enumerate(ts_urls)
        ]

        # 全局重试循环
        while global_retry_count < max_global_retries and not self.stop_event.is_set():
            # 筛选失败的分片
            failed_segments = [seg for seg in segment_info if not seg["success"]]
            if not failed_segments:
                break

            # 进度提示
            print(f"\n全局下载 {global_retry_count + 1}/{max_global_retries}：需要下载 {len(failed_segments)} 个分片")

            self.progress_callback(
                f"全局下载 {global_retry_count + 1}/{max_global_retries}：需要下载 {len(failed_segments)} 个分片",
                int((total - len(failed_segments)) / total * 100),
                "warning"
            )

            # 线程池下载
            max_workers = dynamic_config["max_workers"]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交任务
                futures = {
                    executor.submit(self.download_ts_segment, seg["url"], output_dir, seg["seg_num"]): seg
                    for seg in failed_segments
                }

                # 处理完成的任务
                for future in as_completed(futures):
                    seg = futures[future]
                    seg_num = seg["seg_num"]
                    try:
                        success = future.result()
                        if success:
                            file_path = os.path.join(output_dir, f"seg-{seg_num}.ts")
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                seg["success"] = True
                                downloaded = len([s for s in segment_info if s["success"]])
                                print(f"分片 {seg_num} 下载成功（累计成功：{downloaded}/{total}）")
                            else:
                                seg["success"] = False
                                os.remove(file_path) if os.path.exists(file_path) else None
                                print(f"分片 {seg_num} 下载后文件为空，标记为失败")
                        else:
                            seg["success"] = False
                            print(f"分片 {seg_num} 下载失败")
                    except Exception as e:
                        seg["success"] = False
                        print(f"分片 {seg_num} 处理异常: {str(e)}")

                    # 更新进度
                    downloaded = len([s for s in segment_info if s["success"]])
                    progress = int(downloaded / total * 100)
                    speed_info = f" | 速度: {self.current_speed:.2f} MB/s"
                    self.progress_callback(f"下载分片 {downloaded}/{total}{speed_info}", progress, "info")

                    # 主动触发检测，解决卡顿不更新
                    self.calculate_download_speed(0)

                    # 检查停止信号
                    if self.stop_event.is_set():
                        executor.shutdown(wait=False)
                        return False, "下载被中断"

            # 全局重试计数+1
            global_retry_count += 1

        # 检查所有分片是否成功
        all_success = all([seg["success"] for seg in segment_info])
        downloaded = len([s for s in segment_info if s["success"]])

        # 返回结果
        if all_success:
            return True, f"所有 {total} 个分片下载完成"
        else:
            failed_seg_nums = [seg["seg_num"] for seg in segment_info if not seg["success"]]
            return False, f"经过 {max_global_retries} 次全局重试后，仍有 {len(failed_seg_nums)} 个分片下载失败：{failed_seg_nums}"

    def get_unique_output_file(self, output_dir, raw_name):
        """
        获取唯一的输出文件名（避免重复）
        :param output_dir: 输出目录
        :param raw_name: 原始文件名
        :return: 唯一的文件路径
        """
        # 兜底空文件名 → 时间戳默认名
        if not raw_name or raw_name is None or raw_name.strip() == "":
            raw_name = f"video_{int(time.time())}"

        # 清理非法字符
        clean_name = raw_name.strip()
        for char in '<>:"|?*/\\':
            clean_name = clean_name.replace(char, "_")

        # 构建基础路径
        base_file = f"{clean_name}.mp4"
        full_path = os.path.join(output_dir, base_file)

        # 处理重复文件
        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(output_dir, f"{clean_name}_{counter}.mp4")
            counter += 1

        return full_path

    def merge_video_segments(self, input_dir, output_dir, file_name):
        """
        合并TS分片为MP4文件（基于FFmpeg）
        :param input_dir: TS分片目录
        :param output_dir: 最终视频输出目录
        :param file_name: 纯文件名（不带路径、不带后缀）
        :return: 元组 (是否成功, 结果消息, 最终文件路径)
        """
        try:
            # 获取唯一输出文件名
            output_file = self.get_unique_output_file(output_dir, file_name)

            # 收集并排序TS文件
            ts_files = []
            for f in os.listdir(input_dir):
                if f.endswith('.ts'):
                    match = re.findall(r'seg-(\d+)\.ts', f)
                    if match:
                        try:
                            seg_num = int(match[0])
                            ts_files.append((seg_num, f))
                        except ValueError:
                            continue

            # 按分片序号排序
            ts_files.sort(key=lambda x: x[0])
            ts_files = [f[1] for f in ts_files]

            # 检查TS文件
            if not ts_files:
                return False, "未找到有效TS分片文件（文件名需符合seg-数字.ts格式）", ""

            # 创建文件列表
            list_file = os.path.join(input_dir, "file_list.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for ts_file in ts_files:
                    ts_path = os.path.abspath(os.path.join(input_dir, ts_file))
                    ts_path = ts_path.replace("\\", "/")
                    f.write(f"file '{ts_path}'\n")

            # 构建FFmpeg命令
            ffmpeg_path = get_resource_path(FFMPEG_RELATIVE_PATH)
            cmd = [
                ffmpeg_path,
                '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-hide_banner',
                '-loglevel', 'error',
                output_file
            ]

            # 执行FFmpeg命令
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.run(
                cmd,
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                capture_output=True,
                timeout=300
            )

            # 检查输出文件
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1024:
                os.remove(list_file)
                file_size = os.path.getsize(output_file) / (1024 * 1024)
                return True, f"视频合并完成: {output_file}（大小：{file_size:.2f}MB）", output_file
            else:
                # 获取错误信息
                try:
                    error_msg = process.stderr.decode('utf-8', errors='ignore')[:500]
                except:
                    error_msg = process.stderr.decode('gbk', errors='ignore')[:500]
                return False, f"合并失败：文件为空或创建失败\n错误信息：{error_msg}", ""

        except Exception as e:
            error_detail = f"合并异常: {str(e)}"
            print(f"合并失败详情：{error_detail}")
            import traceback
            traceback.print_exc()
            return False, error_detail, ""

    def close(self):
        """
        关闭Chrome驱动，清理资源
        """
        try:
            self.stop_event.set()
            time.sleep(1)
            self.driver.quit()
        except:
            pass
