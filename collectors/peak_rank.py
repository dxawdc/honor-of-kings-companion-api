"""
巅峰榜采集脚本（对应 App 内「工具箱 - 巅峰榜」，实为嵌在 App 里的 H5 页面 camp.qq.com 调用的接口）。

接口：POST https://kohcamp.qq.com/game/getpeakranklist
请求体：{"cSystem":"android","h5Get":1,"roleId":<你的roleId>,"areaType":<区服>,
        "page":1,"pageSize":500,"branchType":<分路>,"rankDateType":<0或1>}

维度取值（实测穷举确认，见 docs/api_reference.md）：
  branchType（分路）: 1=对抗路 2=中路 3=发育路 4=打野 5=游走 6=全能 7=总榜
  areaType（区服）  : 1=QQ安卓区 2=QQ苹果区 3=微信安卓区 4=微信苹果区
  rankDateType      : 0=今日实时，非0=昨日快照（不是任选某天，只有这两种状态）

认证方式和另外两个榜单不一样，走的是网页版签名认证：请求头里带 sig / msdkEncodeParam /
msdkToken / timestamp / algorithm / encode，算法没有逆向。但经过实测：
  - 同一份抓包头，改 branchType / areaType / rankDateType / page / pageSize 都能正常返回数据；
  - pageSize 直接传 500 就能一次性拿到该组合下的全部数据（榜单本身封顶 500 条，pageSize>500 会返回空）；
  - 脱离手机、直接从任意机器用这份 header 发请求也能成功。
说明 sig 只跟"抓包那一刻的会话/时间戳"绑定，跟请求体内容无关。也就是说全量 7 x 4 x 2 = 56 次
请求可以用同一份抓包头一次性跑完，不需要每换一个筛选项就重新抓包。唯一没摸清的是这份 sig 的
有效期（TTL）有多长，如果间隔太久没用被拒绝，重新抓一次页面 URL 里的参数即可（见 README）。

用法示例：
  cp data/peak_headers.example.json peak_headers.json  # 填入一次抓包得到的真实请求头
  python -m collectors.peak_rank --headers peak_headers.json --role-id <你的roleId> --out out/peak_all.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import requests

URL = "https://kohcamp.qq.com/game/getpeakranklist"

BRANCH_TYPES = {1: "对抗路", 2: "中路", 3: "发育路", 4: "打野", 5: "游走", 6: "全能", 7: "总榜"}
AREA_TYPES = {1: "QQ安卓区", 2: "QQ苹果区", 3: "微信安卓区", 4: "微信苹果区"}
RANK_DATE_TYPES = {0: "今日", 1: "昨日"}

CSV_FIELDS = [
    "branchType", "branchTypeName", "areaType", "areaTypeName", "rankDateType", "rankDateTypeName",
    "rankNo", "nickname", "rankScore", "gradeLevel", "sex", "lastDayScore", "lastDayRank",
]


class PeakAuthError(RuntimeError):
    pass


def load_headers(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        headers = json.load(f)
    headers.pop("_comment", None)
    headers.pop("Content-Length", None)
    return headers


def fetch(headers: dict, role_id: int, branch_type: int, area_type: int, rank_date_type: int,
          page_size: int = 500, timeout: float = 15.0) -> list[dict]:
    body = {
        "cSystem": "android",
        "h5Get": 1,
        "roleId": role_id,
        "areaType": area_type,
        "page": 1,
        "pageSize": page_size,
        "branchType": branch_type,
        "rankDateType": rank_date_type,
    }
    resp = requests.post(URL, headers=headers, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=timeout)
    if resp.status_code != 200:
        raise PeakAuthError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "rankList" not in data:
        raise PeakAuthError(
            f"返回内容不含 rankList，很可能是抓包头已经过期，需要重新抓一份。"
            f"原始返回：{json.dumps(data, ensure_ascii=False)[:300]}"
        )
    return data["rankList"]


def flatten(rank_list: list[dict], branch_type: int, area_type: int, rank_date_type: int) -> list[dict]:
    rows = []
    for item in rank_list:
        rows.append(
            {
                "branchType": branch_type,
                "branchTypeName": BRANCH_TYPES.get(branch_type, str(branch_type)),
                "areaType": area_type,
                "areaTypeName": AREA_TYPES.get(area_type, str(area_type)),
                "rankDateType": rank_date_type,
                "rankDateTypeName": RANK_DATE_TYPES.get(rank_date_type, str(rank_date_type)),
                "rankNo": item.get("rankNo"),
                "nickname": item.get("nickname"),
                "rankScore": item.get("rankScore"),
                "gradeLevel": item.get("gradeLevel"),
                "sex": item.get("sex"),
                "lastDayScore": item.get("lastDayScore"),
                "lastDayRank": item.get("lastDayRank"),
            }
        )
    return rows


def parse_dim(value: str, valid: dict[int, str]) -> list[int]:
    if value == "all":
        return sorted(valid.keys())
    return [int(x) for x in value.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser(description="巅峰榜全量采集（branchType x areaType x rankDateType）")
    ap.add_argument("--headers", default="peak_headers.json", help="一次抓包得到的完整请求头 JSON 文件路径")
    ap.add_argument("--role-id", type=int, required=True, help="你自己的 roleId（对应抓包里 body 的 roleId）")
    ap.add_argument("--branch-type", default="all", help="逗号分隔或 all，取值 1-7，见 BRANCH_TYPES")
    ap.add_argument("--area-type", default="all", help="逗号分隔或 all，取值 1-4，见 AREA_TYPES")
    ap.add_argument("--rank-date-type", default="0,1", help="逗号分隔，0=今日 1=昨日")
    ap.add_argument("--page-size", type=int, default=500, help="单次请求条数，榜单封顶500，直接一次拿满")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    headers = load_headers(args.headers)
    branch_types = parse_dim(args.branch_type, BRANCH_TYPES)
    area_types = parse_dim(args.area_type, AREA_TYPES)
    rank_date_types = [int(x) for x in args.rank_date_type.split(",")]

    total_combos = len(branch_types) * len(area_types) * len(rank_date_types)
    print(f"组合数 = {len(branch_types)}(分路) x {len(area_types)}(区服) x {len(rank_date_types)}(今日/昨日) = {total_combos}")

    all_rows: list[dict] = []
    done = 0
    for branch_type in branch_types:
        for area_type in area_types:
            for rank_date_type in rank_date_types:
                done += 1
                print(f"[{done}/{total_combos}] branchType={branch_type}({BRANCH_TYPES.get(branch_type,'?')}) "
                      f"areaType={area_type}({AREA_TYPES.get(area_type,'?')}) rankDateType={rank_date_type} ...")
                try:
                    rank_list = fetch(headers, args.role_id, branch_type, area_type, rank_date_type, args.page_size)
                except PeakAuthError as e:
                    print(f"停止：{e}")
                    _write_out(all_rows, args.out)
                    return
                rows = flatten(rank_list, branch_type, area_type, rank_date_type)
                print(f"  -> {len(rows)} 条")
                all_rows.extend(rows)
                time.sleep(args.delay)

    _write_out(all_rows, args.out)


def _write_out(rows: list[dict], out: str) -> None:
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".csv":
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"完成，共 {len(rows)} 条，已写入 {out_path}")


if __name__ == "__main__":
    main()
