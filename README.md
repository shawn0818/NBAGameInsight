# NBAGameInsight: NBA 数据洞察平台

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**一个强大且智能的 Python 工具，用于获取、解析、分析和展示 NBA 比赛的各类数据。**

NBAGameInsight 专注于为 NBA 爱好者、数据分析师和开发者提供全方位的数据服务。项目整合了数据抓取、结构化解析、可视化展示、智能 AI 分析和社交媒体发布等功能，旨在让用户深入洞察 NBA 赛事，并基于数据驱动开发各种应用。

---

## 主要特性

### 全面数据获取
- **实时与历史数据：** 支持获取比赛的 Boxscore、PlayByPlay、赛程、联盟排名、球员与球队信息、视频集锦等。
- **权威数据源：** 数据源自 NBA 官方及 Stats API，确保数据准确性。

### 高效数据处理
- **结构化数据：** 基于 Pydantic v2 模型进行数据验证和转换，确保数据质量。
- **智能解析：** 强大的解析器将原始数据转换为易用的 Python 对象，并内置缓存机制以提升响应速度。

### 丰富数据展示
- **多格式输出：** 支持 JSON、文本、Markdown 等多种输出格式。
- **可视化图表：** 绘制投篮点图、得分影响力图等，让比赛数据一目了然。
- **视频与 GIF 集锦：** 生成比赛精彩瞬间的视频集锦和 GIF 动画，捕捉关键时刻。

### 智能 AI 分析
- **AI 助力：** 集成 AI 服务，实现比赛事件深度分析、摘要生成和球员表现评估，提供更深入的赛事洞察。

### 灵活的命令行工具
- **多模式支持：** 提供 Info、Chart、Video、Weibo、AI、New Season 等多种运行模式，满足不同场景需求。
- **命令组合：** 内置组合命令，可一次性执行多个任务，提升工作效率。

### 社交媒体集成
- **微博发布：** 支持将比赛分析、图表、视频等内容自动发布到微博平台（需配置微博 API）。

---

## 快速开始

### 1. 环境准备

- **Python 版本：** Python 3.8 或更高版本  
- **安装依赖：**

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

### 3. 命令行使用方法

项目提供了灵活的命令行工具，可以通过不同的运行模式满足各种需求。

```bash
python main.py [--team TEAM] [--player PLAYER] [--date DATE] [--mode MODE] [--no-weibo] [--debug] [--config CONFIG] [--new-season NEW_SEASON]
```

#### 参数说明：

- `--team`：指定球队，默认为 "Lakers"
- `--player`：指定球员，默认为 "LeBron James"
- `--date`：指定日期，默认为 "last"（最近一场比赛）
- `--mode`：运行模式，选项包括：
  - `info`：只显示比赛信息
  - `chart`：只生成图表
  - `video`：处理所有视频
  - `video-team`：只处理球队视频
  - `video-player`：只处理球员视频
  - `video-rounds`：处理球员视频的回合GIF
  - `weibo`：执行所有微博发布功能
  - `weibo-team`：只发布球队集锦视频
  - `weibo-player`：只发布球员集锦视频
  - `weibo-chart`：只发布球员投篮图
  - `weibo-team-chart`：只发布球队投篮图
  - `weibo-round`：只发布球员回合解说和GIF
  - `ai`：只运行AI分析
  - `all`：执行所有功能（默认）
  - `new_season`：新赛季同步更新数据库
- `--no-weibo`：不发布到微博
- `--debug`：启用调试模式，输出详细日志
- `--config`：指定配置文件
- `--new-season`：指定新赛季标识，例如 '2025-26'，用于更新数据库新赛季数据

#### 示例：

```bash
# 获取湖人队最近一场比赛的信息
python main.py --team Lakers --mode info

# 获取LeBron James最近一场比赛的统计并生成投篮图
python main.py --team Lakers --player "LeBron James" --mode chart

# 生成Warriors最近一场比赛的视频集锦
python main.py --team Warriors --mode video-team

# 生成Stephen Curry最近一场比赛的集锦视频并发布到微博
python main.py --team Warriors --player "Stephen Curry" --mode weibo-player

# 执行对Durant最近一场比赛的AI分析
python main.py --team Suns --player "Kevin Durant" --mode ai

# 更新2025-26赛季数据
python main.py --mode new_season --new-season "2025-26"
```

### 4. 程序化使用示例

除了命令行工具，您还可以在自己的Python程序中使用该库：

```python
from nba.services.nba_service import NBAService, NBAServiceConfig

# 创建配置
config = NBAServiceConfig(
    default_team="Lakers",
    default_player="LeBron James",
    date_str="last"
)

# 使用上下文管理器确保资源正确关闭
with NBAService(config=config) as nba_service:
    # 获取比赛基本信息
    game = nba_service.data_service.get_game("Lakers")
    if game:
        print(f"比赛ID: {game.game_data.game_id}")
        print(f"主队: {game.game_data.home_team.team_city} {game.game_data.home_team.team_name}")
        print(f"客队: {game.game_data.away_team.team_city} {game.game_data.away_team.team_name}")
        
    # 生成球员投篮图
    chart_paths = nba_service.generate_shot_charts(
        player_name="LeBron James",
        chart_type="both",
        shot_outcome="made_only"
    )
    
    # 获取球员集锦视频
    player_videos = nba_service.get_player_highlights(
        player_name="LeBron James",
        merge=True
    )
```

## 配置详解

`NBAServiceConfig` 类提供了丰富的配置选项，可以通过修改配置来自定义 NBA 数据服务的行为。以下是主要配置项的说明：

### 基础配置

* `default_team`：默认球队名称，用于在未指定球队时获取默认球队的数据
* `default_player`：默认球员名称，用于在未指定球员时获取默认球员的数据
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

## 项目结构

主要模块和组件如下：

```
NBAGameInsight/
├── config/ # 配置模块
│   └── nba_config.py # NBA数据服务配置
├── nba/ # 核心功能模块
│   ├── models/ # 数据模型
│   └── services/ # 服务模块
│       ├── data_service.py # 数据服务
│       ├── game_video_service.py # 视频服务
│       ├── nba_service.py # 主服务
│       └── shot_chart_service.py # 投篮图服务
├── utils/ # 工具模块
│   ├── ai_processor.py # AI处理
│   ├── logger_handler.py # 日志处理
│   └── video_converter.py # 视频转换
├── weibo/ # 微博集成模块
│   ├── weibo_content_generator.py # 微博内容生成
│   └── weibo_post_service.py # 微博发布服务
└── main.py # 主程序入口
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