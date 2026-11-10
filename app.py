"""쇼핑 리스트 Streamlit 앱."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

import streamlit as st

from storage import load_items, transaction

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

NAME_MAX = 50
MEMO_MAX = 100
QTY_MIN, QTY_MAX = 1, 999
FILTERS = ["전체", "미완료", "완료"]


# ---------------------------------------------------------------- 데이터 헬퍼


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_item(name: str, quantity: int = 1, memo: str = "") -> dict:
    """PRD 5장 데이터 모델에 맞는 아이템을 만든다."""
    now = _now()
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "quantity": quantity,
        "memo": memo,
        "checked": False,
        "created_at": now,
        "updated_at": now,
    }


def _normalize(name: str) -> str:
    return name.strip().casefold()


def find(items: list[dict], item_id: str) -> dict | None:
    return next((i for i in items if i["id"] == item_id), None)


def validate(
    items: list[dict], name: str, quantity: int | None, memo: str, exclude_id: str | None = None
) -> str | None:
    """입력값을 검증한다. 문제가 있으면 오류 메시지, 없으면 None."""
    if not name:
        return "아이템 이름을 입력해 주세요."
    if len(name) > NAME_MAX:
        return f"아이템 이름은 {NAME_MAX}자 이하로 입력해 주세요."
    if len(memo) > MEMO_MAX:
        return f"메모는 {MEMO_MAX}자 이하로 입력해 주세요."
    if quantity is None or not (QTY_MIN <= quantity <= QTY_MAX):
        return f"수량은 {QTY_MIN}~{QTY_MAX} 사이로 입력해 주세요."
    key = _normalize(name)
    for item in items:
        if item["id"] != exclude_id and _normalize(item["name"]) == key:
            return f"'{md_escape(item['name'])}'은(는) 이미 리스트에 있어요."
    return None


def _qty(value) -> int | None:
    return None if value is None else int(value)


def notify(message: str, icon: str = "✅") -> None:
    """콜백에서 보낸 알림을 다음 화면 렌더링 때 st.toast로 보여 준다. message는 이스케이프된 상태여야 한다."""
    st.session_state["toasts"].append((message, icon))


# ---------------------------------------------------------------- 마크다운 이스케이프

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>:$^])")
# 자동 링크(http://, www., 이메일)는 백슬래시 이스케이프로 막히지 않으므로 폭 없는 공백으로 끊는다.
_AUTOLINK = re.compile(r"(?i)(https?|ftp|mailto)(?=:)|\b(www)(?=\.)|(@)")
_ZWSP = "​"


def md_escape(text: str) -> str:
    """사용자 입력을 마크다운 서식·링크 없이 그대로 보이도록 이스케이프한다."""
    text = _AUTOLINK.sub(lambda m: m.group(0) + _ZWSP, text)
    return _MD_SPECIAL.sub(r"\\\1", text)


# ---------------------------------------------------------------- 상태 초기화


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("editing_id", None)
    ss.setdefault("confirm_clear_all", False)
    ss.setdefault("toasts", [])
    ss.setdefault("add_error", None)
    ss.setdefault("edit_error", None)
    # 위젯 기본값 (value=/default= 인자 대신 세션 상태로 관리해 콜백에서 바꿀 수 있도록)
    ss.setdefault("new_name", "")
    ss.setdefault("new_qty", 1)
    ss.setdefault("new_memo", "")
    ss.setdefault("filter", "전체")


# ---------------------------------------------------------------- 콜백
# 모든 수정은 transaction() 안에서 파일의 최신 목록을 기준으로 한다 (다른 탭·기기 변경 보존).


def on_add() -> None:
    ss = st.session_state
    name = ss["new_name"].strip()
    memo = ss["new_memo"].strip()
    qty = _qty(ss["new_qty"])
    with transaction() as items:
        error = validate(items, name, qty, memo)
        if error:
            ss["add_error"] = error
            return
        items.append(new_item(name, qty, memo))
    ss["new_name"], ss["new_qty"], ss["new_memo"] = "", 1, ""
    ss["add_error"] = None
    notify(f"'{md_escape(name)}'을(를) 추가했어요.")


def on_toggle(item_id: str) -> None:
    checked = st.session_state[f"chk_{item_id}"]
    with transaction() as items:
        item = find(items, item_id)
        if item is None:
            notify("다른 곳에서 이미 삭제된 항목이에요.", "⚠️")
            return
        item["checked"] = checked
        item["updated_at"] = _now()


def on_start_edit(item_id: str) -> None:
    item = find(load_items(), item_id)
    if item is None:
        notify("다른 곳에서 이미 삭제된 항목이에요.", "⚠️")
        return
    ss = st.session_state
    ss["editing_id"] = item_id
    ss["edit_error"] = None
    ss[f"edit_name_{item_id}"] = item["name"]
    ss[f"edit_qty_{item_id}"] = item["quantity"]
    ss[f"edit_memo_{item_id}"] = item["memo"]


def on_save_edit(item_id: str) -> None:
    ss = st.session_state
    name = ss[f"edit_name_{item_id}"].strip()
    memo = ss[f"edit_memo_{item_id}"].strip()
    qty = _qty(ss[f"edit_qty_{item_id}"])
    with transaction() as items:
        item = find(items, item_id)
        if item is None:
            on_cancel_edit()
            notify("다른 곳에서 이미 삭제된 항목이라 저장하지 못했어요.", "⚠️")
            return
        error = validate(items, name, qty, memo, exclude_id=item_id)
        if error:
            ss["edit_error"] = error
            return
        item.update(name=name, quantity=qty, memo=memo, updated_at=_now())
    on_cancel_edit()
    notify(f"'{md_escape(name)}'을(를) 수정했어요.")


def on_cancel_edit() -> None:
    st.session_state["editing_id"] = None
    st.session_state["edit_error"] = None


def on_delete(item_id: str) -> None:
    with transaction() as items:
        item = find(items, item_id)
        if item is None:
            notify("다른 곳에서 이미 삭제된 항목이에요.", "⚠️")
            return
        items[:] = [i for i in items if i["id"] != item_id]
    if st.session_state["editing_id"] == item_id:
        on_cancel_edit()
    notify(f"'{md_escape(item['name'])}'을(를) 삭제했어요.", "🗑️")


def on_delete_checked() -> None:
    with transaction() as items:
        remaining = [i for i in items if not i["checked"]]
        removed = len(items) - len(remaining)
        items[:] = remaining
    if st.session_state["editing_id"] not in {i["id"] for i in remaining}:
        on_cancel_edit()
    notify(f"체크된 항목 {removed}개를 삭제했어요.", "🗑️")


def on_request_clear_all() -> None:
    st.session_state["confirm_clear_all"] = True


def on_confirm_clear_all() -> None:
    with transaction() as items:
        items.clear()
    on_cancel_edit()
    st.session_state["confirm_clear_all"] = False
    notify("전체 아이템을 삭제했어요.", "🗑️")


def on_cancel_clear_all() -> None:
    st.session_state["confirm_clear_all"] = False


def on_filter_change() -> None:
    # 선택된 필터를 다시 누르면 선택이 해제되므로 "전체"로 되돌린다.
    if st.session_state["filter"] is None:
        st.session_state["filter"] = "전체"


# ---------------------------------------------------------------- 화면

# 사용자 입력이 들어가지 않는 고정 CSS만 사용한다.
CSS = """
<style>
/* 아이템 행·추가 폼: 좁은 화면에서도 컬럼이 세로로 쌓이지 않게 한 줄 유지 */
.st-key-add_box [data-testid="stHorizontalBlock"],
[class*="st-key-row_"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.5rem;
}
.st-key-add_box [data-testid="stColumn"],
[class*="st-key-row_"] [data-testid="stColumn"] {
    min-width: 0 !important;
}
/* 아이템 행: 긴 단어 줄바꿈, 버튼은 손가락으로 누르기 쉬운 크기로 */
[class*="st-key-row_"] p {
    overflow-wrap: anywhere;
}
[class*="st-key-row_"] button {
    min-height: 2.5rem;
    min-width: 2.5rem;
    padding: 0 0.4rem;
}
/* 빈 상태 안내 */
.empty-state {
    text-align: center;
    padding: 2.5rem 1rem;
    opacity: 0.7;
    line-height: 1.8;
}
.empty-state .empty-icon { font-size: 2.5rem; }
/* 모바일: 수량 입력의 +/- 버튼을 숨겨 입력칸 공간 확보 */
@media (max-width: 640px) {
    .st-key-add_box [data-testid="stNumberInputStepUp"],
    .st-key-add_box [data-testid="stNumberInputStepDown"] {
        display: none;
    }
}
</style>
"""


def render_toasts() -> None:
    for message, icon in st.session_state["toasts"]:
        st.toast(message, icon=icon)
    st.session_state["toasts"] = []


def render_header(items: list[dict]) -> None:
    st.title("🛒 쇼핑 리스트")
    total = len(items)
    done = sum(1 for i in items if i["checked"])
    if total == 0:
        st.caption("살 것을 적어 두고, 장바구니에 담으면 체크하세요.")
        return
    ratio = done / total
    st.markdown(f"전체 **{total}**개 · 남은 것 **{total - done}**개 · 완료 **{done}**개")
    st.progress(ratio, text=f"{round(ratio * 100)}% 완료")
    if done == total:
        st.success("모두 샀어요! 🎉")


def render_add_form() -> None:
    # 수량 범위는 위젯(min/max)이 아니라 validate()에서 검사한다.
    # 위젯 범위 검사는 제출을 조용히 막고 영어 툴팁만 보여 주기 때문.
    with st.container(key="add_box"):
        with st.form("add_form", border=True):
            col_name, col_qty, col_btn = st.columns([5, 2, 2], vertical_alignment="bottom")
            col_name.text_input(
                "아이템 이름", key="new_name", max_chars=NAME_MAX, placeholder="예: 우유"
            )
            col_qty.number_input("수량", key="new_qty", step=1)
            col_btn.form_submit_button("추가", on_click=on_add, type="primary", width="stretch")
            st.text_input(
                "메모",
                key="new_memo",
                max_chars=MEMO_MAX,
                placeholder="메모 (선택) 예: 저지방",
                label_visibility="collapsed",
            )
    if st.session_state["add_error"]:
        st.warning(st.session_state["add_error"], icon="⚠️")
        st.session_state["add_error"] = None


def render_edit_row(item: dict) -> None:
    item_id = item["id"]
    with st.container(key=f"row_edit_{item_id}"):
        with st.form(f"edit_form_{item_id}", border=True):
            col_name, col_qty = st.columns([3, 1])
            col_name.text_input("아이템 이름", key=f"edit_name_{item_id}", max_chars=NAME_MAX)
            col_qty.number_input("수량", key=f"edit_qty_{item_id}", step=1)
            st.text_input("메모 (선택)", key=f"edit_memo_{item_id}", max_chars=MEMO_MAX)
            col_save, col_cancel = st.columns(2)
            col_save.form_submit_button(
                "저장", on_click=on_save_edit, args=(item_id,), type="primary", width="stretch"
            )
            col_cancel.form_submit_button("취소", on_click=on_cancel_edit, width="stretch")
    if st.session_state["edit_error"]:
        st.warning(st.session_state["edit_error"], icon="⚠️")
        st.session_state["edit_error"] = None


def render_item_row(item: dict, editing_other: bool) -> None:
    item_id = item["id"]
    checked = item["checked"]
    name = md_escape(item["name"])
    qty = item["quantity"]

    # 다른 탭·기기에서 바뀐 체크 상태가 반영되도록 매번 파일 값으로 위젯 상태를 맞춘다.
    st.session_state[f"chk_{item_id}"] = checked

    with st.container(border=True, key=f"row_{item_id}"):
        col_chk, col_text, col_edit, col_del = st.columns(
            [0.7, 6, 1, 1], vertical_alignment="center", gap="small"
        )
        col_chk.checkbox(
            f"{name} 구매 완료",
            key=f"chk_{item_id}",
            on_change=on_toggle,
            args=(item_id,),
            label_visibility="collapsed",
        )
        if checked:
            text = f":gray[~~{name}~~] :gray-badge[x{qty}]"
        else:
            text = f"**{name}** :green-badge[x{qty}]"
        if item["memo"]:
            # 메모는 이름 아래 작은 회색 글씨로 (같은 블록에 넣어 줄 간격을 좁힘)
            text += f"  \n:small[:gray[{md_escape(item['memo'])}]]"
        col_text.markdown(text)
        # 편집 중일 때는 다른 행 수정을 막아, 저장하지 않은 변경이 조용히 사라지지 않게 한다.
        col_edit.button(
            "✏️",
            key=f"edit_{item_id}",
            on_click=on_start_edit,
            args=(item_id,),
            help="편집 중인 항목을 먼저 저장하거나 취소하세요" if editing_other else "수정",
            type="tertiary",
            disabled=editing_other,
        )
        col_del.button(
            "🗑️",
            key=f"del_{item_id}",
            on_click=on_delete,
            args=(item_id,),
            help="삭제",
            type="tertiary",
        )


def render_list(items: list[dict]) -> None:
    if not items:
        st.markdown(
            '<div class="empty-state"><div class="empty-icon">🧺</div>'
            "아직 아이템이 없어요. 위에서 추가해 보세요!</div>",
            unsafe_allow_html=True,
        )
        return

    done = sum(1 for i in items if i["checked"])
    counts = {"전체": len(items), "미완료": len(items) - done, "완료": done}
    st.segmented_control(
        "보기",
        FILTERS,
        key="filter",
        on_change=on_filter_change,
        format_func=lambda f: f"{f} {counts[f]}",
        label_visibility="collapsed",
        width="stretch",
    )
    selected = st.session_state["filter"] or "전체"
    editing_id = st.session_state["editing_id"]

    ordered = sorted(items, key=lambda i: (i["checked"], i["created_at"]))
    # 편집 중인 항목은 필터와 관계없이 보여 준다 (저장·취소할 수 있도록).
    if selected == "미완료":
        ordered = [i for i in ordered if not i["checked"] or i["id"] == editing_id]
    elif selected == "완료":
        ordered = [i for i in ordered if i["checked"] or i["id"] == editing_id]

    if not ordered:
        st.markdown(
            '<div class="empty-state">해당하는 아이템이 없어요.</div>', unsafe_allow_html=True
        )
    for item in ordered:
        if item["id"] == editing_id:
            render_edit_row(item)
        else:
            render_item_row(item, editing_other=editing_id is not None)


def render_bulk_actions(items: list[dict]) -> None:
    if not items:
        st.session_state["confirm_clear_all"] = False
        return
    st.divider()
    has_checked = any(i["checked"] for i in items)
    col_checked, col_all = st.columns(2)
    col_checked.button(
        "체크된 항목 삭제",
        on_click=on_delete_checked,
        disabled=not has_checked,
        icon=":material/playlist_remove:",
        width="stretch",
    )
    col_all.button(
        "전체 삭제", on_click=on_request_clear_all, icon=":material/delete_sweep:", width="stretch"
    )
    if st.session_state["confirm_clear_all"]:
        st.warning(f"아이템 {len(items)}개를 모두 삭제할까요? 되돌릴 수 없어요.", icon="⚠️")
        col_yes, col_no = st.columns(2)
        col_yes.button("삭제", on_click=on_confirm_clear_all, type="primary", width="stretch")
        col_no.button("취소", on_click=on_cancel_clear_all, width="stretch")


# ---------------------------------------------------------------- 메인

init_state()

# 매 실행마다 파일에서 최신 목록을 읽어 다른 탭·기기의 변경을 반영한다.
items = load_items()
st.session_state["items"] = items
if st.session_state["editing_id"] and find(items, st.session_state["editing_id"]) is None:
    on_cancel_edit()
    notify("편집 중이던 항목이 다른 곳에서 삭제됐어요.", "⚠️")

render_toasts()
st.markdown(CSS, unsafe_allow_html=True)
render_header(items)
render_add_form()
render_list(items)
render_bulk_actions(items)
