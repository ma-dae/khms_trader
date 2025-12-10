"""
khms_trader 메인 엔트리포인트

예시:
    백테스트 모드 실행
        python -m khms_trader.main backtest

    실시간(또는 실매매) 모드 실행
        python -m khms_trader.main live
"""

import argparse


def run_backtest() -> None:
    """백테스트 실행 함수 (임시 버전).

    나중에:
        - 데이터 로드
        - 전략 적용
        - 성능 지표 출력
    등을 이 함수 안에서 호출하도록 구조를 확장할 예정.
    """
    print("[khms_trader] 백테스트 모드로 실행되었습니다.")
    print("→ 이후 단계에서 backtest 엔진과 전략을 여기서 호출하게 됩니다.")


def run_live() -> None:
    """실시간 / 실매매 실행 함수 (임시 버전).

    나중에:
        - 한국투자증권 API 연동
        - 종목 스캔 후 주문
        - 로그 기록
    등을 이 함수 안에서 호출하게 됩니다.
    """
    print("[khms_trader] 라이브(실시간) 모드로 실행되었습니다.")
    print("→ 이후 단계에서 한국투자증권 API를 붙여서 주문을 실행하게 됩니다.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="khms_trader - 한국 주식 스윙 자동매매 프로젝트"
    )
    parser.add_argument(
        "mode",
        choices=["backtest", "live"],
        help="실행 모드 선택: backtest | live",
    )

    args = parser.parse_args()

    if args.mode == "backtest":
        run_backtest()
    elif args.mode == "live":
        run_live()
    else:
        # argparse choices 덕분에 사실상 여기 도달하진 않지만 방어 코드
        raise ValueError(f"지원하지 않는 모드입니다: {args.mode}")


if __name__ == "__main__":
    main()
