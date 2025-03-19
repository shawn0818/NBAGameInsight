# NBAGameInsight: NBA比赛分析平台 | NBA Game Analysis Platform

<div align="center">

[![Python 版本](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![许可证](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[中文](README.md) | [English](#english-version)**

</div>

**一个强大且智能的 Python 工具，用于获取、解析、分析和可视化 NBA 比赛数据。**

NBAGameInsight 致力于为 NBA 爱好者、数据分析师和开发者提供全方位的数据服务。本项目整合了数据抓取、结构化解析、可视化展示、智能 AI 分析和社交媒体发布等功能，帮助用户深入洞察 NBA 赛事，并基于数据开发各种应用。

## 🌟 主要特性

### 📊 全面数据获取
- **实时与历史数据**：支持获取比赛的 Boxscore、PlayByPlay、赛程、联盟排名、球员与球队信息等
- **权威数据源**：数据来自 NBA 官方及 Stats API，确保数据准确性和实时性
- **增量更新**：支持新赛季数据自动同步，保持数据库最新状态

### 🔄 高效数据处理
- **结构化数据**：基于 Pydantic v2 模型进行数据验证和转换，确保数据质量
- **智能解析**：强大的解析器将原始数据转换为易用的 Python 对象
- **缓存机制**：内置智能缓存系统，大幅提升响应速度和性能

### 📈 可视化数据展示
- **专业投篮图**：生成球员和球队的投篮分布热图，直观展示得分热区
- **球员影响力分析**：可视化球员得分和助攻影响力，全面展示球员价值
- **多格式输出**：支持 JSON、Markdown 等多种输出格式，适应不同场景需求

### 🎬 视频集锦处理
- **自动下载**：从官方源自动获取比赛精彩片段和球员集锦
- **智能合并**：将零散片段合并为完整集锦视频，提供更好的观看体验
- **GIF 生成**：为关键回合创建高质量 GIF，便于分享和展示

### 🤖 智能 AI 分析
- **比赛摘要**：AI 生成专业的比赛分析和摘要，提供深度洞察
- **球员表现评估**：对球员数据进行智能分析，提供专业评价
- **回合解说**：为关键回合生成专业解说，捕捉比赛精彩瞬间

### 📱 社交媒体集成
- **微博发布**：支持将比赛分析、图表、视频等内容一键发布到微博
- **内容生成**：自动生成符合平台特性的文案和标签，提高传播效果
- **批量处理**：支持多内容类型的批量发布，高效管理社交媒体内容

### 🛠️ 灵活的命令行工具
- **多模式支持**：提供 Info、Chart、Video、Weibo、AI 等多种运行模式
- **自定义配置**：支持通过命令行参数或配置文件自定义行为
- **批量处理**：内置组合命令，可一次性执行多个任务

## 🚀 快速开始

### 环境准备

- **Python 要求**：Python 3.8 或更高版本
- **安装依赖**：

```bash
# 克隆仓库
git clone https://github.com/yourusername/NBAGameInsight.git
cd NBAGameInsight

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 基础配置

1. **复制配置文件模板**：

```bash
cp .env.example .env
```

2. **编辑配置文件**：根据需要修改 `.env` 文件中的配置项：

```
# 必要配置
API_KEY=your_nba_api_key

# 可选配置
WB_COOKIES=your_weibo_cookies  # 用于微博发布功能
AI_API_KEY=your_ai_api_key     # 用于AI分析功能
```

### 基本使用示例

#### 查看比赛信息

```bash
# 获取湖人队最近一场比赛的信息
python main.py --team Lakers --mode info
```

#### 生成投篮图表

```bash
# 生成LeBron James最近一场比赛的投篮图
python main.py --team Lakers --player "LeBron James" --mode chart
```

#### 处理视频集锦

```bash
# 生成Warriors队最近一场比赛的视频集锦
python main.py --team Warriors --mode video-team

# 生成Stephen Curry最近一场比赛的集锦视频
python main.py --team Warriors --player "Stephen Curry" --mode video-player
```

#### 发布到微博

```bash
# 发布Kevin Durant最近一场比赛的集锦视频到微博
python main.py --team Suns --player "Kevin Durant" --mode weibo-player
```

#### AI分析比赛

```bash
# 执行对Durant最近一场比赛的AI分析
python main.py --team Suns --player "Kevin Durant" --mode ai
```

#### 更新赛季数据

```bash
# 更新2025-26赛季数据
python main.py --mode new_season --new-season "2025-26"
```

### 命令行参数说明

```
参数            描述                               默认值
--team        指定球队                            Lakers
--player      指定球员                            LeBron James
--date        指定日期 (YYYY-MM-DD 或 "last")     last
--mode        运行模式                            all
--no-weibo    不发布到微博                        False
--debug       启用调试模式                        False
--config      指定配置文件路径                    
--new-season  指定新赛季标识                      
```

可选的运行模式:
- `info`: 只显示比赛信息
- `chart`: 只生成图表
- `video`: 处理所有视频
- `video-team`: 只处理球队视频
- `video-player`: 只处理球员视频
- `video-rounds`: 处理球员视频的回合GIF
- `weibo`: 执行所有微博发布功能
- `weibo-team`: 只发布球队集锦视频
- `weibo-player`: 只发布球员集锦视频
- `weibo-chart`: 只发布球员投篮图
- `weibo-team-chart`: 只发布球队投篮图
- `weibo-round`: 只发布球员回合解说和GIF
- `ai`: 只运行AI分析
- `all`: 执行所有功能 (默认)
- `new_season`: 新赛季同步更新数据库

## 💻 程序化使用示例

除了命令行工具，您还可以在自己的 Python 程序中直接使用该库：

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
    
    # 执行AI分析
    game_ai_data = game.prepare_ai_data()
    print(f"分析数据包含 {len(game_ai_data.get('events', {}).get('data', []))} 个事件")
```

## 📁 项目结构

```
NBAGameInsight/
├── nba/                 # 核心功能模块
│   ├── database/        # 数据库模块
│   ├── fetcher/         # 数据获取模块
│   ├── models/          # 数据模型
│   ├── parser/          # 数据解析模块
│   └── services/        # 服务模块
│       ├── nba_service.py         # 主服务
│       ├── game_data_service.py   # 数据服务
│       ├── game_video_service.py  # 视频服务
│       └── game_charts_service.py # 图表服务
├── weibo/               # 微博集成模块
│   ├── weibo_content_generator.py # 内容生成
│   └── weibo_post_service.py      # 发布服务
├── utils/               # 工具模块
│   ├── ai_processor.py     # AI 处理
│   ├── logger_handler.py   # 日志处理
│   └── video_converter.py  # 视频转换
├── data/                # 数据缓存
├── storage/             # 媒体存储
│   ├── pictures/        # 图表存储
│   ├── videos/          # 视频存储
│   └── gifs/            # GIF存储
├── main.py              # 主程序入口
├── config.py            # 全局配置模块    
├── requirements.txt     # 依赖列表
└── README.md            # 项目文档
```

## 🔗 实际应用案例

- **球队数据分析**：自动为球队生成每场比赛的数据报告和视频集锦
- **球员数据跟踪**：跟踪和分析特定球员的表现和进步情况
- **微博内容运营**：为 NBA 相关账号提供自动化内容发布解决方案
- **数据可视化展示**：生成专业的投篮分布图和影响力分析图表

## 🤝 贡献

欢迎任何形式的贡献，包括但不限于：

- 提交 Bug 报告
- 提出功能建议
- 贡献代码（例如，添加新的数据源、解析器、可视化功能等）
- 完善文档

请在提交 Pull Request 之前，确保代码风格符合 PEP 8 规范，并添加必要的单元测试。

## 📝 许可证

本项目采用 MIT License 开源许可证，详情请见 [LICENSE](LICENSE) 文件。

## 📧 联系方式

如果您有任何问题或建议，欢迎通过 GitHub Issues 或 Email 联系我们。

---

**感谢您的关注和支持！**

---

<a name="english-version"></a>

# NBAGameInsight: NBA Game Analysis Platform

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[中文](#) | [English](README_EN.md)**

</div>

**A powerful and intelligent Python tool for fetching, parsing, analyzing, and visualizing NBA game data.**

NBAGameInsight is dedicated to providing comprehensive data services for NBA enthusiasts, data analysts, and developers. This project integrates data scraping, structured parsing, visualization, intelligent AI analysis, and social media publishing capabilities to help users gain deep insights into NBA games and develop various applications based on the data.

## 🌟 Key Features

### 📊 Comprehensive Data Acquisition
- **Real-time & Historical Data**: Support for retrieving game Boxscores, PlayByPlay data, schedules, league standings, player and team information
- **Authoritative Data Sources**: Data from NBA official and Stats API, ensuring accuracy and timeliness
- **Incremental Updates**: Support for automatic synchronization of new season data, keeping the database up-to-date

### 🔄 Efficient Data Processing
- **Structured Data**: Data validation and conversion based on Pydantic v2 models, ensuring data quality
- **Intelligent Parsing**: Powerful parsers that convert raw data into easy-to-use Python objects
- **Caching Mechanism**: Built-in intelligent caching system that significantly improves response speed and performance

### 📈 Visual Data Display
- **Professional Shot Charts**: Generate shot distribution heat maps for players and teams, visually showing scoring hot zones
- **Player Impact Analysis**: Visualize player scoring and assist impact, comprehensively showcasing player value
- **Multiple Output Formats**: Support for JSON, Markdown, and other output formats to suit different scenarios

### 🎬 Video Highlights Processing
- **Automatic Downloads**: Automatically obtain game highlights and player compilations from official sources
- **Intelligent Merging**: Combine scattered clips into complete highlight videos for a better viewing experience
- **GIF Generation**: Create high-quality GIFs for key plays, facilitating sharing and display

### 🤖 Intelligent AI Analysis
- **Game Summaries**: AI-generated professional game analysis and summaries providing deep insights
- **Player Performance Evaluation**: Intelligent analysis of player data, providing professional evaluations
- **Play-by-Play Commentary**: Generate professional commentary for key moments, capturing the exciting moments of the game

### 📱 Social Media Integration
- **Weibo Publishing**: Support for one-click publishing of game analysis, charts, videos, and other content to Weibo
- **Content Generation**: Automatically generate platform-specific copy and tags to enhance dissemination effect
- **Batch Processing**: Support for batch publishing of multiple content types, efficiently managing social media content

### 🛠️ Flexible Command Line Tools
- **Multi-Mode Support**: Provides Info, Chart, Video, Weibo, AI and other operating modes
- **Custom Configuration**: Support for customizing behavior through command line parameters or configuration files
- **Batch Processing**: Built-in combination commands to execute multiple tasks at once

## 🚀 Quick Start

### Environment Preparation

- **Python Requirements**: Python 3.8 or higher
- **Installing Dependencies**:

```bash
# Clone the repository
git clone https://github.com/yourusername/NBAGameInsight.git
cd NBAGameInsight

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Basic Configuration

1. **Copy the configuration file template**:

```bash
cp .env.example .env
```

2. **Edit the configuration file**: Modify the configuration items in the `.env` file as needed:

```
# Required configuration
API_KEY=your_nba_api_key

# Optional configuration
WB_COOKIES=your_weibo_cookies  # For Weibo publishing functionality
AI_API_KEY=your_ai_api_key     # For AI analysis functionality
```

### Basic Usage Examples

#### View Game Information

```bash
# Get information about the Lakers' most recent game
python main.py --team Lakers --mode info
```

#### Generate Shot Charts

```bash
# Generate LeBron James' shot chart from the most recent game
python main.py --team Lakers --player "LeBron James" --mode chart
```

#### Process Video Highlights

```bash
# Generate highlights video for the Warriors' most recent game
python main.py --team Warriors --mode video-team

# Generate highlights video for Stephen Curry's most recent game
python main.py --team Warriors --player "Stephen Curry" --mode video-player
```

#### Publish to Weibo

```bash
# Publish Kevin Durant's most recent game highlights video to Weibo
python main.py --team Suns --player "Kevin Durant" --mode weibo-player
```

#### AI Game Analysis

```bash
# Perform AI analysis on Durant's most recent game
python main.py --team Suns --player "Kevin Durant" --mode ai
```

#### Update Season Data

```bash
# Update data for the 2025-26 season
python main.py --mode new_season --new-season "2025-26"
```

### Command Line Parameters

```
Parameter       Description                            Default
--team          Specify team                           Lakers
--player        Specify player                         LeBron James
--date          Specify date (YYYY-MM-DD or "last")    last
--mode          Running mode                           all
--no-weibo      Don't publish to Weibo                 False
--debug         Enable debug mode                      False
--config        Specify configuration file path        
--new-season    Specify new season identifier          
```

Available running modes:
- `info`: Display game information only
- `chart`: Generate charts only
- `video`: Process all videos
- `video-team`: Process team videos only
- `video-player`: Process player videos only
- `video-rounds`: Process player video round GIFs
- `weibo`: Execute all Weibo publishing functions
- `weibo-team`: Publish team highlight videos only
- `weibo-player`: Publish player highlight videos only
- `weibo-chart`: Publish player shot charts only
- `weibo-team-chart`: Publish team shot charts only
- `weibo-round`: Publish player round commentary and GIFs only
- `ai`: Run AI analysis only
- `all`: Execute all functions (default)
- `new_season`: Synchronize and update database for new season

## 💻 Programmatic Usage Example

In addition to the command line tool, you can use the library directly in your Python programs:

```python
from nba.services.nba_service import NBAService, NBAServiceConfig

# Create configuration
config = NBAServiceConfig(
    default_team="Lakers",
    default_player="LeBron James",
    date_str="last"
)

# Use context manager to ensure resources are properly closed
with NBAService(config=config) as nba_service:
    # Get basic game information
    game = nba_service.data_service.get_game("Lakers")
    if game:
        print(f"Game ID: {game.game_data.game_id}")
        print(f"Home Team: {game.game_data.home_team.team_city} {game.game_data.home_team.team_name}")
        print(f"Away Team: {game.game_data.away_team.team_city} {game.game_data.away_team.team_name}")
        
    # Generate player shot charts
    chart_paths = nba_service.generate_shot_charts(
        player_name="LeBron James",
        chart_type="both",
        shot_outcome="made_only"
    )
    
    # Get player highlight videos
    player_videos = nba_service.get_player_highlights(
        player_name="LeBron James",
        merge=True
    )
    
    # Execute AI analysis
    game_ai_data = game.prepare_ai_data()
    print(f"Analysis data contains {len(game_ai_data.get('events', {}).get('data', []))} events")
```

## 📁 Project Structure

```
NBAGameInsight/
├── nba/                 # Core functional modules
│   ├── database/        # Database module
│   ├── fetcher/         # Data retrieval module
│   ├── models/          # Data models
│   ├── parser/          # Data parsing module
│   └── services/        # Service modules
│       ├── nba_service.py         # Main service
│       ├── game_data_service.py   # Data service
│       ├── game_video_service.py  # Video service
│       └── game_charts_service.py # Chart service
├── weibo/               # Weibo integration module
│   ├── weibo_content_generator.py # Content generation
│   └── weibo_post_service.py      # Publishing service
├── utils/               # Utility modules
│   ├── ai_processor.py     # AI processing
│   ├── logger_handler.py   # Log handling
│   └── video_converter.py  # Video conversion
├── data/                # Data cache
├── storage/             # Media storage
│   ├── pictures/        # Chart storage
│   ├── videos/          # Video storage
│   └── gifs/            # GIF storage
├── main.py              # Main program entry
├── config.py            # Global configuration module    
├── requirements.txt     # Dependency list
└── README.md            # Project documentation
```

## 🔗 Practical Application Cases

- **Team Data Analysis**: Automatically generate data reports and video highlights for each team game
- **Player Data Tracking**: Track and analyze a specific player's performance and progress
- **Weibo Content Operations**: Provide automated content publishing solutions for NBA-related accounts
- **Data Visualization Display**: Generate professional shot distribution charts and impact analysis charts

## 🤝 Contributing

Contributions of any form are welcome, including but not limited to:

- Submitting bug reports
- Suggesting new features
- Contributing code (e.g., adding new data sources, parsers, visualization features, etc.)
- Improving documentation

Before submitting a Pull Request, please ensure that your code style complies with PEP 8 standards and add necessary unit tests.

## 📝 License

This project is open-source under the MIT License. For details, please see the [LICENSE](LICENSE) file.

## 📧 Contact

If you have any questions or suggestions, please feel free to contact us through GitHub Issues or Email.

---

**Thank you for your attention and support!**