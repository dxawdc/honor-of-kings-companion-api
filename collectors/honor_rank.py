"""
荣耀榜采集脚本（对应 App 内「工具箱 - 荣耀榜」，按英雄 + 地区查看称号积分排名）。

接口：
  地区树   POST https://kohcamp.qq.com/game/honor/districts
  排行榜   POST https://kohcamp.qq.com/game/honor/ranklist
           body: {"recommendPrivacy":0,"areaId":<大区,取自config>,"adcode":<地区码>,"roleId":<你的roleId>,"heroId":<英雄ID>}

关键点：
  - adcode 可以是省级(3位)、市级(4位)、区县级(6位)，三层都能单独查询，
    地区码表已经离线存在 data/regions.json，不需要每次现查。
  - 每次查询最多返回 100 条（不支持分页），返回条数 = 该英雄在该地区实际有效排名人数。
  - 「全量」= 英雄数 x 地区节点数，例如 131 英雄 x 3246 地区(省+市+区县) ≈ 42.5 万次请求，
    体量比另外两个榜单大好几个量级，脚本默认不允许直接跑全量，超过阈值必须加 --confirm-full。

用法示例：
  # 只看省级颗粒度，全部英雄（131 x 34 = 4454 次请求）
  python -m collectors.honor_rank --config config.json --region-level province --hero-ids all --out out/honor_province.csv

  # 指定英雄 + 指定地区
  python -m collectors.honor_rank --config config.json --hero-ids 118 --adcodes 510107 --out out/honor_118_510107.json

  # 真的要跑三级全量（不推荐，体量巨大且容易触发限流/风控）
  python -m collectors.honor_rank --config config.json --region-level all --hero-ids all --confirm-full --out out/honor_full.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from collectors.client import AuthError, KohCampClient, load_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FULL_RUN_THRESHOLD = 5000  # 超过这个组合数就要求显式确认

CSV_FIELDS = [
    "heroId", "heroName", "adcode", "regionName", "regionLevel",
    "rankNo", "roleId", "roleName", "roleJobName", "rankValue", "rankChange",
]


def load_heroes(hero_ids_arg: str) -> list[dict]:
    heroes = load_json(DATA_DIR / "heroes.json")
    if hero_ids_arg == "all":
        return heroes
    wanted = {int(x) for x in hero_ids_arg.split(",")}
    return [h for h in heroes if h["heroId"] in wanted]


def flatten_regions(node: dict, level: str, out: list[dict]) -> None:
    out.append({"adcode": node["adcode"], "name": node["name"], "level": level})
    next_level = {"province": "city", "city": "county"}.get(level)
    for child in node.get("children", []) or []:
        flatten_regions(child, next_level, out)


def load_regions(region_level_arg: str, adcodes_arg: str | None) -> list[dict]:
    if adcodes_arg:
        codes = {int(x) for x in adcodes_arg.split(",")}
        return [{"adcode": c, "name": str(c), "level": "unknown"} for c in codes]

    tree = load_json(DATA_DIR / "regions.json")["tree"]
    flat: list[dict] = []
    for province in tree:
        flatten_regions(province, "province", flat)

    if region_level_arg == "all":
        return flat
    return [r for r in flat if r["level"] == region_level_arg]


def fetch_one(client: KohCampClient, hero_id: int, adcode: int, area_id: str) -> dict:
    body = {
        "recommendPrivacy": 0,
        "areaId": int(area_id),
        "adcode": adcode,
        "roleId": client.config["gameRoleId"],
        "heroId": hero_id,
    }
    return client.post("/game/honor/ranklist", body)


def flatten(resp: dict, hero: dict, region: dict) -> list[dict]:
    rows = []
    for item in resp.get("data", {}).get("list", []):
        rows.append(
            {
                "heroId": hero["heroId"],
                "heroName": hero["heroName"],
                "adcode": region["adcode"],
                "regionName": region["name"],
                "regionLevel": region["level"],
                "rankNo": item.get("rankNo"),
                "roleId": item.get("roleId"),
                "roleName": item.get("roleName"),
                "roleJobName": item.get("roleJobName"),
                "rankValue": item.get("rankValue"),
                "rankChange": item.get("rankChange"),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="荣耀榜采集")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--hero-ids", default="all", help="英雄ID逗号分隔，或 all")
    ap.add_argument("--region-level", default="province", choices=["province", "city", "county", "all"])
    ap.add_argument("--adcodes", default=None, help="直接指定 adcode 列表（逗号分隔），优先于 --region-level")
    ap.add_argument("--out", required=True)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--confirm-full", action="store_true", help="组合数超过阈值时必须加这个参数才会真正执行")
    ap.add_argument("--limit", type=int, default=None, help="最多执行多少次请求，用于抽样试跑")
    args = ap.parse_args()

    heroes = load_heroes(args.hero_ids)
    regions = load_regions(args.region_level, args.adcodes)
    total_combos = len(heroes) * len(regions)

    print(f"英雄数={len(heroes)} 地区数={len(regions)} 组合数={total_combos}")
    if total_combos > FULL_RUN_THRESHOLD and not args.confirm_full:
        print(
            f"组合数 {total_combos} 超过安全阈值 {FULL_RUN_THRESHOLD}，"
            "这是一次很大的采集量，可能触发接口限流/账号风控。\n"
            "如果确认要这么做，请加上 --confirm-full 重新运行；"
            "更推荐用 --hero-ids / --region-level / --adcodes 缩小范围，或用 --limit 先抽样试跑。"
        )
        return

    client = KohCampClient(args.config, delay=args.delay)
    area_id = client.config["gameAreaId"]

    all_rows: list[dict] = []
    done = 0
    stop = False
    for hero in heroes:
        if stop:
            break
        for region in regions:
            if args.limit and done >= args.limit:
                stop = True
                break
            print(f"[{done + 1}/{total_combos}] hero={hero['heroName']}({hero['heroId']}) "
                  f"region={region['name']}({region['adcode']}) ...")
            try:
                resp = fetch_one(client, hero["heroId"], region["adcode"], area_id)
            except AuthError as e:
                print(f"认证失败，停止后续请求：{e}")
                stop = True
                break
            rows = flatten(resp, hero, region)
            print(f"  -> {len(rows)} 条")
            all_rows.extend(rows)
            done += 1

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
