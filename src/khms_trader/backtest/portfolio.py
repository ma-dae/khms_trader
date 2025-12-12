class Portfolio:
    def __init__(self, initial_cash=10000000):
        self.cash = initial_cash
        self.positions = {}  # symbol → {"qty":..., "avg_price":...}
        self.history = []

    def update(self, signals: dict, price_map: dict, date):
        """
        signals: {"005930": 1, "000660": -1, ...}
        price_map: {"005930": 71200, ...}
        """

        for symbol, sig in signals.items():
            price = price_map.get(symbol)
            if price is None:
                continue

            # 매수
            if sig == 1:
                qty = self.cash // price
                if qty > 0:
                    self.positions[symbol] = {
                        "qty": qty,
                        "avg_price": price,
                    }
                    self.cash -= qty * price

            # 매도
            elif sig == -1 and symbol in self.positions:
                qty = self.positions[symbol]["qty"]
                self.cash += qty * price
                del self.positions[symbol]

        # 평가금액 계산
        equity = self.cash
        for symbol, pos in self.positions.items():
            if symbol in price_map:
                equity += pos["qty"] * price_map[symbol]

        self.history.append({
            "date": date,
            "cash": self.cash,
            "equity": equity,
        })

    def get_history(self):
        return self.history
