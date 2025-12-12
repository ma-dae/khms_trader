import argparse

from .execution.runner import run_paper_trading_auto_universe


def run_backtest() -> None:
    # 아직은 미구현. 나중에 backtest 엔진 붙이면 여기서 호출.
    print("[khms_trader] 백테스트 모드 (구현 예정)")


def run_live() -> None:
    """
    현재는 실전 계좌가 아니라
    - 자동 스크리너(거래대금·변동성 상위) 기반 유니버스 선정
    - HSMS 전략 + PaperBroker 모의투자
    를 수행한다.
    """
    print("[khms_trader] LIVE 모드 (PaperBroker + 자동 스크리너) 시작")
    run_paper_trading_auto_universe()
    print("[khms_trader] LIVE 모드 종료")


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


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    from khms_trader.backtest.hsms_single import HSMSSingleBacktester
    from khms_trader.backtest.dataset_loader import load_raw

    df = load_raw("005930")
    bt = HSMSSingleBacktester("005930")
    eq = bt.run(df)
    print(eq.tail())
