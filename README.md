# NBA 数据服务平台

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**一个强大的 Python 库，用于获取、解析、分析和展示 NBA 比赛的各种数据。**

本项目旨在为 NBA 爱好者、数据分析师和开发者提供一个全面且易于使用的平台，以访问和利用丰富的 NBA 比赛数据。它集成了数据抓取、解析、缓存、可视化、AI 分析以及社交媒体发布等功能，帮助用户深入了解 NBA 赛事，并进行数据驱动的应用开发。

## 主要特性

### 全面的数据获取

* 支持获取比赛的实时和历史数据，包括比赛 Boxscore、PlayByPlay、赛程、联盟排名、球员信息、球队信息和视频集锦等
* 数据源自 NBA 官方网站和 Stats API，保证数据的权威性和准确性

### 高效的数据处理

* 使用 Pydantic v2 模型进行数据结构化和验证，确保数据质量
* 强大的数据解析器，将原始 API 数据转换为易于使用和分析的 Python 对象
* 内置缓存机制，支持动态缓存时长，减少 API 请求，提高数据访问速度

### 丰富的数据展示

* 提供多种数据格式化输出，包括 JSON、文本和 Markdown
* 集成 AI 服务（可选），支持比赛事件分析和摘要生成，提供更深入的赛事解读
* 强大的图表生成功能，可以绘制球员投篮点图、助攻分布图和得分影响力图，直观展示比赛数据
* 支持生成比赛精彩瞬间的 GIF 动画和 MP4 视频集锦

### 灵活的配置选项

* 通过 `NBAServiceConfig` 类提供统一的配置管理，可以自定义 API 密钥、存储路径、缓存策略、显示语言等
* 模块化设计，各个子服务（数据服务、显示服务、图表服务、视频服务、AI 服务）可独立配置和使用

### 社交媒体集成

* 集成微博发布功能，可以将比赛分析、精彩瞬间等内容自动发布到微博平台（需要配置微博 API）

### 易于扩展和定制

* 模块化架构和清晰的代码结构，方便用户进行二次开发和功能扩展
* 提供丰富的 API 接口，方便用户在自己的项目中使用 NBA 数据服务

## 快速开始

### 1. 环境准备

* Python 版本：Python 3.8 或更高版本
* 安装依赖：

```bash
pip install -r requirements.txt
```

### 2. 配置

* 复制配置文件：复制 `.env.example` 文件并重命名为 `.env`，然后根据需要修改其中的配置项。

```bash
cp .env.example .env
```

* 配置项说明（部分重要配置）：
  * `WB_COOKIES`：微博 Cookies，用于微博发布功能（可选）
  * `AI_API_KEY`：AI 服务 API 密钥（可选，用于 AI 分析功能）
  * `AI_BASE_URL`：AI 服务 API 基础 URL（可选，用于 AI 分析功能）

### 3. 运行示例

以下是一些基本的使用示例，更多用法请参考代码和文档。

#### 获取今日湖人队比赛的基本信息

```python
from nba.services.nba_service import NBAService

with NBAService() as nba_service:
    game_info = nba_service.format_basic_game_info(team="Lakers", date="today")
    if game_info:
        print(game_info)
    else:
        print("未找到比赛信息")
```

#### 获取勇士队最近一场比赛的所有球员统计数据

```python
from nba.services.nba_service import NBAService

with NBAService() as nba_service:
    player_stats = nba_service.format_player_stats(team="Warriors", date="last")
    if player_stats:
        for stat in player_stats:
            print(stat)
    else:
        print("未找到球员统计数据")
```

#### 绘制 LeBron James 在最近一场比赛的得分影响力图

```python
from nba.services.nba_service import NBAService

with NBAService() as nba_service:
    chart_path = nba_service.plot_player_scoring_impact(
        team="Lakers", 
        player_name="LeBron James", 
        title="LeBron James 得分影响力图"
    )
    if chart_path:
        print(f"图表已保存到: {chart_path}")
    else:
        print("图表生成失败")
```

#### 获取最近一场湖人队比赛的投篮命中视频集锦

```python
import asyncio
from nba.services.nba_service import NBAService
from nba.models.video_model import ContextMeasure

async def get_videos():
    with NBAService() as nba_service:
        video_paths = nba_service.get_game_videos(
            team="Lakers",
            context_measure=ContextMeasure.FGM
        )
        if video_paths:
            for event_id, path in video_paths.items():
                print(f"Event ID: {event_id}, 视频保存路径: {path}")
        else:
            print("未找到视频集锦")

asyncio.run(get_videos())
```

## 配置详解

`NBAServiceConfig` 类提供了丰富的配置选项，可以通过修改配置来自定义 NBA 数据服务的行为。以下是主要配置项的说明：

### 基础配置

* `team`：默认球队名称，用于在未指定球队时获取默认球队的数据
* `player`：默认球员名称，用于在未指定球员时获取默认球员的数据
* `date_str`：默认日期字符串，用于在未指定日期时获取默认日期的比赛数据
* `language`：显示语言，目前支持 "zh_CN"（中文）和 "en_US"（英文）

### AI 配置（可选）

* `use_ai`：是否启用 AI 服务，默认为 `True`
* `ai_api_key`：AI 服务 API 密钥
* `ai_base_url`：AI 服务 API 基础 URL

### 图表配置

* `chart_style`：`ChartStyleConfig` 对象，用于配置图表样式

### 视频配置

* `video_format`：视频输出格式，可选 "mp4" 或 "gif"
* `video_quality`：视频质量，可选 "sd"（标清）或 "hd"（高清）
* `gif_config`：`GIFConfig` 对象，用于配置 GIF 转换参数

### 存储配置

* `storage_paths`：字典，用于配置各种文件的存储路径

### 其他配置

* `cache_size`：缓存大小，默认为 128
* `auto_refresh`：是否自动刷新数据，默认为 `False`
* `use_pydantic_v2`：是否使用 Pydantic v2 版本，默认为 `True`

## 模块结构

```
nba-data-service/
├── config/                # 配置文件和路径配置
├── nba/                   # NBA 数据服务核心模块
│   ├── fetcher/          # 数据抓取模块
│   ├── models/           # 数据模型定义
│   ├── parser/           # 数据解析模块
│   ├── services/         # 服务层模块
├── utils/                 # 工具模块
├── weibo/                # 微博发布模块
├── .env.example          # 环境变量配置文件示例
├── requirements.txt      # Python 依赖文件
└── README.md             # 项目 README 文件
```

## 贡献

欢迎任何形式的贡献，包括但不限于：

* 提交 Bug 报告
* 提出功能建议
* 贡献代码（例如，添加新的数据源、解析器、可视化功能等）
* 完善文档

请在提交 Pull Request 之前，确保代码风格符合 PEP 8 规范，并添加必要的单元测试。

## 许可证

本项目采用 MIT License 开源许可证，详情请见 [LICENSE](LICENSE) 文件。

## 联系方式

如果您有任何问题或建议，欢迎通过 GitHub Issues 或 Email 联系我。

**感谢您的使用和支持！**