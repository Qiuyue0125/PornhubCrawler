# PornhubCrawler

[中文](README.md) | [English](README_EN.md)

PornhubCrawler 是一款面向 Windows 的 Pornhub 专用图形化视频下载工具，支持单视频下载、列表批量处理、多页面连续下载、并发下载、失败重试及任务管理。

> 本项目仅针对 Pornhub 的页面结构和视频资源实现，不适配其他视频网站，也不提供通用网站解析能力。

> **使用限制：本项目仅供个人学习、技术研究与交流，禁止任何商业用途，包括但不限于销售、付费分发、商业服务及商业获利。**

## 下载

[下载最新版 PornhubCrawler（Windows x64）](https://github.com/Qiuyue0125/PornhubCrawler/releases/latest/download/PHCrawler-Windows-x64.zip)

下载 ZIP 后请完整解压，再运行其中的 `ph_crawler.exe`。程序依赖压缩包内附带的浏览器、驱动和 FFmpeg 文件，请勿只复制 exe 单独运行。

## 界面预览

### 下载页面

支持单视频和列表批量下载。在“提取页数”中填写需要处理的分页数量，即可从批量 URL 开始连续提取并下载多个页面；“跳过数”可跳过列表开头的指定视频数量。

![下载页面](./assets/download-page.png)

### 输出目录

集中查看已下载文件、文件大小和视频预览，并可快速打开输出目录。

![输出目录](./assets/output-page.png)

### 下载参数

可调整线程数、批量间隔、分片重试、连接与读取超时、M3U8 解析重试等参数。

![下载参数](./assets/download-settings.png)

### 路径与快捷链接

可设置视频输出目录、单视频默认链接，以及添加或删除批量下载快捷链接。

![路径与快捷链接](./assets/path-link-settings.png)

## 默认界面

发布版本默认使用完整的正常模式：

```json
"_UI_MODE": 1
```

正常模式会显示完整的文件与任务管理界面；将其设为 `0` 时会切换至简化界面。

## 主要功能

- 支持 Pornhub 单个视频链接解析与下载
- 支持 Pornhub 列表页面批量提取和下载
- 支持多页面连续下载，只需填写“提取页数”
- 支持并发任务、分片下载与自动重试
- 支持暂停、停止及失败任务记录
- 支持已下载文件管理和视频预览
- 使用内附浏览器和驱动完成页面解析
- 使用 FFmpeg 处理视频流与合并文件
- 可通过图形界面或 `config.json` 调整下载参数和输出目录

## 使用方法

1. 下载并完整解压 Release 中的 ZIP 文件。
2. 运行 `ph_crawler.exe`。
3. 单视频下载：填写一个 Pornhub 视频链接，然后点击“开始下载”。
4. 批量下载：填写 Pornhub 列表页 URL，在“提取页数”中填写要连续处理的页数，然后点击“开始批量下载”。
5. 如有需要，可填写“跳过数”或勾选“倒序下载”。
6. 在“输出目录”页面查看和管理下载结果。

例如，将“提取页数”设为 `5`，程序会从所填列表 URL 对应的页面开始，连续处理 5 页内容。

## 配置说明

程序读取随发行包提供的 `config.json`，修改后需要重启程序才能生效。常用设置包括：

- `_UI_MODE`：`1` 为完整界面，`0` 为简化界面
- `DEFAULT_MAX_WORKERS`：并发线程数
- `DEFAULT_BATCH_INTERVAL`：批量任务间隔
- `DEFAULT_DOWNLOAD_PAGE`：批量下载默认提取页数
- `DEFAULT_JUMP_PAGE`：批量下载默认跳过视频数
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

## 声明与使用限制

- 本项目仅供个人学习、技术研究和非商业交流。
- 禁止将本项目或其衍生版本用于任何商业用途、收费分发、付费服务或商业获利。
- 仅可处理你有权访问和下载的内容；请遵守 Pornhub 服务条款及所在地法律法规。
- 禁止用于侵犯版权、传播非法内容、绕过访问控制或其他未经授权的行为。
- 本项目不隶属于 Pornhub，也未获得 Pornhub 的官方认可或授权。
- 使用者须自行承担使用本项目所产生的全部责任。
