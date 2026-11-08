# 安装与查询

## 环境检查和补装

从本技能根目录运行：

```powershell
python scripts/dependencies.py doctor
python scripts/dependencies.py install-missing
```

`doctor`不联网、不安装；只检查skill、CLI、媒体工具与凭证存在性。`install-missing`只补官方FlyAI技能/CLI和指定高德技能/依赖，不能代装交互式Ego、浏览器登录或收费服务。节点命令缺失时按输出先配置Node。技能安装完成后，下一个用户回合可自动发现；当前可直接读取其安装目录的SKILL。

FlyAI官方仓库为 `https://github.com/alibaba-flyai/flyai-skill`，子目录 `skills/flyai`。通过本机系统skill-installer的GitHub安装脚本安装，再安装 `@fly-ai/flyai-cli`。用户给过的 `flyai-skil` 少了最后一个l，不能据此搜索同名第三方包。

高德指定来源：

```powershell
npx.cmd --yes skills@1.7.6 add 'https://clawhub.ai/lbs-amap/skills/amap-lbs-skill' --agent codex --global --yes
```

需要Node依赖时，在已安装的高德skill目录运行 `npm install --ignore-scripts --omit=dev --no-audit --no-fund`。不要把依赖目录复制进本skill仓库。

配置复用 `FLYAI_API_KEY` 对应的FlyAI私有配置与 `AMAP_WEBSERVICE_KEY` 环境变量。Windows刚写入用户环境后，旧进程可按需从用户级环境读取，不要求用户重新提供已经配置的Key。配置新Key时避免终端回显和仓库文件；不要在文档、示例、URL、HTML或ZIP写入真实Key。

video-report、Ego缺失时通过已有安装机制或官方说明补齐；不从不明镜像下载。媒体工具优先使用video-report已配置的 `.venv`、`.tools` 或 `VIDEO_REPORT_FFMPEG`、`VIDEO_REPORT_FFPROBE`；中文字体由 `TRAVEL_FONT` 或本机微软雅黑/Noto CJK提供。

## FlyAI

先读已安装FlyAI的 `SKILL.md` 及所用命令对应的 `references/` 文件，不能猜schema。可用本技能包装器稳定保存JSON：

```powershell
python scripts/flyai_query.py --output <任务目录>/research/datong-hotels.json -- search-hotel --dest-name 大同 --poi-name 大同古城 --check-in-date 2027-02-06 --check-out-date 2027-02-08 --hotel-bed-types 双床房
python scripts/flyai_query.py --output <任务目录>/research/flight.json -- search-flight --origin 北京 --destination 大同 --dep-date 2027-02-06
```

第二条仅演示参数，不能把示例的北京或省内自驾城市替代用户实际的机票出发城市。用户要求机票却未提供出发城市时必须补问；先继续不依赖该信息的酒店与行程研究。CLI支持的搜索参数未包含儿童总价、库存或房间数量时，如实保留未确认项，必要时在飞猪订单详情页只读核对；查询不进入付款。

包装器保存 `query`、`response`、`checked_at`、`process_exit` 和 `transport_warning`。已获得 `status:0` 的服务JSON、随后Node进程异常退出时，保留有效响应并注明传输警告，不误报完全失败，也不把进程当作正常退出。无JSON或服务失败则报错；不要为了一个展示价重复重试。

向用户展示候选时遵守FlyAI要求：自然说明来自FlyAI/飞猪，返回图片在预订链接前展示，保留返回的 `systemMessage` 平台提示。不要把响应中的无关推广当成目标景点或出发日的报价。

## 高德

先读已安装 `amap-lbs-skill/SKILL.md` 的对应场景。按其约定发送不带个人数据的调用统计，再调用POI或路径API。不要依赖未经验证的“一键travelPlanner”输出代替真实路线；逐点搜索和驾车路径是可核对的入口。

```powershell
node <高德skill目录>/scripts/poi-search.js --keywords=广武国际滑雪场 --city=朔州
node <高德skill目录>/scripts/route-planning.js --type=driving --origin=113.295060,40.092531 --destination=113.188831,39.566465
```

坐标来自实际POI，使用高德坐标系；不得把WGS84坐标直接混入。需要原始JSON时可从Node脚本导入其 `index.js` 的 `searchPOI`、`drivingRoute`；输出字段和函数签名以已安装代码为准。串行查询间隔至少约1秒，遇QPS限制退避后只补失败项，保留成功结果。

地图图片使用Ego打开真实的高德路线查询页，确认起终点、途经点、交通模式和所选路线再截图，保留高德标识与可见路线信息。若官方静态图API有权限，也可使用其实际返回图片；请求Key不能进入素材来源URL或成片。静态路线、导航时间和截图均注明查询时刻，不能预测几个月后的春节堵车。

## 每日位置地图

每天的地图都应能回答“今天从哪里出发、依次去哪里、在哪里吃饭和住宿”。按实际日程标景点入口/停车点、正餐餐厅、住宿及转场方向；跨城日同样覆盖出发和抵达点。较密集的城市日可配局部放大图，但不能省略当天的整体位置关系。

优先保留真实高德查询图。点位与同名分店须逐个核对城市、区县、地址和高德坐标；依据实际路线记录车程/里程，避免在图上画直线却把它称作驾车路线。地点尚未选定时可标候选与待定，不虚构已订酒店或已核实的餐厅坐标。

需要更清楚的布局或真实地图无法取得时，可依据已核对的POI坐标及真实路线结果绘制原创位置示意，标注“位置示意，非真实导航图”、坐标来源、查询日期及必要比例说明。示意线仅表达顺序时注明“连线仅示顺序”；不要凭空摆点、描出不存在的道路或冒充高德页面截图。没有路线结果的转场写待查，不能把坐标间距离当实际行车距离。

地图素材登记当天日期/日序、点位名称与坐标来源、交通方式、路线结果路径和截图/示意文件。将地图放在相应日的行程和视频中，餐厅或住宿改变后同步更新点位和相关路段。

## 大众点评餐饮

网页查询与城市、登录核对按 [大众点评查询](dianping.md)。它提供当前页面的店铺、口味和消费线索；高德用于确认分店位置及就近路线。两者店名相似时核对地址再合并，不能用另一分店的评分或营业信息代填。无需新增大众点评API、导出Cookie或另配密钥。

## 报价截图

API JSON用于数值与条件依据，截图用于解释具体页面。先确认页面日期、城市、房型/航班与返回结果一致，再截图保留必要上下文；隐藏Cookie、账户电话、乘机人等无关个人内容。飞猪酒店按实际入住/离店日、房型与间数记录展示价，机票按实际出发城市、日期及成人/儿童条件记录；没有返回的税早、行李、退改或库存写未确认。只有JSON、没有报价页面时，可做注明“查询结果整理”的原创报价卡，不能冒充飞猪页面截图。
