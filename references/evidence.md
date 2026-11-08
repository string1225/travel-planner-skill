# 研究记录格式

`sources.json` 与 `quotes.json` 都是数组；没有报价时使用空数组，而不是为画面编造报价。

来源字段：`id`、`title`、`author`、`url`、`captured_at`（或 `checked_at`），日期使用ISO日期或时间。`published_at` 不可见时为null。`status` 为 `reference`、`verified_text`、`linked_only`、`captured`、`blocked` 或 `original`；`captured` 必须另有存在的本地 `asset_path` 或 `evidence_path`。链接参考或受阻材料不能宣称 `included_in_video:true`。原创规划的 `platform: original` 或 `verification: planning_assumption` 可无URL。

报价例子：

```json
[
  {
    "id": "Q1", "kind": "hotel", "provider": "FlyAI/飞猪",
    "checked_at": "2026-11-08T16:00:00+08:00",
    "query": {"dest_name":"大同","check_in_date":"2027-02-06","check_out_date":"2027-02-08"},
    "price": "597", "currency": "CNY", "unit": "room/night",
    "claim": "display", "unconfirmed": ["两间房库存","儿童早餐","退改与最终税费"],
    "response_path": "research/datong-hotels.json"
  }
]
```

这是字段示意，不是当前旅行的报价承诺。`kind` 支持flight、hotel、train、ticket、package；`query` 使用任务记录的规范字段：航班/火车需origin、destination、dep_date，酒店需dest_name、check_in_date、check_out_date，门票需visit_date，组合产品需travel_date。查询CLI的连字符参数在此转为下划线，仅用于研究清单，不反传CLI。

`claim` 默认为 `display`；不含旅行日期的一般促销信息标 `generic`，不能用于确定日程的预算报价；无可用结果标 `unavailable`。需要显示的价格必须有currency与unit。仅在供应商确实提供保留/锁价依据时才可标 `locked`，并提供 `lock_evidence`（本地依据文件或供应商公开链接）和 `expires_at`；一般搜索响应不能充当锁价证明。校验器能查字段与文件，不能验证供应商是否真的保留库存，Agent仍须核对内容。

```powershell
python scripts/evidence.py validate <任务目录>
```

所有相对文件路径以任务目录为根。不得在URL或任何嵌套字段保存Cookie、CSRF、API Key等凭证。浏览器与原始查询记录保存时先去除敏感内容，公开交付包仅包含必要材料。
