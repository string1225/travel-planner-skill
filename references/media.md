# 素材清单与混合视频

## 先制作基础片

读取已安装video-report的SKILL与制作SOP，创建任务 `report.json`、来源与分镜。用其 `video_report.py validate/build/check` 生成旁白、逐句字幕、累计帧时间轴、原始场景PNG和基础视频。先验证样片再全片；需要已有旅行专用布局时在任务runtime内修改，不改全局模板或其他用户项目。

本技能使用该输出目录的 `report.json`、`timeline.json`、`captions.json`、`subtitles.ass`、`voice.wav` 与 `frames/`。当前混合工具支持1920×1080；保留原时间轴整数fps和累计帧边界，不按每场景独立四舍五入。

## 媒体清单

`report_dir`、`asset_path` 相对清单所在目录解析，也可为绝对路径。每个场景最多一个图片或视频；未列出的场景保留原始场景PNG。多图对比可先在本地排成一张图，或在写稿时拆成不同场景。示意：

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

URL应改为实际景点来源的规范公开链接；示例主页不证明某段素材来源。`source` 必填平台、作者、标题、获取日期；外部素材另填原文URL。`usage.basis` 为 `permission`、`license` 或 `quotation`，前两者填 `evidence`，引用填具体 `purpose`。原创素材设平台和依据均为 `original`。工具只核对声明字段，不能替代对材料是否适当使用的判断。

视频必须明确起止秒，实际可用长度不能超出原片。短于旁白场景时优先缩短稿件、拆场景或换足够长的素材；确需停留末帧，才设置 `hold_last_frame:true`，工具会在来源标签提示。不会自动循环原视频或补出新镜头。内容区等比缩放并留白，禁止为铺满而裁掉署名。

来源URL不能携带API Key、会话或CSRF参数。保留规范公开链接；登录结果页的敏感查询串不进入清单或输出。

## 构建与检查

```powershell
python scripts/assemble.py validate <任务目录>/media-manifest.json
python scripts/assemble.py build <任务目录>/media-manifest.json --output <任务目录>/output/mixed
```

通过环境 `VIDEO_REPORT_FFMPEG`、`VIDEO_REPORT_FFPROBE` 和 `TRAVEL_FONT` 可指定已有工具。默认尝试video-report工具目录与本机CJK字体。输出必须与基础目录不同；已存在成片默认拒绝覆盖，修订同一输出时显式 `--overwrite`。

混合输出为 `video.mp4`、`deck/index.html`、`media/`、`media-manifest.json`、原配音/字幕/时间轴及 `mixed-qa.json`；`work/` 是可再生编码中间文件，不必交付。媒体目录的视频只包含实际使用片段、没有原音，原始参考文件留在研究目录。清单以自身为 `report_dir`，保留原始场景所需PNG，可在原基础目录不可用时重建；原片引用起止时间保存在 `source.original_clip_start/end`，再裁片会累计偏移。编辑素材清单、源图片、片段和报告后重建视频；HTML里的修改只影响预览。移动交付时保留deck、media、frames、配音等相对目录。

全片解码、画幅、帧数和音轨通过后，逐类抽帧看实际素材、水印/作者、地图标识、报价日期与完整句字幕。截图内容太密就重新取材或分场景，不用缩小字幕补救。打开HTML验证播放、暂停、进度拖动及视频与旁白同步；无法抽听就记未抽听。

视频总成本应合并基础制作 `costs.json`、混合编码 `mixed-qa.json` 的实测时间及可获得的查询/平台账单；没有账单的模型、Key服务、Ego和电费保持未知。新增媒体拼合只在本机运行FFmpeg，不代表整趟任务免费。

发布继续走video-report维护入口，但 `videoPath` 必须换成已核验的 **mixed/video.mp4**。混合片的创作声明按实际引用和授权重新核对，不能继承只覆盖早期全原创示意片的权利确认。
