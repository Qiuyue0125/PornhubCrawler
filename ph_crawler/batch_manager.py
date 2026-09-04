import time
import re
import threading
import requests
import urllib3
import datetime
from urllib.parse import urljoin
import tkinter as tk
from bs4 import BeautifulSoup

from config import GAL_PROXIES, dynamic_config,BATCH_FAILED_LOG_PATH

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BatchDownloadManager:
    """批量下载管理器"""

    def __init__(self, parent):
        self.parent = parent
        self.current_batch_urls = []
        self.current_index = 0
        self.batch_downloading = False
        self.batch_total = 0
        self.batch_success = 0
        self.batch_failed = 0
        self.current_fail_reason = ""

    def extract_links_from_page(self, url):
        """从页面提取所有视频链接"""
        all_links = []

        # 解析页码
        page_value = 1
        base_url = url
        if 'page=' in url:
            page_match = re.search(r'([?&])page=(\d+)', url)
            if page_match:
                page_value = int(page_match.group(2))
                base_url = re.sub(r'([?&])page=\d+', '', url).rstrip('?&')
        if '?' in base_url:
            base_url += '&page={}'
        else:
            base_url += '?page={}'

        print(f"基础URL: {base_url}")
        print(f"起始页码: {page_value}")
        print(f"计划下载页数: {self.parent.download_page}")

        # 循环下载多页
        for page in range(page_value, page_value + self.parent.download_page):
            current_url = base_url.format(page)
            page_index = page - page_value + 1
            page_total = self.parent.download_page
            self.parent.root.after(
                0,
                lambda current=page_index, total=page_total:
                    self.parent.update_batch_prepare_progress(current, total),
            )
            print(f"\n=== 开始处理第 {page} 页 ===")
            print(f"页面URL: {current_url}")

            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                }

                response = requests.get(current_url, headers=headers, timeout=30, proxies=GAL_PROXIES, verify=False)
                response.raise_for_status()

                generic_pattern = r'(?:href|src|data-src)\s*=\s*[\'"]?([^\'" >]*?/view_video\.php\?viewkey=[a-zA-Z0-9]{10,})[^\'">]*[\'"]?'

                soup = BeautifulSoup(response.text, 'html.parser')
                all_a_tags = soup.find_all('a')

                # 核心配置
                valid_phase = False
                trigger_class_set = {'gtm-event-watch-page', 'playAllLink'}
                exclude_class = 'gtm-event-watch-page'
                matches = []  # 按遍历顺序存储，保留重复
                seen_hrefs = set()  # 记录已添加的href，用于去重（保留首次）

                matched_count = 0

                for idx, a_tag in enumerate(all_a_tags, 1):
                    a_tag_str = str(a_tag)
                    a_classes = a_tag.get('class', [])
                    a_class_str = ' '.join(a_classes)

                    if not valid_phase:
                        if trigger_class_set.issubset(set(a_classes)):
                            valid_phase = True

                        continue  # 未触发则跳过后续

                    if not re.search(generic_pattern, a_tag_str, re.IGNORECASE):
                        continue

                    if exclude_class in a_class_str:
                        continue

                    tag_matches = re.findall(generic_pattern, a_tag_str, re.IGNORECASE)
                    for href in tag_matches:
                        if href not in seen_hrefs:
                            seen_hrefs.add(href)
                            matches.append(href)
                            matched_count += 1


                links = []
                for match in matches:
                    if ' ' in match:
                        match = match.split(' ')[0]
                    match = match.strip()
                    full_url = match if match.startswith('http') else urljoin(response.url, match)
                    if full_url not in links:
                        links.append(full_url)

                # 去重
                unique_links = []
                seen = set()
                for link in links:
                    viewkey_match = re.search(r'viewkey=([a-zA-Z0-9]{10,})', link, re.IGNORECASE)
                    if viewkey_match:
                        viewkey = viewkey_match.group(1)
                        if viewkey not in seen:
                            seen.add(viewkey)
                            unique_links.append(link)

                    else:
                        if link not in seen:
                            seen.add(link)
                            unique_links.append(link)

                print(f"从第 {page} 页提取到 {len(unique_links)} 个唯一视频链接")
                all_links.extend(unique_links)

                if page < page_value + self.parent.download_page - 1:
                    time.sleep(1)

            except requests.exceptions.RequestException as e:
                print(f"下载第 {page} 页失败: {e}")
                continue
            except Exception as e:
                print(f"处理第 {page} 页时发生错误: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 最终去重
        final_links = []
        final_seen = set()
        for link in all_links:
            viewkey_match = re.search(r'viewkey=([a-zA-Z0-9]{10,})', link, re.IGNORECASE)
            if viewkey_match:
                viewkey = viewkey_match.group(1)
                if viewkey not in final_seen:
                    final_seen.add(viewkey)
                    final_links.append(link)
                else:
                    print("重复link:" + viewkey)
            else:
                if link not in final_seen:
                    final_seen.add(link)
                    final_links.append(link)

        print(f"\n=== 所有页面处理完成 ===")
        print(f"总共提取到 {len(all_links)} 个唯一视频链接")
        print(f"最终去重后得到 {len(final_links)} 个唯一视频链接")
        print(final_links)

        return final_links

    def filter_links_by_start_url(self, links, start_video_url):
        """根据起始链接过滤下载队列"""
        if not start_video_url:
            return links

        filtered_links = []
        start_found = False
        for link in links:
            if link.strip() == start_video_url.strip():
                start_found = True
                filtered_links.append(link)
                print(f"找到起始链接: {link}，开始加入后续链接")
            elif start_found:
                filtered_links.append(link)

        if not start_found:
            print(f"未找到起始链接: {start_video_url}，将下载所有链接")
            return links

        print(f"过滤后剩余链接数: {len(filtered_links)}")
        return filtered_links

    def start_batch_download(self, list_url, start_video_url="", reverse_download=False):
        """开始批量下载"""
        if self.batch_downloading:
            return

        self.batch_downloading = True
        prepare_thread = threading.Thread(
            target=self._prepare_batch_download,
            args=(list_url, start_video_url, reverse_download, self.parent.jump_page),
            daemon=True,
        )
        prepare_thread.start()

    def _prepare_batch_download(self, list_url, start_video_url, reverse_download, jump_page):
        """在后台提取并整理批量链接，避免阻塞界面。"""
        try:
            links = self.extract_links_from_page(list_url)
        except Exception as exc:
            message = f"提取批量链接失败：{exc}"
            self.parent.root.after(0, lambda message=message: self._batch_prepare_failed(message))
            return

        if not links:
            self.parent.root.after(0, lambda: self._batch_prepare_failed("未找到视频链接"))
            return

        # 第一步：整体倒序
        if reverse_download:
            links = links[::-1]
            print(f"已将所有链接整体倒序，当前前5个链接: {links[:5]}...")

        # 第二步：跳过指定数量（倒序后）
        if len(links) > jump_page:
            links = links[jump_page:]
            print(f"已跳过倒序后列表的前 {jump_page} 个链接，剩余 {len(links)} 个")
        elif jump_page > 0:
            print(f"跳过数 {jump_page} 大于链接总数 {len(links)}，无链接剩余")
            self.parent.root.after(0, lambda: self._batch_prepare_failed("跳过数大于链接总数，无视频可下载"))
            return

        # 第三步：过滤起始链接
        filtered_links = self.filter_links_by_start_url(links, start_video_url)

        self.parent.root.after(
            0,
            lambda: self._begin_prepared_batch(filtered_links, reverse_download, jump_page),
        )

    def _begin_prepared_batch(self, filtered_links, reverse_download, jump_page):
        """回到界面线程启动已经准备好的下载队列。"""
        if not self.batch_downloading:
            return

        self.current_batch_urls = filtered_links
        self.current_index = 0
        self.batch_total = len(filtered_links)
        self.batch_success = 0
        self.batch_failed = 0

        print(f"开始批量下载（倒序: {reverse_download}，跳过数: {jump_page}），共 {self.batch_total} 个视频")
        self.parent.update_batch_status()
        self._download_next_video()

    def _batch_prepare_failed(self, message):
        """批量链接准备失败后恢复界面状态。"""
        self.batch_downloading = False
        self.parent.is_batch_downloading = False
        self.parent.batch_download_btn.config(state=tk.NORMAL)
        self.parent.download_btn.config(state=tk.NORMAL)
        self.parent.progress_bar.stop()
        self.parent.progress_bar.config(mode="determinate")
        self.parent.progress_bar["value"] = 0
        self.parent.batch_info_label.config(text="")
        self.parent.status_label.config(text=message, foreground="red")
        self.parent.show_error(message)

    def _download_next_video(self):
        """下载下一个视频"""
        if self.current_index >= len(self.current_batch_urls) or not self.batch_downloading:
            self.batch_downloading = False
            self.parent.update_batch_status()
            return

        # 重置状态
        self.parent.m3u8_url = None
        self.parent.is_resuming = False

        url = self.current_batch_urls[self.current_index]
        print(f"开始下载第 {self.current_index + 1}/{self.batch_total} 个视频: {url}")
        self.current_fail_reason = ""

        # 更新UI
        self.parent.url_entry.delete(0, tk.END)
        if not self.parent.safe_mode:
            self.parent.url_entry.insert(0, url)
        self.parent.clean_build_dir()

        # 启动下载
        self.parent.start_download_single_for_batch(url, self._on_single_download_complete)

    def _on_single_download_complete(self, success, error_msg=""):
        """单个视频下载完成回调"""
        if success:
            self.batch_success += 1
            print(f"第 {self.current_index + 1} 个视频下载成功")

        else:
            self.batch_failed += 1
            self.current_fail_reason = error_msg if error_msg else "未知错误"
            failed_url = self.current_batch_urls[self.current_index]  # 失败的链接
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(BATCH_FAILED_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"时间：{timestamp}\n链接：{failed_url}\n错误原因：{self.current_fail_reason}\n{'-' * 50}\n")
            print(f"[{timestamp}] 第 {self.current_index + 1} 个视频下载失败: {error_msg}")

        # 重置状态
        self.parent.m3u8_url = None
        self.parent.is_resuming = False
        self.parent.download_btn.config(text="开始下载")
        self.parent.clean_build_dir()

        self.current_index += 1
        self.parent.update_batch_status()

        # 批量间隔使用界面定时器，避免阻塞回调线程或与下一下载器交叉。
        batch_interval = dynamic_config["batch_interval"]
        self.parent.root.after(
            max(0, int(batch_interval * 1000)),
            self._download_next_video,
        )

    def stop_batch(self):
        """停止批量下载"""
        self.batch_downloading = False
        self.parent.update_batch_status()
