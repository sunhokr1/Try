"""쇼핑 리스트 데이터 저장소.

app.py는 load_items(), save_items(), transaction()만 사용한다.
저장 방식을 바꿀 때(Google Sheets, Supabase 등)는 이 파일만 교체하면 된다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "shopping_list.json"

# 한 서버 프로세스 안의 여러 세션(탭·기기)이 동시에 읽고-수정하고-쓰는 것을 직렬화한다.
_LOCK = threading.RLock()


def _to_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _normalize_item(raw: Any, index: int, seen_ids: set[str]) -> dict | None:
    """저장된 항목 하나를 앱이 기대하는 형태로 맞춘다. 살릴 수 없으면 None."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()

    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        # 파일이 바뀌지 않는 한 매번 같은 값이 나오도록 결정적으로 만든다 (다음 저장 때 파일에 기록됨).
        item_id = "item-" + hashlib.sha1(f"{index}:{name}".encode()).hexdigest()[:12]
    if item_id in seen_ids:
        item_id = f"{item_id}-{index}"
    seen_ids.add(item_id)

    memo = raw.get("memo")
    created_at = raw.get("created_at")
    updated_at = raw.get("updated_at")
    return {
        "id": item_id,
        "name": name,
        "quantity": max(1, _to_int(raw.get("quantity"), 1)),
        "memo": memo.strip() if isinstance(memo, str) else "",
        "checked": raw.get("checked") in (True, "true", "True"),
        "created_at": created_at if isinstance(created_at, str) else "",
        "updated_at": updated_at if isinstance(updated_at, str) else "",
    }


def load_items() -> list[dict]:
    """저장된 아이템 목록을 불러온다.

    파일이 없거나 손상되었으면 빈 리스트를, 항목 일부가 잘못되었으면 고칠 수 있는 것만 고쳐서 반환한다.
    """
    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    seen: set[str] = set()
    items = (_normalize_item(raw, i, seen) for i, raw in enumerate(data))
    return [item for item in items if item is not None]


def save_items(items: list[dict]) -> None:
    """아이템 목록을 저장한다. 임시 파일에 쓴 뒤 교체해 저장 중 파일 손상을 막는다."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_FILE.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


@contextmanager
def transaction() -> Iterator[list[dict]]:
    """최신 목록을 불러와 넘겨주고, 블록 안에서 바뀌었으면 저장한다.

    다른 탭·기기에서 저장한 내용을 덮어쓰지 않도록, 수정은 항상 이 블록 안에서 한다.
    블록 안에서 예외가 나면 저장하지 않는다.

        with transaction() as items:
            items.append(...)
    """
    with _LOCK:
        items = load_items()
        before = copy.deepcopy(items)
        yield items
        if items != before:
            save_items(items)
