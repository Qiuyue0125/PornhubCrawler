# PHCrawler

PHCrawler 是一款面向 Windows 的图形化视频解析与批量下载工具，支持单个视频下载、列表批量处理、并发下载、失败重试及任务管理。

## 下载

[下载最新版 PHCrawler（Windows x64）](https://github.com/Qiuyue0125/PHCrawler/releases/latest/download/PHCrawler-Windows-x64.zip)

下载 ZIP 后请完整解压，再运行其中的 `ph_crawler.exe`。程序依赖压缩包内附带的浏览器、驱动和 FFmpeg 文件，请勿只复制 exe 单独运行。

## 默认界面

发布版本默认使用正常模式：

```json
"_UI_MODE": 1
```

正常模式会显示完整的文件与任务管理界面；将其设为 `0` 时会切换至简化界面。

## 主要功能

- 支持单个视频链接解析与下载
- 支持列表页面批量提取和下载
- 支持并发任务、分片下载与自动重试
- 支持暂停、停止及失败任务记录
- 使用内附浏览器和驱动完成页面解析
- 使用 FFmpeg 处理视频流与合并文件
- 可通过 `config.json` 调整线程数、超时、重试次数和输出目录

## 使用方法

1. 下载并完整解压 Release 中的 ZIP 文件。
2. 运行 `ph_crawler.exe`。
3. 在单视频或批量下载区域填写目标链接。
4. 按需设置输出目录、并发数和重试参数。
5. 启动任务，并在文件管理区域查看结果。

## 配置说明

程序读取随发行包提供的 `config.json`。修改后需要重启程序才能生效。常用设置包括：

- `_UI_MODE`：`1` 为完整界面，`0` 为简化界面
- `DEFAULT_MAX_WORKERS`：并发线程数
- `DEFAULT_BATCH_INTERVAL`：批量任务间隔
- `OUTPUT_DIR_ABSOLUTE`：默认下载目录
- `BATCH_VIDEO_LINKS`：批量下载快捷链接

## 从源码运行

需要 Windows 和 Python 3.10 或更高版本：

```powershell
cd ph_crawler
python -m pip install -r requirements.txt
python main.py
```

## 打包

在 `ph_crawler` 目录执行：

```powershell
pyinstaller --noconfirm --clean --distpath ../dist --workpath ../build ph_crawler.spec
```

打包结果位于 `dist/ph_crawler`。`ph_crawler.spec` 已将 `Bin/ico.ico` 嵌入 exe，并把运行所需资源复制到发行目录。

## 使用说明

本工具仅用于处理你有权访问和下载的内容。使用者应遵守目标网站的服务条款以及所在地法律法规，并自行承担使用责任。请勿将其用于侵权、绕过访问控制或其他未经授权的用途。
