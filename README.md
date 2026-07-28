# honor-of-kings-companion-api

抓取「王者营地」App（`com.tencent.gamehelper.smoba`，王者荣耀官方伴侣应用）里
**工具箱**模块三个榜单的采集脚本：

- 英雄热度榜（热度 / 胜率 / 登场率 / Ban率，按段位+分路筛选）
- 巅峰榜（王者战力排行榜）
- 荣耀榜（按英雄 + 省/市/区县查看称号积分排名）

这三个榜单在王者荣耀官网、KPL 赛事官网等公开渠道都查不到，只存在于 App 内部，
本仓库记录了通过 HTTPS 抓包逆向出来的接口结构，并提供可直接跑的采集脚本。

> **仅供个人技术研究与自己账号的数据分析使用。**
> 接口的认证信息（token / roleId 等）与你自己登录的游戏账号绑定，
> 不是公开匿名接口。请遵守游戏官方的用户协议，不要用于大规模爬取、
> 转卖数据或任何形式的滥用；作者不对使用本项目产生的任何后果负责。

## 目录结构

```
honor-of-kings-companion-api/
├── collectors/
│   ├── client.py       # 英雄热度榜/荣耀榜共用的请求客户端（限流+错误识别）
│   ├── hero_rank.py     # 英雄热度榜采集脚本
│   ├── honor_rank.py    # 荣耀榜采集脚本
│   └── peak_rank.py     # 巅峰榜采集脚本
├── data/
│   ├── heroes.json                 # 英雄ID/英雄名对照表（131个英雄，纯公开游戏数据）
│   ├── regions.json                # 省/市/区县三级行政区码树（3246个节点）
│   └── peak_headers.example.json   # 巅峰榜请求头模板
├── docs/
│   └── api_reference.md   # 三个接口的详细请求/响应字段说明
├── config.example.json    # 英雄热度榜/荣耀榜的认证信息模板
└── requirements.txt
```

## 快速开始

```bash
pip install -r requirements.txt
cp config.example.json config.json   # 按下文说明填入你自己的认证信息
```

### 英雄热度榜

```bash
# 抓「所有段位 + 全部分路」一组
python -m collectors.hero_rank --config config.json --segment 1 --position 0 --out out/hero.csv

# 抓全部 4 段位 x 6 分路 = 24 组合
python -m collectors.hero_rank --config config.json --segment all --position all --out out/hero_all.csv
```

### 荣耀榜

```bash
# 全部英雄 x 省级颗粒度（131 x 34 = 4454 次请求）
python -m collectors.honor_rank --config config.json --hero-ids all --region-level province --out out/honor_province.csv

# 指定英雄 + 指定地区
python -m collectors.honor_rank --config config.json --hero-ids 118 --adcodes 510107 --out out/honor_one.json
```

### 巅峰榜

巅峰榜的认证机制和另外两个不一样（见下文「关于巅峰榜的限制」），需要单独一份请求头文件：

```bash
cp data/peak_headers.example.json peak_headers.json  # 填入抓包得到的真实请求头
python -m collectors.peak_rank --headers peak_headers.json --role-id <你的roleId> --page-start 1 --page-end 3 --out out/peak.csv
```

三个脚本的参数、字段含义、榜单维度取值范围，详见 [`docs/api_reference.md`](docs/api_reference.md)。

## 如何获取自己的认证信息

这些接口需要你自己登录游戏账号后的会话信息，拿不到别人的，也不应该去拿。获取方式是给自己的
设备做一次 HTTPS 抓包：

