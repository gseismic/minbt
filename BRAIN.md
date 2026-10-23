# 思考
- plugins中binance不同的数据源时候可以抽象出接口，然后分别实现这个接口，更加清晰。
- Exchange应该包含replay模式和live模式，用来设置配置，run后没有区别
- 应该支持多Exchange，可以做跨市场交易 
```python
exchange1 = binance.Exchange()
exchange2 = astock.Exchange()

exchange = SuperExchange([exchange1, exchange2])
exchange.add_strategy(Strategy, Parameters({'EMA_n': 10}))
exchange.run() 
```
