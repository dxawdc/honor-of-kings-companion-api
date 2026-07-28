"""
巅峰榜采集脚本（对应 App 内「工具箱 - 巅峰榜」，实为嵌在 App 里的 H5 页面 camp.qq.com 调用的接口）。

接口：POST https://kohcamp.qq.com/game/getpeakranklist
请求体：{"cSystem":"android","h5Get":1,"roleId":<你的roleId>,"areaType":<大区>,
        "page":<页码>,"pageSize":20,"branchType":<分路/职业>,"rankDateType":0}

** 重要限制，请务必先读完再用 **
这个接口和另外两个榜单不一样：另外两个走的是 App 原生的 token/encodeParam 认证，
在同一次登录会话里基本是固定不变的；巅峰榜走的是网页版签名认证，请求头里带一个
`sig`（外加 msdkEncodeParam / msdkToken / timestamp / encode / algorithm 等字段），
这个 `sig` 大概率是"时间戳 + 请求参数 + 客户端内置密钥"算出来的签名，算法没有逆向，
所以本脚本**不能像另外两个脚本那样自由拼各种参数组合再自动算出合法签名**。

本脚本的能力边界：
  - 把一次完整抓包里 kohcamp.qq.com/game/getpeakranklist 请求的全部请求头原样保存到
    peak_headers.json（参考 data/peak_headers.example.json），脚本原样复用这些请求头，
    只改请求体里的 page / branchType / areaType / rankDateType / pageSize。
  - 如果 sig 校验的范围包含了这些会变化的字段，服务端会直接拒绝——脚本检测到返回内容
    不是预期结构时会立刻停止并报错，不会无意义地把所有组合都跑一遍。
  - 已确认的 branchType 取值只有 1、7 两个（抓包样本有限，其余取值未知，需要你自己
    在 App 里多点几个筛选项、重新抓包补全 data/peak_headers.example.json 边上的说明）。
  - 如果这个脚本报"认证失败"，说明 sig 确实和你改的字段绑定了，此时只能老老实实
    在 App 里点一次筛选、重新抓包拿一份新的请求头，一份头对应一次查询。

用法示例：
  # 用同一份 headers，只翻页（如果 sig 不校验 page，翻页能成功）
  python -m collectors.peak_rank --headers peak_headers.json --page-start 1 --page-end 5 --out out/peak.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import requests

URL = "https://kohcamp.qq.com/game/getpeakranklist"

CSV_FIELDS = [
    "rankNo", "nickname", "rankScore", "gradeLevel", "areaId", "areaName",
    "sex", "lastDayScore", "lastDayRank", "branchType", "page",
]


class PeakAuthError(RuntimeError):
    pass


def load_headers(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_page(headers: dict, base_body: dict, page: int, timeout: float = 10.0) -> dict:
    body = dict(base_body)
    body["page"] = page
    resp = requests.post(URL, headers=headers, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=timeout)
    if resp.status_code != 200:
        raise PeakAuthError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "rankList" not in data:
        raise PeakAuthError(f"返回内容不含 rankList，很可能是 sig 校验失败，原始返回：{json.dumps(data, ensure_ascii=False)[:300]}")
    return data


def flatten(data: dict, page: int) -> list[dict]:
    rows = []
    for item in data.get("rankList", []):
        rows.append(
            {
                "rankNo": item.get("rankNo"),
                "nickname": item.get("nickname"),
                "rankScore": item.get("rankScore"),
                "gradeLevel": item.get("gradeLevel"),
                "areaId": item.get("areaId"),
                "areaName": item.get("areaName"),
                "sex": item.get("sex"),
                "lastDayScore": item.get("lastDayScore"),
                "lastDayRank": item.get("lastDayRank"),
                "branchType": item.get("branchType"),
                "page": page,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="巅峰榜采集（受限于未逆向的签名机制，见文件头说明）")
    ap.add_argument("--headers", default="peak_headers.json", help="完整抓包请求头 JSON 文件路径")
    ap.add_argument("--branch-type", type=int, default=7)
    ap.add_argument("--area-type", type=int, default=3)
    ap.add_argument("--rank-date-type", type=int, default=0)
    ap.add_argument("--page-size", type=int, default=20)
    ap.add_argument("--page-start", type=int, default=1)
    ap.add_argument("--page-end", type=int, default=1)
    ap.add_argument("--role-id", type=int, required=True, help="你自己的 roleId（对应抓包里 body 的 roleId）")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    headers = load_headers(args.headers)
    base_body = {
        "cSystem": "android",
        "h5Get": 1,
        "roleId": args.role_id,
        "areaType": args.area_type,
        "pageSize": args.page_size,
        "branchType": args.branch_type,
        "rankDateType": args.rank_date_type,
    }

    all_rows: list[dict] = []
    for page in range(args.page_start, args.page_end + 1):
        print(f"抓取 page={page} ...")
        try:
            data = fetch_page(headers, base_body, page)
        except PeakAuthError as e:
            print(f"停止：{e}")
            break
        rows = flatten(data, page)
        print(f"  -> {len(rows)} 条")
        if not rows:
            print("本页没有数据，认为已到榜单末尾，停止翻页")
            break
        all_rows.extend(rows)
        time.sleep(args.delay)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".csv":
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, ensure_ascii=False, indent=2)

    print(f"完成，共 {len(all_rows)} 条，已写入 {out_path}")


if __name__ == "__main__":
    main()
