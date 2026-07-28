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
  `encode`，`sig` 的计算算法未逆向，怀疑是「时间戳 + 请求参数 + 客户端内置密钥」的摘要。

### 请求体

```json
{"cSystem": "android", "h5Get": 1, "roleId": 589741227, "areaType": 3, "page": 1, "pageSize": 20, "branchType": 7, "rankDateType": 0}
```

| 字段 | 说明 |
|---|---|
| `areaType` | 大区，实测样本里只见过 `3` |
| `branchType` | 分路/职业筛选，实测样本只见过 `1` 和 `7`，完整取值范围未知 |
| `rankDateType` | 榜单时间维度，实测样本只见过 `0`（大概率 0=今日，1=昨日之类，未验证） |
| `page` / `pageSize` | 分页，`pageSize` 实测为 20，最大页数未知（没抓到翻页到底的请求） |

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

### 已知限制

- `sig` 是否包含 `page`/`branchType`/`areaType` 在签名范围内没有验证过，如果包含，
  改这些字段重新发请求会直接被判定签名无效。
- 没有抓到过 `page > 1` 或翻到底的请求，所以榜单总深度（比如是不是固定只展示前 100/500/5000 名）未知。

如果你需要更完整的巅峰榜数据，建议的路子是：在 App 里手动多点几次筛选/翻页，
用 mitmproxy 把这些请求都存下来，再用 `collectors/peak_rank.py` 里同样的思路挨个复现，
而不是指望脚本自动穷举所有组合。

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
