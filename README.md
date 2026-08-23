# 📈 Stock Analysis & Backtesting Dashboard

An interactive stock analysis and trading-strategy backtesting dashboard built with **Python, Streamlit, Plotly, pandas, and yfinance**.

The application fetches market data, visualises technical indicators, backtests multiple trading strategies, applies configurable risk management, and evaluates strategy performance against Buy & Hold — all through an interactive web dashboard.

---

## ✨ Features

### 📊 Stock Analysis

- Fetch historical market data using `yfinance`
- Supports US and Indian stocks such as:
  - `AAPL`
  - `TSLA`
  - `TCS.NS`
  - `RELIANCE.NS`
- Multiple analysis periods from `5d` to `max`
- Line and candlestick price charts
- Current price, daily high, daily low and price change
- Company information:
  - Company name
  - Sector
  - Industry
  - Market capitalisation
- Download stock data as CSV
- Market data cached for 5 minutes to reduce unnecessary API calls

---

## 📉 Technical Indicators

The dashboard supports:

- **SMA 20**
- **SMA 50**
- **EMA 20**
- **EMA 50**
- **RSI 14**
- **MACD**
  - MACD Line
  - Signal Line
  - Histogram
- **Bollinger Bands**
- **ATR 14**
- **Volume**

Interactive charts are built using **Plotly**, allowing zooming, hovering and detailed exploration of price movements and indicators.

The application also fetches additional historical data in the background so indicators such as SMA 50 can be calculated correctly even when a shorter display period is selected.

---

## 🔄 Backtesting Engine

The dashboard includes a custom backtesting engine supporting multiple trading strategies.

### Supported Strategies

#### 1. SMA Crossover

Buy when the short-period SMA is above the long-period SMA.

Sell when the short-period SMA falls below the long-period SMA.

Users can configure both SMA periods.

#### 2. EMA Crossover

Similar to the SMA crossover strategy but uses Exponential Moving Averages.

Users can configure the short and long EMA periods.

#### 3. RSI Strategy

- Buy when RSI falls below the configurable oversold level
- Hold the position
- Sell when RSI rises above the configurable overbought level

RSI period and threshold levels can be customised.

#### 4. MACD Strategy

Buy when:

`MACD Line > Signal Line`

Sell when:

`MACD Line < Signal Line`

Fast EMA, slow EMA and signal periods can all be configured.

#### 5. Bollinger Bands Strategy

- Buy when price falls below the lower Bollinger Band
- Hold the position
- Sell when price rises above the upper Bollinger Band

The Bollinger period and standard-deviation multiplier are configurable.

---

## 🛡️ Risk Management

The backtesting engine supports configurable risk-management rules.

### Stop Loss

Users can define a percentage stop loss.

The engine checks:

- Daily Open
- Daily Low

If the stock gaps below the stop-loss level, the trade exits at the opening price rather than assuming execution at the original stop price.

### Take Profit

Users can define a percentage take-profit level.

The engine checks:

- Daily Open
- Daily High

Gap-up situations are also handled using the actual opening price.

### Same-Candle Stop Loss and Take Profit

Daily OHLC data does not reveal whether the day's High or Low occurred first.

Therefore, when both stop loss and take profit are reached during the same candle, the backtest uses a conservative assumption and processes the **Stop Loss first**.

---

## 💰 Transaction Costs

A configurable transaction-cost percentage can be included in the backtest.

The dashboard displays both:

- Strategy return before transaction cost
- Strategy return after transaction cost

This makes the backtest more realistic than assuming completely free trades.

---

## 📊 Performance Metrics

The dashboard calculates several strategy-performance metrics:

- Strategy Return
- Strategy Return After Cost
- Buy & Hold Return
- Final Strategy Value
- Final Buy & Hold Value
- Maximum Drawdown
- CAGR
- Sharpe Ratio
- Number of Completed Trades
- Win Rate
- Average Winning Trade
- Average Losing Trade
- Risk / Reward Ratio
- Expectancy
- Stop-Loss Exits
- Take-Profit Exits
- Strategy Exits

---

## 📈 Portfolio Growth

The dashboard plots the growth of:

- Buy & Hold portfolio
- Trading strategy portfolio

This provides a visual comparison between actively following a strategy and simply holding the stock for the selected period.

---

## 🧾 Trade History

Every completed trade is stored in a trade table containing:

- Buy Date
- Buy Price
- Sell Date
- Actual Sell Price
- Trade Return
- Net Return after transaction cost
- Exit Reason

Possible exit reasons include:

- Strategy Exit
- Stop Loss
- Take Profit

Trade history can also be downloaded as a CSV file.

---

## 🟢 Open Position Tracking

If a strategy still holds a position when the selected backtesting period ends, the dashboard identifies it separately instead of incorrectly treating it as a completed trade.

For an open position, the dashboard displays:

- Buy Date
- Buy Price
- Current Price
- Unrealised Return

---

## 🧠 Indicator Warm-Up

Technical indicators require historical observations before producing meaningful values.

For example, calculating SMA 50 requires previous price history.

To handle this, the application automatically downloads additional historical data before the user's selected display period.

Indicators are calculated using the extended history, while charts and backtesting results remain restricted to the period selected by the user.

---

## ⚡ Performance & Data Handling

The application uses:

- `st.cache_data` to cache market data for 5 minutes
- `st.session_state` to preserve stock analysis and backtesting results across Streamlit reruns
- Additional input and data validation
- Error handling for failed market-data requests

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Dashboard | Streamlit |
| Market Data | yfinance |
| Data Processing | pandas |
| Interactive Charts | Plotly |
| Version Control | Git & GitHub |

---

## 📁 Project Structure

```text
Stock-Analysis-Dashboard/
│
├── app.py
├── requirements.txt
├── README.md
└── .gitignore