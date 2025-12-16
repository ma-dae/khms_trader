# scripts/run_dashboard.py
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANS_DIR = PROJECT_ROOT / "plans"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_UNIVERSE_DIR = PROJECT_ROOT / "data" / "universe"
EVENTS_PATH = PROJECT_ROOT / "reports" / "live_events.jsonl"


def _ensure_pythonpath() -> None:
    src = str(PROJECT_ROOT / "src")
    cur = os.environ.get("PYTHONPATH", "")
    if src not in cur.split(os.pathsep):
        os.environ["PYTHONPATH"] = src + (os.pathsep + cur if cur else "")


def _list_plan_files() -> List[Path]:
    if not PLANS_DIR.exists():
        return []
    files = sorted(PLANS_DIR.glob("next_open_plan_*.json"), reverse=True)
    return files


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tail_text(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _list_log_files() -> List[Path]:
    if not LOGS_DIR.exists():
        return []
    # 필요한 확장자만
    exts = (".log", ".txt")
    files = [p for p in LOGS_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _get_broker_state() -> Tuple[Optional[float], Dict[str, int], Optional[str]]:
    """
    broker를 직접 조회하되, 대시보드가 죽지 않게 예외를 문자열로 반환.
    """
    try:
        from khms_trader.config import load_settings
        from khms_trader.broker.factory import make_broker

        s = load_settings()
        broker_cfg = (s.get("broker") or {})
        env = str(broker_cfg.get("env", "")).lower()
        provider = str(broker_cfg.get("provider", ""))

        broker = make_broker()
        cash = float(broker.get_cash())
        positions = broker.get_positions() if hasattr(broker, "get_positions") else {}

        # 안전을 위해 현재 설정도 같이 보여줌
        meta = f"provider={provider}, env={env}"
        return cash, {str(k).zfill(6): int(v) for k, v in (positions or {}).items()}, meta

    except Exception as e:
        return None, {}, f"broker_error: {type(e).__name__}: {e}"


def _list_universe_files() -> List[Path]:
    if not DATA_UNIVERSE_DIR.exists():
        return []
    files = sorted(DATA_UNIVERSE_DIR.glob("kosdaq_*.csv"), reverse=True)
    return files


def main() -> None:
    _ensure_pythonpath()

    st.set_page_config(page_title="KHMS Trader Dashboard", layout="wide")
    st.title("KHMS Trader Dashboard (MVP)")

    # Sidebar controls
    st.sidebar.header("Controls")
    auto_refresh = st.sidebar.checkbox("Auto refresh", value=False)
    refresh_sec = st.sidebar.number_input("Refresh interval (sec)", min_value=3, max_value=300, value=10, step=1)
    if auto_refresh:
        st.sidebar.caption("Auto refresh is enabled.")
        st.sidebar.write(f"Last refresh: {datetime.now():%Y-%m-%d %H:%M:%S}")
        st.autorefresh(interval=int(refresh_sec * 1000), key="refresh")

    colA, colB = st.columns([1, 1])

    # ---- Broker state ----
    with colA:
        st.subheader("Account (Virtual) Snapshot")
        cash, pos, meta = _get_broker_state()
        if cash is None:
            st.error(meta or "broker unavailable")
        else:
            st.write(meta)
            st.metric("Cash", f"{cash:,.0f} KRW")
            st.metric("Positions", f"{len(pos)} symbols")

            if pos:
                pos_df = pd.DataFrame(
                    [{"symbol": k, "qty": v} for k, v in sorted(pos.items(), key=lambda x: -x[1])]
                )
                st.dataframe(pos_df, use_container_width=True, hide_index=True)
            else:
                st.info("No positions.")

    # ---- Plans ----
    with colB:
        st.subheader("Next-Open Plans")
        plan_files = _list_plan_files()
        if not plan_files:
            st.warning("No plan files found under /plans.")
        else:
            labels = [p.name for p in plan_files]
            selected = st.selectbox("Select plan file", labels, index=0)
            plan_path = PLANS_DIR / selected
            plan = _read_json(plan_path)

            # Summary
            buy = plan.get("buy") or []
            sell = plan.get("sell") or []
            err = plan.get("errors") or {}

            st.write(f"Generated at: `{plan.get('generated_at')}`")
            st.write(f"For trading day: `{plan.get('for_trading_day')}`")
            st.write(f"Universe file: `{plan.get('universe_file')}`")
            st.write(f"Fill mode: `{plan.get('fill_mode')}`")

            c1, c2, c3 = st.columns(3)
            c1.metric("BUY candidates", len(buy))
            c2.metric("SELL candidates", len(sell))
            c3.metric("Errors", len(err))

            # Details
            with st.expander("BUY list", expanded=False):
                st.dataframe(pd.DataFrame({"symbol": buy}), use_container_width=True, hide_index=True)

            with st.expander("SELL list", expanded=False):
                st.dataframe(pd.DataFrame({"symbol": sell}), use_container_width=True, hide_index=True)

            if err:
                with st.expander("Errors (sample)", expanded=False):
                    # 너무 길 수 있으니 상위 50개 제한
                    items = list(err.items())[:50]
                    st.dataframe(pd.DataFrame(items, columns=["symbol", "error"]), use_container_width=True, hide_index=True)

    st.divider()

    # ---- Universe files ----
    st.subheader("Universe Files")
    ufiles = _list_universe_files()
    if not ufiles:
        st.info("No universe files found under /data/universe.")
    else:
        ulab = [p.name for p in ufiles]
        u_selected = st.selectbox("Select universe CSV", ulab, index=0)
        u_path = DATA_UNIVERSE_DIR / u_selected
        try:
            udf = pd.read_csv(u_path)
            st.write(f"Rows: {len(udf)} | Columns: {list(udf.columns)}")
            st.dataframe(udf.head(200), use_container_width=True)
        except Exception as e:
            st.error(f"Failed to read universe: {type(e).__name__}: {e}")

    st.divider()

    # ---- Logs ----
    st.subheader("Logs (tail)")
    log_files = _list_log_files()
    if not log_files:
        st.info("No .log/.txt files found under /logs. (Optional) You can add file logging later.")
    else:
        llab = [p.name for p in log_files]
        log_selected = st.selectbox("Select log file", llab, index=0)
        log_path = LOGS_DIR / log_selected
        lines = st.slider("Tail lines", min_value=50, max_value=2000, value=200, step=50)
        st.code(_tail_text(log_path, max_lines=int(lines)), language="text")


if __name__ == "__main__":
    main()
