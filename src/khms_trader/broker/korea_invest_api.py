# src/khms_trader/broker/korea_invest_api.py
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Optional, Any

import time
import requests
from datetime import datetime
from .base import BaseBroker, OrderRequest, OrderResult


class KoreaInvestBroker(BaseBroker):
    """
    한국투자증권 OpenAPI 브로커 (모의투자 우선).

    - virtual=True  -> 모의투자(VTS)
    - virtual=False -> 실거래
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        account_product_code: str,
        base_url: str,
        virtual: bool = True,
        timeout_sec: int = 10,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.account_product_code = account_product_code
        self.base_url = base_url.rstrip("/")
        self.virtual = virtual
        self.timeout_sec = timeout_sec

        self._session = requests.Session()
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0.0

        # 계좌번호 파싱: "CANO-ACNT_PRDT_CD" 또는 "CANO"만 들어오는 케이스 대응
        if "-" in account_no:
            self._cano, self._acnt_prdt_cd = account_no.split("-", 1)
        else:
            # 환경별로 상품코드가 01 고정인 경우가 많아 기본값 01
            self._cano, self._acnt_prdt_cd = account_no, "01"

    # ---------- low-level helpers ----------

    def _post(self, path: str, headers: Dict[str, str], json: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        url = self.base_url + path
        r = requests.post(url, headers=headers, json=json, params=params, timeout=10)
        if not r.ok:
            raise RuntimeError(
                f"HTTP {r.status_code} for {url}\n"
                f"response_text={r.text}\n"
            )
        
        return r.json()

    def _get(self, path: str, headers: Dict[str, str], params: Optional[dict] = None) -> dict:
        url = self.base_url + path
        r = requests.get(url, headers=headers, params=params, timeout=10)

        if not r.ok:
            raise RuntimeError(
                f"HTTP {r.status_code} for {r.url}\n"
                f"response_test={r.text}\n"
            )
        
        return r.json()

    def _ensure_token(self) -> None:
        # 토큰이 유효하면 재사용
        now = time.time()
        if self._access_token and now < self._token_expire_at:
            return

        # OAuth2 tokenP 발급 (grant_type=client_credentials)
        # KIS 오픈API에서 통상 사용하는 토큰 발급 방식
        # (응답의 expires_in을 이용해 만료시각 설정)
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        data = self._post("/oauth2/tokenP", headers={"content-type": "application/json"}, json=payload)
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 0) or 0)

        if not token:
            raise RuntimeError(f"Failed to get access_token. resp={data}")

        # 보수적으로 만료 60초 전 갱신
        self._access_token = token
        self._token_expire_at = time.time() + max(expires_in - 60, 60)

    def _auth_headers(self, tr_id: str) -> Dict[str, str]:
        self._ensure_token()
        assert self._access_token is not None
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {self._access_token}",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }

    def _hashkey(self, body: dict) -> str:
        """
        주문(POST) 시 hashkey를 요구하는 환경이 많아 사전 생성.
        KIS는 /uapi/hashkey로 hashkey를 발급해주는 패턴을 제공.
        """
        headers = self._auth_headers(tr_id="")  # hashkey는 tr_id 없이도 동작하는 케이스가 많음
        # 일부 환경에선 authorization/appKey/appSecret만 필요하므로 안전하게 최소로 재구성
        headers = {
            "content-type": "application/json",
            "authorization": headers["authorization"],
            "appKey": self.app_key,
            "appSecret": self.app_secret,
        }
        data = self._post("/uapi/hashkey", headers=headers, json=body)
        hk = data.get("HASH")
        if not hk:
            raise RuntimeError(f"Failed to get hashkey. resp={data}")
        return str(hk)

    # ---------- BaseBroker interface ----------

    def get_cash(self) -> float:
        """
        예수금/현금성 잔고: 잔고조회(inquire-balance) 응답의 output2 계열에서 추출.
        필드명은 계정/환경에 따라 다를 수 있어 몇 가지 후보를 순차 탐색.
        """
        tr_id = "VTTC8434R" if self.virtual else "TTTC8434R"  # 잔고조회 TR (모의/실전) :contentReference[oaicite:5]{index=5}
        headers = self._auth_headers(tr_id=tr_id)

        params = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        data = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params)
        out2 = data.get("output2")

        if isinstance(out2, list):
            if not out2:
                raise RuntimeError("inquire-balance output2 is empty list")
            out2 = out2[0]
        
        if not isinstance(out2, dict):
            raise RuntimeError(f"Unexpected output2 type: {type(out2)}")

        # 후보 필드들(환경별 상이): dnca_tot_amt / prvs_rcdl_excc_amt / tot_evlu_amt 등
        for key in ["dnca_tot_amt", "prvs_rcdl_excc_amt", "cma_evlu_amt", "tot_evlu_amt"]:
            v = out2.get(key)
            if v is not None and str(v).strip() != "":
                try:
                    return float(v)
                except ValueError:
                    pass

        raise RuntimeError(f"Cannot parse cash from inquire-balance. resp_keys={list(out2.keys())}")

    def get_positions(self) -> Dict[str, int]:
        """
        보유 종목 수량: inquire-balance의 output1(보유종목 리스트)에서 qty 추출.
        """
        tr_id = "VTTC8434R" if self.virtual else "TTTC8434R"
        headers = self._auth_headers(tr_id=tr_id)

        params = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        data = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params)
        rows = data.get("output1") or []
        pos: Dict[str, int] = {}
        for r in rows:
            sym = str(r.get("pdno", "")).strip()
            qty = r.get("hldg_qty") or r.get("ord_psbl_qty") or r.get("qty")
            if not sym:
                continue
            try:
                q = int(float(qty))
            except Exception:
                q = 0
            if q != 0:
                pos[sym] = q
        return pos

    def get_position(self, symbol: str) -> int:
        return int(self.get_positions().get(symbol, 0))

    def place_order(self, req: OrderRequest) -> OrderResult:
        """
        현금 주문(order-cash).
        - 모의투자: BUY=VTTC0802U / SELL=VTTC0801U :contentReference[oaicite:6]{index=6}
        - 실전:     BUY=TTTC0802U / SELL=TTTC0801U
        """
        side = req.side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side={req.side}. expected BUY/SELL")

        tr_id = None
        if self.virtual:
            tr_id = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        else:
            tr_id = "TTTC0802U" if side == "BUY" else "TTTC0801U"

        headers = self._auth_headers(tr_id=tr_id)

        # KIS: ORD_DVSN(주문구분) - "01" 지정가, "00" 시장가 등 (프로젝트에선 지정가를 기본 권장)
        body = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "PDNO": req.symbol,
            "ORD_DVSN": "01",
            "ORD_QTY": str(int(req.quantity)),
            "ORD_UNPR": str(int(req.price)) if req.price is not None else "0",
        }

        # hashkey 붙이기(요구되는 환경 대비)
        try:
            headers["hashkey"] = self._hashkey(body)
        except Exception:
            # hashkey가 강제 아닐 수도 있어 안전하게 진행(서버가 요구하면 여기서 실패할 것)
            pass

        data = self._post("/uapi/domestic-stock/v1/trading/order-cash", headers=headers, json=body)  # :contentReference[oaicite:7]{index=7}

        # 결과 파싱: 환경마다 output 형태가 달라서 최소한의 공통 처리
        rt_cd = str(data.get("rt_cd", ""))
        msg = str(data.get("msg1", ""))

        ok = (rt_cd == "0")
        order_no = None
        out = data.get("output") or {}
        for key in ["ODNO", "odno", "order_no"]:
            if key in out:
                order_no = out.get(key)
                break

        return OrderResult(
            success=ok,
            message=msg,
            order_id=str(order_no) if order_no else None,
            raw=data,
        )
    def get_order_status(
            self,
            order_id:str,
            inqr_start_dt: Optional[str] = None,
            inqr_end_dt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        주문번호(ODNO) 기준으로 주문/체결 상태를 조회한다.
        - API: /uapi/domestic-stock/v1/trading/inquire-daily-ccld
        - TR_ID: 모의 VTTC8001R / 실전 TTTC8001R  (3개월 이내 체결/미체결 조회)
        참고 파라미터 구성은 KIS 예제에 기반. :contentReference[oaicite:1]{index=1}
        """
        
        start = inqr_start_dt or datetime.today().strftime("%Y%m%d")
        end = inqr_end_dt or datetime.today().strftime("%Y%m%d")

        tr_id = "VTTC8001R" if self.virtual else "TTTC8001R"  # 3개월 이내 주문체결조회 :contentReference[oaicite:2]{index=2}
        headers = self._auth_headers(tr_id=tr_id)

        def _to_int(x: Any) -> Optional[int]:
            if x is None:
                return None
            s = str(x).strip()
            if s == "":
                return None
            # 쉼표 제거 대응
            s = s.replace(",", "")
            try:
                return int(float(s))
            except Exception:
                return None
            
        def _get_odno(rec:Dict[str,Any]) -> Optional[str]:
            for k in ("ODNO", "odno", "order_no", "ord_no"):
                v = rec.get(k)
                if v is not None and str(v).strip() != "":
                    return str(v).strip()
            return None


        # 페이징 키(일반적으로는 1페이지에서 끝나지만, 안전하게 루프)
        fk100 = ""
        nk100 = ""

        last_resp: Dict[str, Any] = {}
        for _ in range(5):  # 과도 호출 방지(최대 5페이지)
            params = {
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "INQR_STRT_DT": start,
                "INQR_END_DT": end,
                "SLL_BUY_DVSN_CD": "00",   # 00:전체 / 01:매도 / 02:매수 :contentReference[oaicite:3]{index=3}
                "INQR_DVSN": "01",         # 00:역순 / 01:정순 :contentReference[oaicite:4]{index=4}
                "PDNO": "",                # 종목번호(선택)
                "CCLD_DVSN": "00",         # 00:전체 / 01:체결 / 02:미체결 :contentReference[oaicite:5]{index=5}
                "ORD_GNO_BRNO": "",
                "ODNO": str(order_id),
                "INQR_DVSN_3": "00",       # 00:전체(현금/융자 등) :contentReference[oaicite:6]{index=6}
                "INQR_DVSN_1": "0",        # 공란/0:전체(예제는 '0') :contentReference[oaicite:7]{index=7}
                "CTX_AREA_FK100": fk100,
                "CTX_AREA_NK100": nk100,
            }

            last_resp = self._get(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=headers,
                params=params,
            )

            # KIS 응답은 보통 output1/output2 중 하나가 list 형태(환경/버전별 차이)
            candidates = []
            for key in ("output1", "output2", "output"):
                v = last_resp.get(key)
                if isinstance(v, list):
                    candidates = v
                    break

            # dict 1건으로 오는 케이스 방어
            if isinstance(candidates, dict):
                candidates = [candidates]

            found: Optional[Dict[str, Any]] = None
            for rec in candidates or []:
                if not isinstance(rec, dict):
                    continue
                odno = _get_odno(rec)
                if odno == str(order_id):
                    found = rec
                    break
            if found:
                # 체결/미체결 수량 파싱(필드명이 환경별로 달라 후보를 폭넓게 잡음)
                ord_qty = None
                for k in ("ORD_QTY", "ord_qty", "ORD_QTY1", "ord_qty1", "tot_ord_qty"):
                    if k in found:
                        ord_qty = _to_int(found.get(k))
                        if ord_qty is not None:
                            break

                filled_qty = None
                for k in ("CCLD_QTY", "ccld_qty", "tot_ccld_qty", "TOT_CCLD_QTY", "exec_qty"):
                    if k in found:
                        filled_qty = _to_int(found.get(k))
                        if filled_qty is not None:
                            break

                unfilled_qty = None
                if ord_qty is not None and filled_qty is not None:
                    unfilled_qty = max(ord_qty - filled_qty, 0)

                # 상태 필드도 환경별 상이 → 후보 탐색
                status = None
                for k in ("ORD_STAT", "ord_stat", "ORD_STAT_CD", "ord_stat_cd", "status", "stts"):
                    v = found.get(k)
                    if v is not None and str(v).strip() != "":
                        status = str(v).strip()
                        break
                return {
                    "found": True,
                    "order_id": str(order_id),
                    "status": status,
                    "ord_qty": ord_qty,
                    "filled_qty": filled_qty,
                    "unfilled_qty": unfilled_qty,
                    "record": found,       # 해당 주문 레코드(원본)
                    "raw": last_resp,      # API 전체 원본
                }

            # 다음 페이지 키 갱신(없으면 종료)
            fk100 = str(last_resp.get("ctx_area_fk100") or last_resp.get("CTX_AREA_FK100") or "").strip()
            nk100 = str(last_resp.get("ctx_area_nk100") or last_resp.get("CTX_AREA_NK100") or "").strip()
            if not fk100 and not nk100:
                break

        return {
            "found": False,
            "order_id": str(order_id),
            "raw": last_resp,
        }

