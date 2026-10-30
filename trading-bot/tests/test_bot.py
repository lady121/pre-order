import json
from types import SimpleNamespace

from bot.agents.market_data import synthetic_prices
from bot.orchestrator import Config, TradingTeam


def test_backtest_runs_and_reports():
    team = TradingTeam(synthetic_prices(400, seed=1))
    r = team.run()
    assert r["trades"] > 0
    assert 0 <= r["max_drawdown"] < 1
    assert len(team.execution.equity_curve) == 400


def test_orders_fill_on_next_bar_open():
    data = synthetic_prices(300, seed=2)
    team = TradingTeam(data)
    team.run()
    by_step = {}
    for m in team.bus.log:
        by_step.setdefault(m.topic, []).append(m)
    for fill in by_step["order.filled"]:
        if fill.payload["reason"] == "stop loss":
            continue
        open_px = data["open"].iloc[fill.step]
        assert abs(fill.payload["price"] / open_px - 1) < 0.001


def test_risk_manager_caps_position_size():
    team = TradingTeam(synthetic_prices(400, seed=3), Config(max_position=0.3))
    team.run()
    weights = [m.payload["target_weight"] for m in team.bus.log if m.topic == "order.approved"]
    assert max(abs(w) for w in weights) <= 0.3


def test_drawdown_halt_stops_trading():
    team = TradingTeam(synthetic_prices(600, seed=4), Config(max_drawdown=0.01))
    team.run()
    assert team.risk.halted
    halt = next(m.step for m in team.bus.log if m.topic == "risk.halt")
    assert team.execution.shares == 0
    assert not any(m.topic == "order.filled" and m.step > halt + 1 for m in team.bus.log)


def test_llm_strategist_feeds_portfolio_manager():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        text = json.dumps({"score": 0.9, "confidence": 0.8, "rationale": "uptrend"})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])

    team = TradingTeam(synthetic_prices(120, seed=5), Config(use_llm=True, llm_every=10))
    team.strategist._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    team.run()
    assert calls and calls[0]["model"] == "claude-opus-5-5"
    assert len(calls) <= 120 // 10 + 1
    assert any(m.topic == "signal.strategist" for m in team.bus.log)
