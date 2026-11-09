# 素材与动态成片

## 优先使用原生媒体与动效

先读取已安装video-report的 `SKILL.md`、制作SOP、`references/media-and-motion.md` 和 `references/timing-and-captions.md`。新版已有 `report.media`、`scene.media`、`motion` 和 `voice.speed`：优先在同一原生流程制作HTML、旁白、完整句字幕和逐帧MP4，不再先导出动态片再按单张场景PNG重拼。

每份素材先实际保存到任务 `assets/` 并核对内容、尺寸和来源。顶层 `report.media` 按video-report当前schema登记 `id/type/path/title/source_url/creator/license/attribution`；`path` 相对 `report.json`，保留许可/使用依据、原始来源、裁剪及视频起止时间，建议记录文件摘要。使用依据按实际填写，不能将引用标注写成已获得转载许可。远端链接、搜索缩略图或下载失败不算已取得的本地素材。

用 `scene.media` 选择登记的素材ID、caption和fit。地图、报价、平台截图与图表使用 `contain` 保留完整信息；水印、作者、日期及地图标识不能因铺满画面而裁掉。同页需要换图时使用 `scene.media.switches`，按整句字幕cue及偏移切换；无需为了旧工具的“一场景一素材”限制把原生流程退化为静态页。视频先按实际范围裁剪并去原音，HTML格式优先使用video-report建议的WebM；保留原片起止映射与改动记录。

设置 `motion.enabled: true`，按 `scene.reveal_cues` 将安排或景点要点绑定到对应整句字幕。每日可先讲位置图，再切餐厅、住宿或景点截图，配合卡片显现、照片轻缓推近等已支持动效；不能凭空声称地图道路或点位已实现自定义动画。需要分段路线展示时，可根据真实路线制作不同阶段图并用素材切换呈现。视频默认片尾停住；只有明确适合且检查过循环接点时才使用 `loop: true`。

优先使用现有版式。确需定制时在任务隔离的video-report副本内修改模板并用同副本构建，保留脚本与模板版本；不改全局模板或其他用户项目。只编辑生成的HTML不会回写MP4，重建也可能覆盖输出HTML；报告、源素材与实际模板才是可再导出的源。

## 每日画面与精简配音

视频主体讲每日具体安排、景点特点与为何这样走。每天有能辨认景点、餐饮、住宿和当日转场的真实高德地图或有依据的位置示意，规范见 [每日位置地图](services.md)。大众点评、飞猪、小红书和B站截图放在其支持的餐次、住宿或景点段落；截图太密就取必要区域或拆页，不用缩小字幕补救。儿童信息仅在实际影响票务或安排时提及；必要交通、预约与营业限制在对应段简述。

先删除重复描述和冗长提醒，保留完整句，再按用户要求调速。`voice.rate` 是现有TTS基准，`voice.speed` 是此基础上的保音高倍率。例如用户要求“比当前快1.25倍”时，保留原 `rate` 并设 `speed: 1.25`；1.2等其他倍率同理，具体以用户请求为准。没有确切倍率时可为本次样片自主选择清楚可懂的稍快值，试听后决定，不硬编码为以后任务的默认。

只改speed可复用原合成缓存；改稿后重做受影响配音。运行video-report重建时间轴和字幕，最终时长仍以处理后的实际PCM采样数计算；不手改字幕时间来追赶加速音频，也不在未知边界按字数截断句子。

## 原生构建与检查

按video-report实际脚本路径运行：

```powershell
python <video-report目录>/scripts/video_report.py validate <任务目录>/report.json
python <video-report目录>/scripts/video_report.py build <任务目录>/report.json --output <任务目录>/output/report
python <video-report目录>/scripts/video_report.py check <任务目录>/output/report
```

使用已配置的venv与FFmpeg，先短样片再全片。保留 `media-sources.json`、`deck/MEDIA-CREDITS.md`、时间轴、旁白、字幕及QA。检查 `motion-qa.json` 和完整解码结果之外，还要实际看同页至少两个时刻、动效中间态、短片运动、素材切换、片尾停帧及拖动回退，核对地图点位、报价日期、水印/作者、比例与完整句字幕，抽听加速后的可懂度及跨页。不能用video元素存在、音轨存在或只有联系表来代替动态验收；未做的视觉/抽听检查分别记录。

## 兼容分支：旧环境的assemble

