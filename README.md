KHMS Trader (KIS Virtual · Next-Open Strategy)
=============================================

본 프로젝트는 한국투자증권(KIS) 모의투자(virtual) 환경에서
Next-Open(다음날 시가 기준) 전략을 수동 또는 자동으로 운영하기 위한
주식 자동매매 및 대시보드 프로젝트입니다.

전략 로직, 주문 실행, 대시보드, 알림을 분리하여
운영 안정성과 디버깅 용이성을 최우선으로 설계했습니다.


1. 프로젝트 개요
-----------------
- 전략 방식: Next-Open (전일 장 마감 후 plan 생성 → 다음날 시가 실행)
- 대상 시장: KOSDAQ
- 브로커 구성
  · 운영/대시보드 조회: korea_invest (virtual)
  · 테스트/드라이런: paper 또는 virtual
- 주요 기능
  · Plan 생성
  · 주문 실행
  · 상태 점검
  · Streamlit 대시보드
  · 텔레그램 알림(선택)


2. 디렉토리 구조
-----------------

khms_trader/
  src/
    khms_trader/
      broker/
        - KIS / Paper broker 구현
      data/
        - 데이터 수집 로직
      execution/
        - plan 실행 로직
      notifications/
        - Telegram notifier
      config/
        - settings / secrets loader

  scripts/
    prepare_next_open_plan.py
      - 다음 거래일 plan 생성
    execute_next_open_plan.py
      - plan 기반 실제 주문 실행
    run_virtual_live.py
      - 계좌 상태 점검 / 간이 실행
    run_virtual_next_open_forever.py
      - 상시 스케줄러
    run_dashboard.py
      - Streamlit 대시보드
    tools/
      sell_out_legacy.py
        - 관리자용 계좌 정리 스크립트

  plans/
    - 생성된 next_open plan 파일

  logs/
    - 실행 로그

  data/
    universe/
      - 유니버스 CSV

  reports/
    - 이벤트 / 리포트

  settings.yaml
    - 일반 설정

  secrets.yaml
    - API / Telegram 비밀정보 (gitignore)

  README.txt



3. 환경 설정
-------------
Python 환경:
  conda activate khms_trader

settings.yaml 예시:
  broker.provider: paper | korea_invest
  broker.env: virtual | real
  trading.fill_mode: next_open

secrets.yaml:
  - korea_invest virtual 계좌 정보
  - telegram token / chat_id


4. 운영 방식
-------------

[수동 운영 - 권장]

(1) 매일 장 마감 전 (15:40)
  python scripts/prepare_next_open_plan.py --universe-limit 200 --qty 1

(2) 다음날 장 시작 직후 (09:01)
  python scripts/execute_next_open_plan.py

※ 보유하지 않은 종목의 sell 신호는 자동으로 skip됨


[자동 운영 - 상시 스케줄러]

  python scripts/run_virtual_next_open_forever.py --times 15:40 09:01 --qty 1 --universe-limit 200

- 15:40: plan 생성
- 09:01: plan 실행
- 터미널 점유 상태는 정상 동작


5. 상태 점검 및 대시보드
-----------------------

대시보드 실행:
  streamlit run scripts/run_dashboard.py

- 항상 KIS virtual 계좌 기준 조회
- 표시 항목
  · 현금 (dnca_tot_amt)
  · 보유 종목/수량
  · 총자산 (tot_evlu_amt)
  · 최신 plan 및 로그

※ Streamlit 실행 시 해당 터미널은 점유됨


주문 없이 상태 확인:
  python scripts/run_virtual_live.py --universe-limit 10


6. 계좌 초기화 및 예외 대응
---------------------------

- KIS 모의계좌는 로컬에서 리셋 불가
- 원치 않는 보유 발생 시:
  1) 전량 매도 (권장)
  2) legacy holding으로 분리 관리

관리자용 스크립트:
  scripts/tools/sell_out_legacy.py
  - 일반 운영 중 사용 금지
  - 계좌 복구/정리 시에만 사용


7. 텔레그램 알림
----------------
- settings/secrets 기반 자동 로드
- 네트워크 환경에 따라 실패 가능
- 알림 실패 시에도 매매 로직은 중단되지 않음


8. 핵심 운영 원칙
------------------
- plan 생성과 실행은 반드시 분리
- sell 신호 ≠ 실제 매도
- 실험 상태와 운영 계좌 분리
- 처음 실행 시에도 사고 주문 방지


9. 현재 상태 요약
------------------
- KIS virtual 연동 정상
- Next-Open 파이프라인 정상
- 대시보드 KIS 기준 고정
- 현금 / 총자산 분리 완료
- legacy 보유 정리 완료
- 수동/자동 운영 루트 확정


10. 향후 확장 아이디어
----------------------
- 실계좌(real) 전환
- ledger 기반 포지션 관리
- 주문 실패 자동 재시도
- 전략 분리
- 성과 시각화 대시보드 확장


본 프로젝트는 "사고 안 나는 자동매매"를 최우선 목표로 설계되었습니다.
