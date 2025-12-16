def format_signal(symbol, strategy, signal, price):
    return (
        f"[SIGNAL]\n"
        f"- symbol: {symbol}\n"
        f"- strategy: {strategy}\n"
        f"- signal: {signal}\n"
        f"- price: {price}"
    )

def format_error(symbol, stage, message):
    return (
        f"[ERROR]\n"
        f"- symbol: {symbol}\n"
        f"- stage: {stage}\n"
        f"- message: {message}"
    )
