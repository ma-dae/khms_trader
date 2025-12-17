# KHMS Trader (KIS Virtual · Next-Open Strategy)

한국투자증권(KIS) **모의투자(virtual)** 환경에서  
**Next-Open(다음날 시가 기준)** 전략을 수동 또는 자동으로 운영하기 위한  
주식 자동매매/대시보드 프로젝트입니다.

본 프로젝트는 **전략 로직, 주문 실행, 대시보드, 텔레그램 알림**을 분리해  
운영 안정성과 디버깅 용이성을 우선으로 설계되었습니다.

---

## 1. 프로젝트 개요

- **전략 방식**: Next-Open (전일 장 마감 후 plan 생성 → 다음날 시가 실행)
- **대상 시장**: KOSDAQ
- **브로커**
  - 운영/대시보드 조회: `korea_invest (virtual)`
  - 테스트/백테스트/드라이런: `paper` 또는 `virtual`
- **주요 구성**
  - Plan 생성 (`prepare_next_open_plan`)
  - 주문 실행 (`execute_next_open_plan`)
  - 실시간/상태 점검 (`run_virtual_live`)
  - 대시보드 (Streamlit)
  - 텔레그램 알림 (옵션)

---

## 2. 디렉토리 구조
khms_trader/
├─ src/khms_trader/
│ ├─ broker/ # KIS / Paper broker
│ ├─ data/ # 데이터 수집
│ ├─ execution/ # plan 실행 로직
│ ├─ notifications/ # Telegram notifier
│ └─ config/ # settings / secrets loader
│
├─ scripts/
│ ├─ prepare_next_open_plan.py
│ ├─ execute_next_open_plan.py
│ ├─ run_virtual_live.py
│ ├─ run_virtual_next_open_forever.py
│ ├─ run_dashboard.py
│ └─ tools/
│ └─ sell_out_legacy.py # (관리자용) 계좌 정리 스크립트
│
├─ plans/ # 생성된 plan 파일
├─ logs/ # 실행 로그
├─ data/universe/ # 유니버스 CSV
├─ reports/ # 이벤트/리포트
├─ settings.yaml # 일반 설정
├─ secrets.yaml # API/Telegram 비밀정보 (gitignore)
└─ README.md


---

## 3. 환경 설정

### 3.1 Python 환경
```bash
conda activate khms_trader

### 3.2 setting.yaml (예시)
broker:
  provider: paper        # paper | korea_invest
  env: virtual           # virtual | real

market: "KRX"
base_currency: "KRW"

trading:
  fee_bps: 14.7
  tax_bps: 15.0
  slippage_bps: 10.0
  fill_mode: next_open

live:
  loop_sec: 60
  max_positions: 8

### 3.3 secrets.yaml (필수, gitignore)
korea_invest:
  virtual:
    app_key: "..."
    app_secret: "..."
    account_no: "..."
    account_product_code: "..."

telegram:
  enabled: true
  token: "..."
  chat_id: "..."

4. 운영 방식
4.1 수동 운영 (권장·안정)
① 매일 장 마감 전 (15:40)

다음 거래일 plan 생성

python scripts/prepare_next_open_plan.py --universe-limit 200 --qty 1

② 다음날 장 시작 직후 (09:01)

plan 실행 (실제 주문)

python scripts/execute_next_open_plan.py


⚠️ 보유하지 않은 종목의 sell 신호는 자동으로 skipped 됩니다.

4.2 자동 운영 (상시 스케줄러)
python scripts/run_virtual_next_open_forever.py --times 15:40 09:01 --qty 1 --universe-limit 200


15:40 → plan 생성

09:01 → plan 실행

터미널 점유 상태가 정상 동작

5. 상태 점검 & 대시보드
5.1 대시보드 실행 (조회 전용)
streamlit run scripts/run_dashboard.py
항상 KIS virtual 계좌 기준으로 조회

표시 항목:

현금 (dnca_tot_amt)

보유 종목/수량

총자산 (tot_evlu_amt)

최신 plan / 로그

Streamlit 실행 시 해당 터미널은 점유됩니다.
다른 작업은 새 터미널에서 실행하세요.

5.2 주문 없이 상태 확인
python scripts/run_virtual_live.py --universe-limit 10

6. 계좌 초기화 / 예외 대응
6.1 원치 않는 보유가 생겼을 경우

KIS 모의계좌는 로컬 리셋 불가

해결 방법:

전량 매도 (권장)

legacy holding으로 분리 관리

6.2 관리자용 정리 스크립트
scripts/tools/sell_out_legacy.py


일반 운영 중 사용 금지

계좌 복구/정리 시에만 사용


7. 텔레그램 알림

TelegramNotifier()는 settings/secrets 기반 자동 로드

네트워크 환경에 따라 연결 실패 가능

실패해도 매매 로직은 중단되지 않도록 설계됨

8. 핵심 운영 원칙 (중요)

plan 생성과 실행은 반드시 분리

sell 신호 ≠ 실제 매도 (보유 여부 필터링)

실험/드라이런 상태는 운영 계좌와 분리

“처음 실행” 시에도 사고 주문이 나가지 않도록 방어 로직 유지

9. 현재 상태 요약

 KIS virtual 연동 정상

 Next-Open plan → 실행 파이프라인 정상

 대시보드 KIS 기준 고정

 현금 / 총자산 분리

 초기 legacy 보유 정리 완료

 수동/자동 운영 루트 확정