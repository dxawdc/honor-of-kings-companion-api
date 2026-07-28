"""
英雄热度榜采集脚本（对应 App 内「工具箱 - 英雄热度榜」）。

接口：POST https://kohcamp.qq.com/hero/getdetailranklistbyid
请求体：{"bottomTab":"","rankId":0,"segment":<段位>,"position":<分路>,"recommendPrivacy":0}

维度取值（来自接口返回的 filter 字段，实测有效）：
  position（分路）: 0=全部分路 1=对抗路 2=中路 3=发育路 4=游走 5=打野
  segment（段位） : 1=所有段位 3=巅峰赛1350+ 4=顶端排位 5=赛事
                    （0、2 目前是空位，服务端会返回空列表，脚本默认跳过）

用法示例：
  # 抓「所有段位 + 全部分路」一组
  python -m collectors.hero_rank --config config.json --segment 1 --position 0 --out out/hero_1_0.json

  # 抓全部 4 段位 x 6 分路 = 24 组合，输出成一份汇总 CSV
  python -m collectors.hero_rank --config config.json --segment all --position all --out out/hero_all.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from collectors.client import AuthError, KohCampClient

SEGMENTS = {1: "所有段位", 3: "巅峰赛1350+", 4: "顶端排位", 5: "赛事"}
POSITIONS = {0: "全部分路", 1: "对抗路", 2: "中路", 3: "发育路", 4: "游走", 5: "打野"}

CSV_FIELDS = [
    "segment", "segmentName", "position", "positionName",
    "heroId", "heroName", "tRank", "winRate", "showRate", "banRate",
]


def fetch_one(client: KohCampClient, segment: int, position: int) -> dict:
    body = {"bottomTab": "", "rankId": 0, "segment": segment, "position": position, "recommendPrivacy": 0}
    return client.post("/hero/getdetailranklistbyid", body)


def flatten(resp: dict, segment: int, position: int) -> list[dict]:
    rows = []
    for item in resp.get("data", {}).get("list", []):
        hero = item.get("heroInfo", {})
        rows.append(
            {
                "segment": segment,
                "segmentName": SEGMENTS.get(segment, str(segment)),
                "position": position,
                "positionName": POSITIONS.get(position, str(position)),
                "heroId": hero.get("heroId"),
                "heroName": hero.get("heroName"),
                "tRank": item.get("tRank"),
                "winRate": item.get("winRate"),
                "showRate": item.get("showRate"),
                "banRate": item.get("banRate"),
            }
        )
    return rows


def parse_dim(value: str, valid: dict[int, str]) -> list[int]:
    if value == "all":
        return sorted(valid.keys())
    return [int(x) for x in value.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser(description="英雄热度榜采集")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--segment", default="1", help="段位，逗号分隔或 all，取值见 SEGMENTS")
    ap.add_argument("--position", default="0", help="分路，逗号分隔或 all，取值见 POSITIONS")
    ap.add_argument("--out", required=True, help="输出文件路径，.json 或 .csv")
    ap.add_argument("--delay", type=float, default=0.5, help="每次请求间隔秒数")
    args = ap.parse_args()

    segments = parse_dim(args.segment, SEGMENTS)
    positions = parse_dim(args.position, POSITIONS)

    client = KohCampClient(args.config, delay=args.delay)

    all_rows: list[dict] = []
    for segment in segments:
        for position in positions:
            print(f"抓取 segment={segment}({SEGMENTS.get(segment, '?')}) "
                  f"position={position}({POSITIONS.get(position, '?')}) ...")
            try:
                resp = fetch_one(client, segment, position)
            except AuthError as e:
                print(f"认证失败，停止后续请求：{e}")
                break
            rows = flatten(resp, segment, position)
            print(f"  -> {len(rows)} 条")
            all_rows.extend(rows)

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
