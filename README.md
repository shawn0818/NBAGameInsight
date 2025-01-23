# lebron_bot
本项目旨在提供：
高效、可靠的NBA数据获取和处理解决方案，支持比赛数据、球员数据、赛程等信息的自动化获取；
自动发布NBA数据至微博等社交平台；


未来计划将项目重构为四层架构：

1. **数据获取层 (Fetchers)**
   ```python
   class GameFetcher:
       def get_boxscore(self, game_id: str) -> Optional[Dict]:
           # 专注于数据获取
           return self._fetch_game_data('boxscore', game_id)
   ```

2. **数据转换层 (Transformers)**
   ```python
   class BoxScoreTransformer:
       def to_dataframe(self) -> DataFrame:
           # 转换为DataFrame格式
           pass
       
       def to_dict(self) -> Dict:
           # 转换为字典格式
           pass
   ```

3. **数据模型层 (Models)**
   ```python
   @dataclass
   class BoxScore:
       game_id: str
       home_team_score: int
       away_team_score: int
       # 更多字段定义
   ```

4. **业务服务层 (Services)**
   ```python
   class GameDataService:
       def get_team_game_stats(self, game_id: str, output_format: str = 'dataframe'):
           # 统一的数据访问接口
           data = self.fetcher.get_boxscore(game_id)
           return self.transformer.transform(data, output_format)
   ```

## 架构优势

1. **清晰的职责分离**
   - 每一层都有明确的职责
   - 代码组织更加清晰
   - 易于维护和测试

2. **灵活的数据格式**
   - 支持多种输出格式（DataFrame、Dict、Model）
   - 便于适应不同的使用场景
   - 转换逻辑集中管理

3. **强类型支持**
   - 使用dataclass定义数据结构
   - 提供完整的类型提示
   - 支持IDE智能提示

4. **出色的可扩展性**
   - 易于添加新的数据模型
   - 易于添加新的转换方法
   - 易于添加新的输出格式

## 待实现功能

### Phase 1: 基础功能（当前阶段）
- [✅] 实现核心数据获取功能
- [✅] 添加基础缓存机制
- [✅] 实现错误处理和日志记录

### Phase 2: 数据结构优化
- [❌] 实现数据模型层
- [❌] 添加数据验证机制
- [❌] 实现批量数据处理

### Phase 3: 性能优化
- [❌] 添加异步支持
- [❌] 优化缓存策略
- [❌] 实现性能监控

## 使用示例

```python
# 当前用法
with GameFetcher() as game:
    box_score = game.get_boxscore("0022300001")

# 重构后的用法
service = GameDataService()

# 获取不同格式的数据
df = service.get_team_game_stats("0022300001", output_format="dataframe")
box_score = service.get_team_game_stats("0022300001", output_format="model")

# 使用模型对象
print(f"Home Team Score: {box_score.home_team_score}")
```