只有所用video-report环境缺少原生媒体能力、或需要重建已有旧格式交付时才使用本节。`assemble.py` 使用每场景PNG回退，不能保留当前原生HTML的逐帧动效、reveal或素材切换；不要把已有原生动态片送入此分支后声称动效保持。需要动态画面的任务优先使用已具备能力的video-report，兼容环境的剩余缺口如实交接。

旧流程先用对应版本video-report构建基础输出，再使用其 `report.json`、`timeline.json`、`captions.json`、`subtitles.ass`、`voice.wav` 与 `frames/`。混合工具支持1920×1080，保留原整数fps和累计帧边界，不按场景独立四舍五入。基础目录保留，兼容成片输出到不同目录。

`media-manifest.json` 的 `report_dir`、`asset_path` 相对清单所在目录解析，也可为绝对路径。**此兼容清单**每场景最多一张图片或一个视频，未列场景保留原始PNG；多图可先排为一图或拆场景。它不是原生 `report.media` 的替代schema。示意：

```json
{
  "schema_version": 1,
  "report_dir": "output/base",
  "media": [
    {
      "scene_id": "route", "kind": "image", "asset_path": "assets/amap-route.png",
      "source": {"platform":"amap","author":"高德地图","title":"实际起终点的驾车路线","url":"https://www.amap.com/","captured_at":"2026-11-08T16:00:00+08:00"},
      "usage": {"basis":"quotation","purpose":"解释本路线的实际转场与里程"}
    },
    {
      "scene_id": "spot", "kind": "video", "asset_path": "assets/authorized-spot.mp4",
      "clip_start": 12.0, "clip_end": 30.0,
      "source": {"platform":"bilibili","author":"实际作者","title":"实际视频标题","url":"https://www.bilibili.com/","captured_at":"2026-11-08T16:05:00+08:00"},
      "usage": {"basis":"permission","evidence":"任务中保存的授权记录或许可条款路径"}
    }
  ]
}
```

URL改为实际来源的规范公开链接，示例主页不证明某段素材来源。`source` 必填平台、作者、标题、获取日期，外部素材另填原文URL。`usage.basis` 为 `permission`、`license` 或 `quotation`，前两者填 `evidence`，引用填具体 `purpose`；原创平台和依据均为 `original`。工具只核对声明字段，不替代使用范围判断。URL不得含API Key、会话或CSRF参数。

视频明确起止秒且不超原片。短于旁白场景时优先改稿、拆场景或换足够长素材；确需停留末帧才设 `hold_last_frame: true`，工具会加来源提示。兼容工具不会自动循环原视频或补镜头；内容等比缩放并留白。

```powershell
python scripts/assemble.py validate <任务目录>/media-manifest.json
python scripts/assemble.py build <任务目录>/media-manifest.json --output <任务目录>/output/mixed
```

复用 `VIDEO_REPORT_FFMPEG`、`VIDEO_REPORT_FFPROBE` 和 `TRAVEL_FONT` 或已配置的video-report工具。已有输出默认拒绝覆盖，修订同一输出时显式 `--overwrite`。交付 `video.mp4`、`deck/index.html`、`media/`、`media-manifest.json`、原配音/字幕/时间轴与 `mixed-qa.json`；`work/` 是可再生中间文件。视频只保留实际用段且无原音；原始研究文件另存。交付清单以自身为 `report_dir`，保留回退PNG；原片起止保存在 `source.original_clip_start/end`，再次裁片累计偏移。移动交付保留deck、media、frames及配音相对目录。

兼容流程也要全片解码、抽帧、抽听并检查HTML播放、暂停、拖动和同步；技术检查不能证明已完成动态验收。

## 交付与发布

成本合并video-report实际 `costs.json`、兼容流程实际 `mixed-qa.json` 的时间及可取得的查询/平台账单；没有账单的模型、Key服务、Ego或电费保持未知。是否调用本机FFmpeg不能证明整个任务免费。

明确要求发布时继续走video-report维护入口，`videoPath` 指向**本次实际通过QA的成片**：原生流程通常为 `output/report/video.mp4`，兼容流程为 `output/mixed/video.mp4`。内部核对截图、片段的使用依据和创作声明；用户已授权助手制作成片按自制处理时，沿用video-report保存的持续授权，不因新增地图、署名截图或剪辑版本重复询问。
