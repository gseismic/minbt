import pandas as pd
import polars as pl
import pytest

from minbt import Exchange, Strategy, Broker


class EmptyDataStrategy(Strategy):
    def on_init(self):
        self.initialized = True

    def on_finish(self):
        self.finished = True


class MultiAssetStrategy(Strategy):
    def on_init(self):
        self.row_snapshots = []
        self.bar_snapshots = []

    def on_data(self, row):
        self.row_snapshots.append(
            (
                row['dt'],
                row['symbol'],
                self.broker.get_last_price('A'),
                self.broker.get_last_price('B'),
                self.exchange.get_current_dt(),
            )
        )

    def on_bar(self, dt, rows_by_symbol):
        self.bar_snapshots.append(
            (
                dt,
                list(rows_by_symbol.keys()),
                self.broker.get_last_price('A'),
                self.broker.get_last_price('B'),
            )
        )


class DtCaptureStrategy(Strategy):
    def on_init(self):
        self.dts = []

    def on_data(self, row):
        self.dts.append(self.exchange.get_current_dt())


class CountingBroker(Broker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.price_updates = []

    def on_new_price(self, symbol, price, dt=None):
        self.price_updates.append((symbol, price, dt))
        return super().on_new_price(symbol, price, dt)


def _duplicate_bar_rows():
    return [
        {'dt': '2026-01-01', 'symbol': 'A', 'close': 100.0},
        {'dt': '2026-01-01', 'symbol': 'A', 'close': 101.0},
    ]


def _make_duplicate_bar_data(kind):
    rows = _duplicate_bar_rows()
    if kind == 'pandas':
        return pd.DataFrame(rows)
    if kind == 'polars':
        try:
            return pl.DataFrame(rows)
        except Exception as exc:
            pytest.skip(f'polars DataFrame unavailable: {exc}')
    return rows


def test_exchange_run_empty_data_does_not_divide_by_zero():
    """测试空行情数据仍可完成初始化和结束回调"""
    exchange = Exchange()
    strategy = EmptyDataStrategy(strategy_id='empty', broker=Broker(initial_cash=1000, fee_rate=0))
    data = pd.DataFrame(columns=['dt', 'symbol', 'close'])

    exchange.set_data(data, date_key='dt')
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.initialized
    assert strategy.finished


def test_exchange_run_requires_data():
    """测试未设置行情数据时给出明确错误"""
    exchange = Exchange()

    with pytest.raises(ValueError, match='set_data'):
        exchange.run()


def test_exchange_updates_full_bar_before_strategy_callbacks():
    """测试多标的同一时间点先完整更新价格，再触发策略"""
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = MultiAssetStrategy(strategy_id='multi', broker=broker)
    data = pd.DataFrame(
        [
            {'dt': '2026-01-01', 'symbol': 'A', 'close': 100.0},
            {'dt': '2026-01-01', 'symbol': 'B', 'close': 200.0},
            {'dt': '2026-01-02', 'symbol': 'A', 'close': 110.0},
            {'dt': '2026-01-02', 'symbol': 'B', 'close': 190.0},
        ]
    )

    exchange.set_data(data, date_key='dt')
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.row_snapshots[0] == ('2026-01-01', 'A', 100.0, 200.0, '2026-01-01')
    assert strategy.row_snapshots[1] == ('2026-01-01', 'B', 100.0, 200.0, '2026-01-01')
    assert strategy.bar_snapshots == [
        ('2026-01-01', ['A', 'B'], 100.0, 200.0),
        ('2026-01-02', ['A', 'B'], 110.0, 190.0),
    ]
    assert strategy.get_hist_equity() == [1000, 1000]


def test_exchange_set_data_requires_symbol_and_close():
    """测试行情数据缺必需字段时尽早报错"""
    exchange = Exchange()
    data = pd.DataFrame([{'dt': '2026-01-01', 'symbol': 'A'}])

    with pytest.raises(ValueError, match='close'):
        exchange.set_data(data, date_key='dt')


@pytest.mark.parametrize(
    "data_kind",
    ['pandas', 'polars', 'list'],
)
def test_exchange_set_data_rejects_duplicate_symbol_in_same_bar(data_kind):
    """测试同一时间截面内同一 symbol 重复时尽早报错"""
    exchange = Exchange()
    data = _make_duplicate_bar_data(data_kind)

    with pytest.raises(ValueError, match='duplicate'):
        exchange.set_data(data, date_key='dt')


def test_exchange_without_date_key_uses_sequential_row_number_for_pandas():
    """测试不传 date_key 时 pandas 也使用顺序行号而不是 DataFrame index"""
    exchange = Exchange()
    strategy = DtCaptureStrategy(strategy_id='dt')
    data = pd.DataFrame(
        [
            {'symbol': 'A', 'close': 100.0},
            {'symbol': 'A', 'close': 101.0},
        ],
        index=[10, 20],
    )

    exchange.set_data(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.dts == [0, 1]


def test_exchange_runs_list_dict_data_without_polars_conversion():
    """测试 list[dict] 输入可原生运行且按 date_key 排序"""
    exchange = Exchange()
    strategy = DtCaptureStrategy(strategy_id='list_data')
    data = [
        {'dt': '2026-01-02', 'symbol': 'A', 'close': 101.0},
        {'dt': '2026-01-01', 'symbol': 'A', 'close': 100.0},
    ]

    exchange.set_data(data, date_key='dt')
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.dts == ['2026-01-01', '2026-01-02']


def test_exchange_updates_shared_broker_once_per_bar():
    """测试多个策略共享同一 broker 时行情更新按 broker 去重"""
    exchange = Exchange()
    broker = CountingBroker(initial_cash=1000, fee_rate=0)
    strategy_a = Strategy(strategy_id='a', broker=broker)
    strategy_b = Strategy(strategy_id='b', broker=broker)
    data = pd.DataFrame(
        [
            {'dt': '2026-01-01', 'symbol': 'A', 'close': 100.0},
            {'dt': '2026-01-01', 'symbol': 'B', 'close': 200.0},
            {'dt': '2026-01-02', 'symbol': 'A', 'close': 110.0},
            {'dt': '2026-01-02', 'symbol': 'B', 'close': 190.0},
        ]
    )

    exchange.set_data(data, date_key='dt')
    exchange.add_strategy(strategy_a)
    exchange.add_strategy(strategy_b)
    exchange.run()

    assert broker.price_updates == [
        ('A', 100.0, '2026-01-01'),
        ('B', 200.0, '2026-01-01'),
        ('A', 110.0, '2026-01-02'),
        ('B', 190.0, '2026-01-02'),
    ]
