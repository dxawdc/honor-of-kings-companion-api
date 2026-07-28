# 接口参考文档

本文档记录三个榜单接口的请求/响应结构，均通过对「王者营地」App
（`com.tencent.gamehelper.smoba`）的 HTTPS 流量抓包分析得出，仅供技术研究与个人数据分析使用。

> 这些都是私有接口，认证信息与你自己的登录会话绑定，不是公开 API。
> 抓包方法见根目录 README「如何获取自己的认证信息」一节。

---

## 1. 英雄热度榜 `hero/getdetailranklistbyid`

- **Host**: `kohcamp.qq.com`
- **Method**: `POST`
- **认证方式**: App 原生 token 认证（token / openId / gameOpenId / gameRoleId / encodeParam 等固定请求头）

### 请求体

```json
{"bottomTab": "", "rankId": 0, "segment": 1, "position": 0, "recommendPrivacy": 0}
```

| 字段 | 说明 |
|---|---|
| `segment` | 段位筛选，见下表 |
| `position` | 分路筛选，见下表 |
| `rankId` / `bottomTab` / `recommendPrivacy` | 目前只见过固定值 `0` / `""` / `0`，作用未知 |

`segment` 取值（对应 App 内的段位筛选 Tab，服务端在返回的 `data.filter.tabFilter` 里给出，
数组下标 0 和 2 是空字符串，实测这两个 segment 会返回空列表，怀疑是预留位）：

| segment | 含义 |
|---|---|
| 1 | 所有段位 |
| 3 | 巅峰赛1350+ |
| 4 | 顶端排位 |
| 5 | 赛事 |

`position` 取值（对应 `data.filter.branchFilter`）：

| position | 含义 |
|---|---|
| 0 | 全部分路 |
| 1 | 对抗路 |
| 2 | 中路 |
| 3 | 发育路 |
| 4 | 游走 |
| 5 | 打野 |

### 响应体（节选）

```json
{
  "returnCode": 0,
  "returnMsg": "",
  "data": {
    "filter": {"branchFilter": [...], "tabFilter": [...], "eventList": []},
    "updateTime": 0,
    "sortField": "tRank",
    "list": [
      {
        "heroId": 502,
        "banRate": "12.3%",
        "showRate": "8.1%",
        "winRate": "51.2%",
        "tRank": "T0",
        "heroInfo": {"heroId": 502, "heroName": "云中君", "heroIcon": "...", "heroCareer": "..."}
      }
    ]
  }
}
```

单次请求返回全部英雄（实测 131 个），不支持分页。

---

## 2. 巅峰榜 `game/getpeakranklist`

- **Host**: `kohcamp.qq.com`（注意：是同一个域名，但走的是嵌在 App 里的 H5 页面 `camp.qq.com` 发起的请求，
  认证方式和上面的原生接口完全不同）
- **Method**: `POST`
- **认证方式**: 签名认证 —— 请求头里带 `sig` / `msdkEncodeParam` / `msdkToken` / `timestamp` / `algorithm` /
  `encode`，`sig` 的计算算法未逆向，怀疑是「时间戳 + 客户端内置密钥」的摘要。**已通过实测确认：这个签名
  只跟"打开页面那一刻的会话"绑定，跟请求体里的 `branchType`/`areaType`/`rankDateType`/`page`/`pageSize`
  完全无关** —— 同一份抓包头改任意组合都能用，甚至脱离手机直接从别的机器发请求也能成功。所以只要抓一次
  包，就能拿这份 header 跑完全部组合，不需要每换一个筛选项都重新抓包。

### 请求体

```json
{"cSystem": "android", "h5Get": 1, "roleId": 589741227, "areaType": 3, "page": 1, "pageSize": 500, "branchType": 7, "rankDateType": 0}
```

| 字段 | 说明 |
|---|---|
| `areaType` | 区服，共 4 个值（实测穷举）：`1`=QQ安卓区 `2`=QQ苹果区 `3`=微信安卓区 `4`=微信苹果区 |
| `branchType` | 分路筛选，共 7 个值（实测穷举）：`1`=对抗路 `2`=中路 `3`=发育路 `4`=打野 `5`=游走 `6`=全能 `7`=总榜 |
| `rankDateType` | `0`=今日实时；非 0（试过 1/2/3/99，结果都一样）=昨日快照。本质是个二元开关，不是"任选某一天" |
| `page` / `pageSize` | `pageSize` 直传 `500` 即可一次拿到该组合下的全部数据；`pageSize` 超过 500（试过1000）会返回空列表 |