1. **准备环境**：一台 Android 设备（真机或模拟器）+ 已安装「王者营地」并登录 + [WireGuard](https://www.wireguard.com/) App。
   用系统级 HTTP 代理设置（`设置 -> 代理`）不够，实测王者营地部分请求会绕过 Android 的应用层代理，
   直连服务器，必须用 WireGuard 这种网络层 VPN 才能完整截获。
2. **电脑上装 mitmproxy**，用 WireGuard 模式启动并关闭 HTTP/2（部分接口的响应头会被 h2 的严格校验判定非法而丢包）：
   ```bash
   pip install mitmproxy
   mitmdump --mode wireguard -w flows.dump --no-http2
   ```
   首次启动会在 `~/.mitmproxy/wireguard.conf` 生成一对 WireGuard 密钥，同时终端会打印出可以直接扫码/
   导入的客户端配置内容。
3. **设备接入这个 WireGuard 节点**：把打印出来的配置内容存成 `.conf` 文件导入 WireGuard App，连接。
   连接成功后设备的所有流量（不只是 HTTP 代理能截到的那部分）都会经过你的电脑。
4. **信任 mitmproxy 的证书**：访问 `mitm.it` 下载并安装 CA 证书。这一步在国产手机/模拟器上经常需要把证书
   装成"系统级信任"而不是"用户级信任"才能被 App 认可（King ID证书校验的常见坑），做法因设备而异，
   模拟器一般需要 root 权限把证书塞进 `/system/etc/security/cacerts/`。
5. **在 App 里操作对应榜单**：打开工具箱，依次点开英雄热度榜/巅峰榜/荣耀榜，切换几个筛选项，
   让 mitmproxy 把请求记下来。
6. **从抓包里挑出对应请求，把请求头字段抄进配置文件**：
   - 英雄热度榜 / 荣耀榜：抄进 `config.json`，字段列表见 `config.example.json`。这些字段在同一次
     登录会话里基本不变，抓一次就能用较长一段时间（token 过期需要重新抓）。
   - 巅峰榜：抄进 `peak_headers.json`，字段列表见 `data/peak_headers.example.json`。这份请求头里带
     签名字段 `sig`，有效期未知，谨慎复用。

如果你更熟悉用 mitmweb（`mitmproxy` 自带的网页版界面）而不是命令行，直接用它过滤 `kohcamp.qq.com`
找请求也是一样的。

## 关于巅峰榜的限制

巅峰榜（`getpeakranklist`）走的是嵌在 App 里的 H5 页面签名认证，请求头里的 `sig` 大概率是
"时间戳 + 参数 + 客户端内置密钥"算出来的，算法没有逆向。这意味着：

- 不能像另外两个榜单一样，靠一份配置自由拼参数组合去自动生成一堆合法请求；
- 只能原样复用一次抓包拿到的请求头，跑脚本自带的字段变化（翻页等），如果服务端认为改动的字段
  在签名范围内，会直接报错，此时需要回去重新抓包。

如果你需要更完整的巅峰榜数据（比如更多 `branchType`/`areaType` 取值、更深的分页），目前唯一可靠的
路子是在 App 里手动多操作几次、多抓几份请求头，而不是指望程序化穷举。

## 关于全量采集

三个榜单的数据体量差异很大：

| 榜单 | 维度组合数 | 数据量级 |
|---|---|---|
| 英雄热度榜 | 4 段位 x 6 分路 = 24 | 约 2MB，几秒抓完 |
| 荣耀榜 | 131 英雄 x 3246 地区(省+市+区县) ≈ 42.5 万 | 约 10~15GB |
| 巅峰榜 | 未知（分页深度/筛选取值范围未摸清） | 未知 |

荣耀榜如果真的按"全部英雄 x 全部地区"跑一遍，请求量比另外两个大出好几个数量级，用的又是你自己
账号的会话，高频调用很容易触发风控或者把 token 打挂。`collectors/honor_rank.py` 默认设置了组合数
阈值（超过 5000 组合必须加 `--confirm-full` 才会真正执行），并且默认限流（每次请求间隔 0.6s），
建议按需用 `--hero-ids`/`--region-level`/`--adcodes` 缩小范围，而不是无脑全量拉取。

## License

MIT，见 [LICENSE](LICENSE)。
