from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import requests
import yaml


# --------------------------------------------------
# 경로 설정
#   __file__ : src/khms_trader/data/kis_downloader.py
#   parents[0] = data
#   parents[1] = khms_trader
#   parents[2] = src
#   parents[3] = 프로젝트 루트 (khms_trader)
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


# --------------------------------------------------
# 설정 / 시크릿 로딩
# --------------------------------------------------
@dataclass
class KISSecrets:
    app_key: str
    app_secret: str
    virtual: bool = True
    account_no: str | None = None
    account_product_code: str | None = None


def load_kis_secrets(path: Path | None = None) -> KISSecrets:
    """
    config/secrets.yaml에서 kis.* 정보를 로딩한다.

    기대하는 secrets.yaml 구조 예시:

    kis:
      app_key: "모의투자_APP_KEY"
      app_secret: "모의투자_APP_SECRET"
      virtual: true
      account_no: "12345678"
      account_product_code: "01"
    """
    if path is None:
        path = CONFIG_DIR / "secrets.yaml"

    if not path.exists():
        raise FileNotFoundError(f"secrets.yaml을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if "kis" not in data:
        raise KeyError("secrets.yaml에 'kis' 섹션이 없습니다. (kis.app_key 등)")

    kis = data["kis"]
    return KISSecrets(
        app_key=kis["app_key"],
        app_secret=kis["app_secret"],
        virtual=bool(kis.get("virtual", True)),
        account_no=kis.get("account_no"),
        account_product_code=kis.get("account_product_code"),
    )


# --------------------------------------------------
# 한국투자 Open API Client (데이터 조회용)
# --------------------------------------------------
class KoreaInvestDataClient:
    """
    시세/일봉/투자자 동향 같은 '조회용' REST API를 래핑하는 클라이언트.
    주문/계좌 관련은 broker.korea_invest_api.py에서 따로 처리한다.
    """

    def __init__(self, secrets: KISSecrets) -> None:
        self._secrets = secrets

        # 모의투자 vs 실전 도메인 결정
        # - 모의: https://openapivts.koreainvestment.com:29443
        # - 실전: https://openapi.koreainvestment.com:9443
        if secrets.virtual:
            self._base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self._base_url = "https://openapi.koreainvestment.com:9443"

        self._access_token: str | None = None
        self._session = requests.Session()
        
    # -----------------------
    # http 중복 코드 공통화
    # -----------------------

    def _request(self, method: str, url: str, headers: dict, params=None, data=None):
        resp = self._session.request(method, url, headers=headers, params=params, data=data)
        
        if resp.status_code != 200:
            # JSON 메시지 추출 시도
            try:
                err = resp.json()
                print(
                    f"[KIS ERROR] status={resp.status_code} "
                    f"msg_cd={err.get('msg_cd')} "
                    f"msg1={err.get('msg1')} "
                    f"body={err}"
                )
            except Exception:
                print(f"[KIS ERROR] status={resp.status_code} raw_body={resp.text}")

            resp.raise_for_status()

        # 정상
        return resp.json()
    # ----------------------------
    # OAuth 토큰 발급
    # ----------------------------
    def _ensure_access_token(self) -> str:
        """
        access_token이 없으면 발급, 있으면 기존 것 사용.
        (프로토타입 단계에서는 한 번 발급 후 그대로 재사용한다고 가정)
        """
        if self._access_token is not None:
            return self._access_token

        url = f"{self._base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json; charset=utf-8"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self._secrets.app_key,
            "appsecret": self._secrets.app_secret,
        }

        resp = self._session.post(url, headers=headers, data=json.dumps(body), timeout=5)
        resp.raise_for_status()
        data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(f"토큰 발급 실패: {data}")

        self._access_token = access_token
        return access_token


    # ----------------------------
    # 공통 헤더 구성
    # ----------------------------
    def _headers(self, tr_id: str) -> dict:
        token = self._ensure_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._secrets.app_key,
            "appsecret": self._secrets.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }

    # ----------------------------
    # 1) 국내주식 기간별 시세(일봉) 조회
    # ----------------------------
    def fetch_ohlcv_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adj_price: bool = True,
    ) -> pd.DataFrame:
        """
        국내주식기간별시세(일/주/월/년) API를 이용해
        일봉 OHLCV 데이터를 조회한다.

        - symbol: 종목코드 (예: "005930")
        - start_date, end_date: "YYYYMMDD" 형식 문자열
        """

        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        url = f"{self._base_url}{path}"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",        # J: 주식
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",           # D: 일봉
            "FID_ORG_ADJ_PRC": "1" if adj_price else "0",
        }

        headers = self._headers(tr_id="FHKST03010100")  # 기간별 시세 TR ID

        self._ensure_access_token()
        resp = safe_request_with_retry(
            self._session,
            url,
            headers=headers,
            params=params,
            max_retry=5,
            sleep_sec=0.3,
        )
        data = resp.json()

        # 응답 구조에 따라 'output2' 또는 'output'에 리스트가 들어있음
        output_list = data.get("output2") or data.get("output") or []
        if not output_list:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        rows = []
        for row in output_list:
            date_str = row.get("stck_bsop_date")
            if not date_str:
                continue

            try:
                date_val = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                continue

            rows.append(
                {
                    "date": date_val,
                    "open": float(row.get("stck_oprc", 0) or 0),
                    "high": float(row.get("stck_hgpr", 0) or 0),
                    "low": float(row.get("stck_lwpr", 0) or 0),
                    "close": float(row.get("stck_clpr", 0) or 0),
                    "volume": float(row.get("acml_vol", 0) or 0),
                }
            )

        df = pd.DataFrame(rows)
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    # ----------------------------
    # 2) 최근 30영업일 투자자 매매동향(외국인) 조회
    # ----------------------------
    def fetch_investor_trend_30d(self, symbol: str) -> pd.DataFrame:
        """
        [국내주식] 기본시세 > 주식현재가 투자자 API를 사용해
        최근 30일간 투자자 매매동향(일별)을 조회하고,
        (date, foreign_net_buy) 형태의 DataFrame으로 반환한다.

        반환 컬럼:
          - date: pandas.Timestamp
          - foreign_net_buy: float (외국인 순매수 수량)
        """
        url = f"{self._base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        headers = self._headers(tr_id="FHKST01010900")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",   # J: 주식/ETF/ETN
            "FID_INPUT_ISCD": symbol,        # 6자리 종목코드
        }

        self._ensure_access_token()
        resp = safe_request_with_retry(
            self._session,
            url,
            headers=headers,
            params=params,
            max_retry=5,
            sleep_sec=0.3,
        )
        data = resp.json()

        output = data.get("output", [])
        if isinstance(output, dict):
            output = [output]

        if not output:
            return pd.DataFrame(columns=["date", "foreign_net_buy"])

        df = pd.DataFrame(output)

        # 필요한 컬럼만 남기고 rename
        if "stck_bsop_date" not in df.columns or "frgn_ntby_qty" not in df.columns:
            # 응답 스키마가 예상과 다를 때 안전하게 빈 DF 반환
            return pd.DataFrame(columns=["date", "foreign_net_buy"])

        df = df[["stck_bsop_date", "frgn_ntby_qty"]].copy()
        df.rename(
            columns={
                "stck_bsop_date": "date",
                "frgn_ntby_qty": "foreign_net_buy",
            },
            inplace=True,
        )

        # 타입 정리
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
        df["foreign_net_buy"] = pd.to_numeric(
            df["foreign_net_buy"], errors="coerce"
        ).fillna(0.0)

        # 날짜 NaN은 제거
        df = df.dropna(subset=["date"])

        # 날짜 오름차순 정렬
        df = df.sort_values("date").reset_index(drop=True)
        return df

     # ----------------------------
    # 3) OHLCV + 외국인 순매수 merge
    # ----------------------------
    def fetch_ohlcv_with_foreign(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        일봉 OHLCV에 외국인 순매수(foreign_net_buy)를 merge해서 반환.

        - start, end: 'YYYYMMDD' 문자열
        - 내부에서:
            1) 기간별 시세 일봉 조회 (fetch_ohlcv_daily)
            2) 최근 30영업일 투자자 매매동향 조회 (fetch_investor_trend_30d)
            3) date 기준 left-join
        """

        # 1) 일봉 OHLCV 조회
        ohlcv = self.fetch_ohlcv_daily(symbol, start_date=start, end_date=end)
        if ohlcv is None or ohlcv.empty:
            df = ohlcv.copy() if ohlcv is not None else pd.DataFrame()
            df["foreign_net_buy"] = 0.0
            return df

        # 2) 투자자 매매동향 조회
        inv = self.fetch_investor_trend_30d(symbol)
        if inv is None or inv.empty:
            df = ohlcv.copy()
            df["foreign_net_buy"] = 0.0
            return df

        # 3) date 컬럼 존재 여부 방어
        if "date" not in ohlcv.columns:
            raise KeyError(f"[kis_downloader] {symbol}: ohlcv 데이터에 'date' 컬럼이 없습니다.")
        if "date" not in inv.columns:
            raise KeyError(f"[kis_downloader] {symbol}: 투자자매매동향 데이터에 'date' 컬럼이 없습니다.")

        # 4) date 타입 강제 통일 (여기가 핵심 수정 부분)
        ohlcv = ohlcv.copy()
        inv = inv.copy()

        # ohlcv 쪽 date: 보통 이미 datetime64[ns]일 가능성이 크지만, 확실히 맞춰줌
        ohlcv["date"] = pd.to_datetime(ohlcv["date"], errors="coerce")

        # inv 쪽 date: 문자열(예: '20240105')인 경우가 많으므로 datetime으로 통일
        inv["date"] = pd.to_datetime(inv["date"], errors="coerce")

        # 혹시 변환 과정에서 NaT가 생기면, 그 행은 join 대상에서 제외
        ohlcv = ohlcv.dropna(subset=["date"])
        inv = inv.dropna(subset=["date"])

        # 필요 없는 컬럼이 많다면 여기서 슬림하게 줄여도 됨
        # 예: inv = inv[["date", "foreign_net_buy"]]
        if "foreign_net_buy" not in inv.columns:
            # 투자자매매동향에 foreign_net_buy 자체가 없는 경우 방어
            inv["foreign_net_buy"] = 0.0

        # 5) merge: date 기준 left join
        df = pd.merge(
            ohlcv,
            inv[["date", "foreign_net_buy"]],
            on="date",
            how="left",
        )

        # 6) NaN -> 0.0 대체
        df["foreign_net_buy"] = df["foreign_net_buy"].fillna(0.0)

        return df



# --------------------------------------------------
# CSV 저장 유틸 (원하면 다른 곳에서도 재사용 가능)
# --------------------------------------------------
def save_df_to_raw_csv(symbol: str, df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{symbol}.csv"

    df_to_save = df.copy()
    df_to_save.to_csv(path, index=False, encoding="utf-8-sig")
    
    # date를 문자열로 통일
    if pd.api.types.is_datetime64_any_dtype(df_to_save["date"]):
        df_to_save["date"] = df_to_save["date"].dt.date.astype(str)
    else:
        df_to_save["date"] = df_to_save["date"].astype(str)

    df_to_save.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[kis_downloader] saved: {path} (rows={len(df_to_save)})")
    return path


def download_and_save_symbol(
    client: KoreaInvestDataClient,
    symbol: str,
    start_date: str,
    end_date: str,
) -> Path | None:
    """
    심볼 하나에 대해 KIS에서 데이터를 조회해 raw/{symbol}.csv로 저장.
    - start_date, end_date: YYYYMMDD
    """
    df = client.fetch_ohlcv_with_foreign(symbol, start=start_date, end=end_date)
    if df.empty:
        print(f"[kis_downloader] {symbol}: 조회 결과 없음 (저장 생략).")
        return None

    return save_df_to_raw_csv(symbol, df)

from requests import HTTPError

def download_and_save_symbols(
    symbols: List[str],
    start_date: str,
    end_date: str,
) -> None:
    """
    여러 심볼에 대해 순차적으로 다운로드 + 저장.
    """
    secrets = load_kis_secrets()
    client = KoreaInvestDataClient(secrets)

    for sym in symbols:
        try:
            print(f"[kis_downloader] {sym}: 일봉 + 투자자매매동향 조회 시작...")
            download_and_save_symbol(client, sym, start_date, end_date)
        except HTTPError as e:
            status = e.response.status_code
            print(f"[kis_downloader] {sym}: HTTP {status} 에러 -> {e}")
            if status >= 500:
                print(f"[kis_downloader] {sym}: 서버 내부 오류이므로 이 종목은 건너뜁니다.")
        except Exception as e:
            print(f"[kis_downloader] {sym}: 일반 예외 발생 -> {e}")

import time
import requests

def safe_request_with_retry(session, url, headers, params, max_retry=3, sleep_sec=0.3):
    for i in range(max_retry):
        resp = session.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            return resp
        if 500 <= resp.status_code < 600:
            # 서버 에러이면 잠깐 쉬었다가 재시도
            time.sleep(sleep_sec)
            continue
        # 그 외 에러(400, 401 등)는 바로 반환
        resp.raise_for_status()
    # 여기까지 왔다는 건 max_retry 번 다 실패
    resp.raise_for_status()

# --------------------------------------------------
# CLI 진입점
#   예시:
#     python -m khms_trader.data.kis_downloader 005930 000660 --start 20240101 --end 20240201
# --------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="KIS API를 이용해 data/raw 에 일봉 + 외국인 순매수 데이터를 쌓는 유틸리티"
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="종목코드 리스트 (예: 005930 000660 035420)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="조회 시작일 (YYYYMMDD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="조회 종료일 (YYYYMMDD)",
    )

    args = parser.parse_args()
    download_and_save_symbols(args.symbols, args.start, args.end)


if __name__ == "__main__":
    main()
