from .dataset_loader import load_universe, load_raw
from ..strategies.hsms import HSMSStrategy
from .portfolio import Portfolio
import pandas as pd

class Backtester:

    def __init__(self, rebalance_dates, strategy=None):
        self.rebalance_dates = rebalance_dates
        self.strategy = strategy or HSMSStrategy()
        self.portfolio = Portfolio()

    def run(self):
        for date_str in self.rebalance_dates:

            # 1) 유니버스 로딩
            uni = load_universe(date_str)
            tickers = uni["ticker"].astype(str).tolist()

            signals = {}
            price_map = {}

            for symbol in tickers:

                # 2) raw 시계열 로딩
                df = load_raw(symbol)

                # 2-1) 리밸런싱 날짜 이전 데이터만 사용
                df_cut = df[df["date"] <= pd.to_datetime(date_str)]
                if df_cut.empty:
                    continue

                # 2-2) 전략 시그널 계산
                sig = self.strategy.generate_signal(df_cut)
                signals[symbol] = sig

                # 2-3) 오늘 종가 추출
                today_row = df_cut[df_cut["date"] == df_cut["date"].max()]
                price_map[symbol] = float(today_row["close"].iloc[0])

            # 3) 포트폴리오 업데이트
            self.portfolio.update(signals, price_map, date_str)

        return self.portfolio.get_history()