### 响应体（节选，注意这个接口没有 `returnCode`/`data` 包装，是扁平结构）

```json
{
  "rankList": [
    {
      "rankNo": 1,
      "rankScore": 2381,
      "nickname": "xxx",
      "gradeLevel": "至尊铜III",
      "areaId": "3",
      "sex": 2,
      "lastDayScore": 2359,
      "lastDayRank": 4,
      "branchType": 7,
      "isTopPlayer": true
    }
  ],
  "selfInfo": {...}
}
```

### 榜单深度

每个 `branchType` x `areaType` 组合下，榜单固定封顶 **500 名**（App 里划到底会提示"没有更多内容了~"，
实测第 26 页返回空列表验证过）。所以全量组合数是 `7(branchType) x 4(areaType) x 2(rankDateType) = 56`
次请求，每次用 `pageSize=500` 一把拿完，总计约 2.8 万条记录，量级和英雄热度榜接近，跟荣耀榜完全不是
一回事。

### 已知限制

- `sig` 具体的计算算法仍然没有逆向出来，只是确认了它的"签名范围"不包含请求体参数。
- 没有验证过这份 `sig`/`timestamp` 的有效期（TTL）多长——已知至少十几分钟内持续可用，如果隔了很久
  再用脚本报"认证失败"，回 App 里重新打开一次巅峰榜页面、重新抓一份 header 即可，不需要重新摸索接口。
- App UI 里没有找到能调 `rankDateType` 的入口（没有"昨日/历史"切换按钮），这个值目前只能靠脚本直接
  传参数验证，不是从界面点出来的。

---

## 3. 荣耀榜 `game/honor/ranklist` + `game/honor/districts`

- **Host**: `kohcamp.qq.com`
- **Method**: `POST`
- **认证方式**: 和英雄热度榜一样的 App 原生 token 认证

### 3.1 地区树 `game/honor/districts`

```json
{"recommendPrivacy": 0, "areaId": 3, "heroId": 118}
```

`heroId` 传哪个英雄好像不影响地区树内容，随便传一个有效值即可。

响应是三级行政区划树（省 → 市 → 区县），已经离线整理进 `data/regions.json`
（34 省级 / 472 市级 / 2740 区县级，共 3246 个节点），正常使用不需要再调用这个接口。

每个节点结构：

```json
{"adcode": 510107, "shortName": "武侯区", "fullName": "成都市武侯区", "lowestRankScore": 0, "list": [...子级...]}
```

### 3.2 排行榜 `game/honor/ranklist`

```json
{"recommendPrivacy": 0, "areaId": 3, "adcode": 510107, "roleId": "589741227", "heroId": 118}
```

| 字段 | 说明 |
|---|---|
| `areaId` | 大区，固定值（同 `honor/districts`），来自你抓包时的 `gameAreaId` |
| `adcode` | 地区码，可以是省级(3位)/市级(4位)/区县级(6位)，见 `data/regions.json` |
| `heroId` | 英雄ID，见 `data/heroes.json` |
| `roleId` | 你自己的角色ID，只是用来让服务端识别请求者，不影响返回的排行榜内容 |

响应：

```json
{
  "returnCode": 0,
  "data": {
    "list": [
      {"rankNo": 1, "roleId": "xxx", "nickname": "xxx", "roleJobName": "荣耀王者I", "rankValue": "10721", "rankChange": "0"}
    ],
    "total": 100,
    "updateTime": 1785150363
  }
}
```

固定最多返回 100 条，不支持分页；地区人数不足 100 时返回条数会更少。

### 3.3 全量体量

`131 英雄 × 3246 地区节点 ≈ 42.5 万次请求`，单次响应约 35~38KB，全量估算总数据量在
10~15GB 量级。这个量级不建议真的跑一遍，详见根目录 README「关于全量采集」一节。
