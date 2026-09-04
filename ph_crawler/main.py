import threading
import tkinter as tk
import shutil
import os
import subprocess
import sys
import time


def relaunch_without_console():
    """开发环境使用 pythonw 运行，避免弹出控制台窗口。"""
    if os.name != "nt" or getattr(sys, "frozen", False):
        return False
    if os.environ.get("PH_CRAWLER_KEEP_CONSOLE") == "1":
        return False
    if os.path.basename(sys.executable).lower() != "python.exe":
        return False

    pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw_path):
        return False

    subprocess.Popen(
        [pythonw_path, os.path.abspath(__file__), *sys.argv[1:]],
        cwd=os.getcwd(),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return True


if __name__ == "__main__" and relaunch_without_console():
    raise SystemExit(0)


from config import BUILD_DIR
from video_downloader_app import VideoDownloaderApp


def enable_windows_dpi_awareness():
    """让字体和控件在 Windows 高 DPI 屏幕上保持清晰。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def hide_windows_titlebar_icon(window):
    """移除 Windows 标题栏左侧图标，保留标题和窗口控制按钮。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(window.winfo_id())
        mask_size = 32 * 4
        and_mask = (ctypes.c_ubyte * mask_size)(*([0xFF] * mask_size))
        xor_mask = (ctypes.c_ubyte * mask_size)(*([0x00] * mask_size))
        user32.CreateIcon.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_ubyte, ctypes.c_ubyte,
                                      ctypes.c_void_p, ctypes.c_void_p]
        user32.CreateIcon.restype = ctypes.c_void_p
        blank_icon = user32.CreateIcon(None, 32, 32, 1, 1, and_mask, xor_mask)
        window.blank_icon_handle = blank_icon
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW(hwnd, 0x0080, 0, blank_icon)
        user32.SendMessageW(hwnd, 0x0080, 1, blank_icon)
        set_class_long = getattr(user32, "SetClassLongPtrW", user32.SetClassLongW)
        set_class_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        set_class_long.restype = ctypes.c_void_p
        set_class_long(hwnd, -14, blank_icon)
        set_class_long(hwnd, -34, blank_icon)
        ex_style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, ex_style | 0x00000001)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except (AttributeError, OSError, tk.TclError):
        pass

# 打包指令（在 ph_crawler 目录执行）：
# ..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath ..\dist --workpath ..\build ph_crawler.spec
if __name__ == "__main__":
    enable_windows_dpi_awareness()

    try:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    except:
        pass

    # 初始化临时目录
    os.makedirs(BUILD_DIR, exist_ok=True)

    # 启动GUI应用
    root = tk.Tk()
    root.withdraw()
    app = VideoDownloaderApp(root)

    def show_main_window():
        root.attributes("-alpha", 0.0)
        root.deiconify()
        root.update_idletasks()
        hide_windows_titlebar_icon(root)
        root.attributes("-alpha", 1.0)
        root.lift()

    root.after_idle(show_main_window)


    # 关闭窗口时的清理逻辑
    def on_closing():
        root.destroy()

        # 后台清理函数
        def cleanup_background():
            current_cleanup_thread = threading.current_thread()
            try:
                # 标记停止下载，通知下载器终止任务
                app.stop_download = True

                # 等待下载线程完全结束
                if hasattr(app, 'download_thread') and app.download_thread and app.download_thread.is_alive():
                    print("等待下载线程结束...")
                    app.download_thread.join(timeout=10)
                    if app.download_thread.is_alive():
                        print("下载线程仍未结束，已超时")

                # 关闭下载器资源
                if hasattr(app, 'downloader') and app.downloader:
                    print("关闭下载器资源...")
                    app.downloader.close()

                # 等待所有非守护线程结束（核心修复：排除当前清理线程）
                print("等待所有后台线程结束...")
                main_thread = threading.main_thread()
                # 先收集需要等待的线程（排除主线程、当前清理线程、守护线程）
                threads_to_wait = []
                for thread in threading.enumerate():
                    if (thread is not main_thread and
                            thread is not current_cleanup_thread and  # 排除自己
                            thread.is_alive() and
                            not thread.daemon):
                        threads_to_wait.append(thread)

                # 逐个等待收集到的线程
                for thread in threads_to_wait:
                    print(f"等待线程 {thread.name} 结束...")
                    thread.join(timeout=5)
                    if thread.is_alive():
                        print(f"线程 {thread.name} 仍未结束，已超时")

                # 有线程结束后清理目录
                print("开始清理临时目录...")
                if os.path.exists(BUILD_DIR):
                    max_attempts = 5
                    attempt = 1
                    content_deleted = False
                    while attempt <= max_attempts and not content_deleted:
                        try:
                            shutil.rmtree(BUILD_DIR, ignore_errors=False)
                            content_deleted = True
                            print(f"第{attempt}次删除目录成功")
                        except Exception as e:
                            print(f"第{attempt}次删除目录失败: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            attempt += 1
                            time.sleep(4)

                # 清理空目录
                if os.path.exists(BUILD_DIR):
                    try:
                        os.rmdir(BUILD_DIR)
                        print("删除空目录成功")
                    except Exception as e:
                        print(f"删除空目录失败: {str(e)}")
                else:
                    print("临时目录已不存在")

            except Exception as e:
                print(f"清理过程出错: {str(e)}")
                import traceback
                traceback.print_exc()

        # 启动后台清理线程
        cleanup_thread = threading.Thread(target=cleanup_background, daemon=False, name="CleanupThread")
        cleanup_thread.start()

        print("等待清理完成...")
        cleanup_thread.join()
        print("所有清理工作完成，程序退出")

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
