"""
王者营地 App 内部接口（kohcamp.qq.com）通用请求客户端。

这些接口是王者荣耀官方伴侣 App「王者营地」登录后才能访问的私有接口，
认证信息（token / openId / gameOpenId 等）与你自己的游戏账号绑定，
本模块只负责：拼装请求头、发请求、做限流和基本的错误识别。

认证信息不要写在代码里，统一放到本地的 config.json（参考 config.example.json），
该文件已加入 .gitignore，不会被提交。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://kohcamp.qq.com"

# 这些字段在同一次登录会话内基本固定，随请求变化的只有 cRand（毫秒时间戳）。
_STATIC_HEADER_FIELDS = [
    "cChannelId",
    "cClientVersionCode",
    "cClientVersionName",
    "cCurrentGameId",
    "cGameId",
    "cSystemVersionCode",
    "cSystemVersionName",
    "cpuHardware",
    "encodeParam",
    "gameAreaId",
    "gameId",
    "gameOpenId",
    "gameRoleId",
    "gameServerId",
    "gameUserSex",
    "openId",
    "tinkerId",
    "token",
    "userId",
]


class AuthError(RuntimeError):
    """认证信息失效（token/encodeParam 过期等），需要重新抓包获取。"""


class KohCampClient:
    def __init__(self, config_path: str | Path, delay: float = 0.5, timeout: float = 10.0):
        self.config = self._load_config(config_path)
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self._last_request_ts = 0.0

    @staticmethod
    def _load_config(config_path: str | Path) -> dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(
                f"找不到配置文件 {path}，请复制 config.example.json 为 config.json 并填入你自己的抓包字段"
            )
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        missing = [k for k in _STATIC_HEADER_FIELDS if not cfg.get(k)]
        if missing:
            raise ValueError(f"config.json 缺少字段: {missing}")
        return cfg

    def _headers(self) -> dict[str, str]:
        headers = {k: str(self.config[k]) for k in _STATIC_HEADER_FIELDS}
        headers.update(
            {
                "cGzip": "1",
                "cIsArm64": "true",
                "cSupportArm64": "true",
                "cSystem": "android",
                "cRand": str(int(time.time() * 1000)),
                "NOENCRYPT": "1",
                "Content-Encrypt": "",
                "Accept-Encrypt": "",
                "X-Client-Proto": "https",
                "x-log-uid": self.config.get("x-log-uid") or str(uuid.uuid4()).upper(),
                "kohDimGender": str(self.config.get("gameUserSex", "1")),
                "Content-Type": "application/json; charset=UTF-8",
                "User-Agent": "okhttp/4.9.1",
                "Accept-Encoding": "gzip",
            }
        )
        return headers

    def _throttle(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def post(self, path: str, body: dict[str, Any], retries: int = 2) -> dict[str, Any]:
        """POST 到 kohcamp.qq.com，返回解析后的 JSON。会自动限流和重试。"""
        url = f"{BASE_URL}{path}"
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            self._throttle()
            self._last_request_ts = time.time()
            try:
                resp = self.session.post(
                    url,
                    headers=self._headers(),
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1 + attempt)
                continue

            if resp.status_code != 200:
                last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(1 + attempt)
                continue

            data = resp.json()
            return_code = data.get("returnCode")
            if return_code not in (0, None):
                msg = data.get("returnMsg", "")
                if return_code in (-1, 1001, 1002) or "token" in msg.lower() or "登录" in msg:
                    raise AuthError(
                        f"接口返回 returnCode={return_code} msg={msg!r}，"
                        "大概率是 token/encodeParam 过期，请重新抓包更新 config.json"
                    )
                last_exc = RuntimeError(f"returnCode={return_code} msg={msg!r}")
                time.sleep(1 + attempt)
                continue
            return data

        assert last_exc is not None
        raise last_exc


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
