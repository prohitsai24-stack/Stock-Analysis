import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots


st.set_page_config(
    page_title = "Stock Analysis Dashboard",
    page_icon = "📈",
    layout = "wide"
)

if "analysis_ready" not in st.session_state:
    st.session_state["analysis_ready"] = False

if "backtest_ready" not in st.session_state:
    st.session_state["backtest_ready"] = False

@st.cache_data(ttl = 300)
def get_stock_data(ticker, period):
    stock = yf.Ticker(ticker)
    data = stock.history(period = period)
    return data

@st.cache_data(ttl = 300)
def get_extended_stock_data(ticker, start_date):
    stock = yf.Ticker(ticker)
    data = stock.history(start=start_date)
    return data

@st.cache_data(ttl = 300)
def get_stock_info(ticker):
    stock = yf.Ticker(ticker)
    return stock.info

def format_market_cap(value):
    if value is None or value == "N/A":
        return "N/A"
    elif value >= 1_000_000_000_000:
        return f"{value/1_000_000_000_000:.2f}T"
    elif value >= 1_000_000_000:
            return f"{value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
            return f"{value/1_000_000:.2f}M"
    else:
        return str(value)

#if on the same daily candle: Low  <= Stop Loss and High >= Take Profit 
#we don't know which one happened first because daily data doesn't tell us the intraday sequence,
#So if both are touched on the same day, we assume Stop Loss happened first

def apply_risk_management(data, stop_loss_percent, take_profit_percent):
    adjusted_signal = data["BT_Signal"].copy()
    data["Exit_Reason"] = None
    data["Exit_Price"] = None

    holding = False
    entry_price = None
    blocked = False

    for i in range(len(data)):
        strategy_signal = data["BT_Signal"].iloc[i]

        day_open = data["Open"].iloc[i]
        day_low = data["Low"].iloc[i]
        day_high = data["High"].iloc[i]
        price = data["Close"].iloc[i]
        
        if strategy_signal == 0:
            if holding:
                data.loc[data.index[i], "Exit_Reason"] = "Strategy Exit"
                data.loc[data.index[i], "Exit_Price"] = price

            holding = False
            entry_price = None
            blocked = False
            adjusted_signal.iloc[i] = 0
            continue

        if strategy_signal == 1:
            if not holding and not blocked:
                holding = True
                entry_price = price
                adjusted_signal.iloc[i] = 1
            elif holding:
                stop_hit = False
                take_profit_hit = False
                if stop_loss_percent is not None:
                    stop_price = entry_price * (1 - stop_loss_percent / 100)
                    if day_open <= stop_price:
                        stop_hit = True
                        actual_stop_price = day_open
                    elif day_low <= stop_price:
                        stop_hit = True
                        actual_stop_price = stop_price
                if take_profit_percent is not None:
                    target_price = entry_price * (1 + take_profit_percent / 100)
                    if day_open >= target_price:
                        take_profit_hit = True
                        actual_target_price = day_open
                    elif day_high >= target_price:
                        take_profit_hit = True
                        actual_target_price = target_price

                if stop_hit:
                    holding = False
                    entry_price = None
                    adjusted_signal.iloc[i] = 0
                    blocked = True

                    data.loc[data.index[i], "Exit_Reason"] = "Stop Loss"
                    data.loc[data.index[i], "Exit_Price"] = actual_stop_price
                elif take_profit_hit:
                    holding = False
                    entry_price = None
                    adjusted_signal.iloc[i] = 0
                    blocked = True

                    data.loc[data.index[i], "Exit_Reason"] = "Take Profit"
                    data.loc[data.index[i], "Exit_Price"] = actual_target_price

                else:
                    adjusted_signal.iloc[i] = 1

            else:
                adjusted_signal.iloc[i] = 0

    data["BT_Signal"] = adjusted_signal
    return data

def calculate_backtest_results(data, cost):
    data["Return"] = data["Close"].pct_change().fillna(0)

    data["Trade"] = data["BT_Signal"].diff()
    data.loc[data.index[0], "Trade"] = data["BT_Signal"].iloc[0]

    data["Position_Change"] = data["Trade"].abs()
    data["Position"] = data["BT_Signal"].shift(1).fillna(0)

    data["Strategy_Return"] = data["Position"] * data["Return"]
    if "Exit_Price" in data.columns:
        previous_close = data["Close"].shift(1)

        exit_rows = data["Exit_Price"].notna() & (data["Position"] == 1)

        data.loc[exit_rows, "Strategy_Return"] = (
            data.loc[exit_rows, "Exit_Price"].astype(float) /
            previous_close.loc[exit_rows]
        ) - 1
    data["Strategy_Return_After_Cost"] = data["Strategy_Return"] - data["Position_Change"] * cost

    data["Buy_Hold"] = (1 + data["Return"]).cumprod()
    data["Strategy_Equity"] = (1 + data["Strategy_Return"]).cumprod()
    data["Strategy_Equity_Net"] = (1 + data["Strategy_Return_After_Cost"]).cumprod()

    return data

def run_crossover_backtest(data, short_column, long_column):
    data["BT_Signal"] = 0
    data.loc[data[short_column] > data[long_column], "BT_Signal"] = 1
    return data


st.title("STOCK ANALYSIS DASHBOARD")
st.caption("Analyse stock prices, technical indicators and trading strategies.")

with st.sidebar:
    st.header("Stock Settings")

    with st.form("stock_form"):
        st.markdown("#### Stock Details")
        ticker = st.text_input("Enter the stock :",
                               placeholder = "Example: AAPL, TCS.NS")

        period = st.selectbox("Select Period",
                            ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
                            index = None,
                            placeholder = "Select Period")

        investment = st.number_input("Investment Amount",
                                        min_value = 100,
                                        value = 1000,
                                        step = 100)

        st.markdown("#### Chart Settings")
        indicators = st.multiselect("Select Indicators",
                                    ["SMA_20", "SMA_50", "EMA_20", "EMA_50", 
                                     "RSI_14", "MACD", "Bollinger Bands", "ATR_14", "Volume"])

        chart_type = st.selectbox("Chart Type", ["Lines", "Candlestick"])
        
        submitted = st.form_submit_button("Analyse Stock")

if submitted:
    ticker = ticker.strip().upper()

    if ticker and period:
        with st.spinner("Analysing..."):
            try:
                data = get_stock_data(ticker, period)
            except Exception as e:
                st.error("Unable to fetch stock price data : {e}")
                st.stop()
            try:
                info = get_stock_info(ticker)
            except Exception:
                info = {}

            company_name = info.get("longName", ticker)
            sector = info.get("sector", "N/A")
            industry = info.get("industry", "N/A")
            market_cap = info.get("marketCap", "N/A")
            market_cap = format_market_cap(market_cap)

            if data.empty:
                st.error("No Stock Data Found")
            else:
                display_start_date = data.index[0]
                extended_start_date = display_start_date - pd.Timedelta(days=400)
                extended_data = get_extended_stock_data(ticker, extended_start_date.strftime("%Y-%m-%d"))

                st.session_state["analysis_ready"] = True
                st.session_state["backtest_ready"] = False

                st.session_state["data"] = data
                st.session_state["extended_data"] = extended_data

                st.session_state["ticker"] = ticker
                st.session_state["period"] = period
                st.session_state["investment"] = investment
                st.session_state["indicators"] = indicators
                st.session_state["chart_type"] = chart_type

                st.session_state["company_name"] = company_name
                st.session_state["sector"] = sector
                st.session_state["industry"] = industry 
                st.session_state["market_cap"] = market_cap

    else:
        st.warning("Please Enter correct ticker and period")

if st.session_state["analysis_ready"]:
    data = st.session_state["data"].copy()
    extended_data = st.session_state["extended_data"].copy()

    data = data.dropna(subset = ["Open", "High", "Low", "Close"])
    extended_data = extended_data.dropna(subset = ["Open", "High", "Low", "Close"])

    display_start_date = data.index[0]

    ticker = st.session_state["ticker"]
    period = st.session_state["period"]
    investment = st.session_state["investment"]
    indicators = st.session_state["indicators"]
    chart_type = st.session_state["chart_type"]

    company_name = st.session_state["company_name"]
    sector = st.session_state["sector"]
    industry = st.session_state["industry"]
    market_cap = st.session_state["market_cap"]

    latest_price = data["Close"].iloc[-1]

    if len(data) >= 2:
        previous_price = data["Close"].iloc[-2]
        price_change = latest_price - previous_price
        price_change_percent = (price_change / previous_price) * 100
    else:
        price_change = 0
        price_change_percent = 0
    
    high_price = data["High"].iloc[-1]
    low_price = data["Low"].iloc[-1]


    if "SMA_20" in indicators:
        extended_data["SMA_20"] = extended_data["Close"].rolling(window = 20).mean()
    if "SMA_50" in indicators:
        extended_data["SMA_50"] = extended_data["Close"].rolling(window = 50).mean()
    if "EMA_20" in indicators:
        extended_data["EMA_20"] = extended_data["Close"].ewm(span = 20, adjust = False).mean()
    if "EMA_50" in indicators:
        extended_data["EMA_50"] = extended_data["Close"].ewm(span = 50, adjust = False).mean()
    if "RSI_14" in indicators:
        delta = extended_data["Close"].diff()
        gain = delta.clip(lower = 0)
        loss = -delta.clip(upper = 0)
        avg_gain = gain.ewm(alpha = 1/14, adjust = False).mean()
        avg_loss = loss.ewm(alpha = 1/14, adjust = False).mean()
        rs = avg_gain/avg_loss
        extended_data["RSI_14"] = 100 - 100/(1 + rs)
    if "MACD" in indicators:
        extended_data["EMA_12"] = extended_data["Close"].ewm(span = 12, adjust = False).mean()
        extended_data["EMA_26"] = extended_data["Close"].ewm(span = 26, adjust = False).mean()
        extended_data["MACD"] = extended_data["EMA_12"] - extended_data["EMA_26"]
        extended_data["Signal_line"] = extended_data["MACD"].ewm(span = 9, adjust = False).mean()
        extended_data["Histogram"] = extended_data["MACD"] - extended_data["Signal_line"]
    if "Bollinger Bands" in indicators:
        extended_data["BB_middle"] = extended_data["Close"].rolling(window = 20).mean()
        std = extended_data["Close"].rolling(window = 20).std()
        extended_data["BB_upper"] = extended_data["BB_middle"] + 2 * std
        extended_data["BB_lower"] = extended_data["BB_middle"] - 2 * std
    if "ATR_14" in indicators:
        previous_close = extended_data["Close"].shift(1)
        tr1 = extended_data["High"] - extended_data["Low"]
        tr2 = (extended_data["High"] - previous_close).abs()
        tr3 = (extended_data["Low"] - previous_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis = 1).max(axis = 1)
        extended_data["ATR_14"] = true_range.ewm(alpha = 1/14, adjust = False).mean()

    data = extended_data[extended_data.index >= display_start_date].copy()

    if "Volume" in indicators:
        technical_fig = make_subplots(rows = 2,
                                        cols = 1,
                                        shared_xaxes = True,
                                        row_heights = [0.75, 0.25],
                                        vertical_spacing = 0.01)
        technical_fig.update_layout(title = f"{ticker} Technical Analysis",
                                    height = 650,
                                    hovermode = "x unified",
                                    hoversubplots = "axis",
                                    xaxis2_title = "Date")
    else:
        technical_fig = make_subplots(rows = 1, cols = 1)
        technical_fig.update_layout(title = f"{ticker} Technical Analysis",
                                    height = 500,
                                    hovermode = "x unified",
                                    xaxis_title = "Date")

    tab1, tab2, tab3 = st.tabs(["Overview", "Technical Indicators", "Backtesting"])

    with tab1:
        st.header(ticker)
        st.caption(f"Analysis Period: {period}")

        st.write("Company Name :", company_name)
        st.write("Sector :", sector)
        st.write("Industry :", industry)
        st.write("Market Cap :", market_cap)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Current Price",
                    value = round(latest_price, 2),
                    delta = f"{price_change:.2f} ({price_change_percent:.2f}%)")
        with col2:
            st.metric("Day High", f"{high_price:,.2f}")
        with col3:
            st.metric("Day Low", f"{low_price:,.2f}")

        st.divider()

        fig = go.Figure()
        if chart_type == "Lines":
            fig.add_trace(go.Scatter(x = data.index,
                                    y = data["Close"],
                                    mode = "lines",
                                    name = "Closing price"))
        elif chart_type == "Candlestick":
            fig.add_trace(go.Candlestick(x = data.index,
                                            open = data["Open"],
                                            high = data["High"],
                                            low = data["Low"],
                                            close = data["Close"],
                                            name = ticker))
        fig.update_layout(title = f"{ticker} Price Chart",
                            xaxis_title = "Date",
                            yaxis_title = "Price",
                            height = 500)
        st.plotly_chart(fig, width = "stretch")

        with st.expander("View Stock Data"):
            st.subheader("STOCK DATA")
            st.dataframe(data, width = "stretch")

            csv = data.to_csv().encode("utf-8")
            st.download_button(label = "Download Stock Data",
                                data = csv,
                                file_name = f"{ticker}_{period}_data.csv",
                                mime = "text/csv")

    with tab2:
        st.header("Technical Analysis")
        st.subheader("Price & Selected Indicators")

        technical_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["Close"],
                                        mode = "lines",
                                        name = "Closing Price"), row = 1, col = 1)
        if "SMA_20" in indicators:
            technical_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["SMA_20"],
                                            mode = "lines",
                                            name = "SMA_20"), row = 1, col = 1)
        if "SMA_50" in indicators:
            technical_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["SMA_50"],
                                            mode = "lines",
                                            name = "SMA_50"), row = 1, col = 1)
        if "EMA_20" in indicators:
            technical_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["EMA_20"],
                                            mode = "lines",
                                            name = "EMA_20"), row = 1, col = 1)
        if "EMA_50" in indicators:
            technical_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["EMA_50"],
                                            mode = "lines",
                                            name = "EMA_50"), row = 1, col = 1)
        technical_fig.update_yaxes(title_text = "Price",
                                    row = 1,
                                    col = 1)
        if "Volume" in indicators:
            technical_fig.add_trace(go.Bar(x = data.index,
                                            y = data["Volume"],
                                            name = "Volume"), row = 2, col = 1)
            technical_fig.update_yaxes(title_text = "Volume",
                                        row = 2,
                                        col = 1)                     

        st.plotly_chart(technical_fig, width = "stretch")
        
        if "RSI_14" in indicators:
            st.subheader("RSI")
            rsi_fig = go.Figure()
            rsi_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["RSI_14"],
                                        mode = "lines",
                                        name = "RSI_14"))
            rsi_fig.update_layout(title = f"{ticker} RSI",
                                    xaxis_title = "Date",
                                    yaxis_title = "RSI",
                                    height = 400,
                                    hovermode = "x unified")
            rsi_fig.add_hline(y = 70,
                                line_dash = "dash",
                                line_color = "red",
                                annotation_text = "Overbought",
                                annotation_font_color = "red")
            rsi_fig.add_hline(y = 30,
                                line_dash = "dash",
                                line_color = "green",
                                annotation_text = "Oversold",
                                annotation_font_color = "green")
            rsi_fig.update_yaxes(range = [0, 100])
            
            st.plotly_chart(rsi_fig, width = "stretch")

        if "MACD" in indicators:
            st.subheader("MACD")
            macd_fig = go.Figure()
            macd_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["MACD"],
                                        mode = "lines",
                                        name = "MACD"))
            macd_fig.add_trace(go.Bar(x = data.index,
                                        y = data["Histogram"],
                                        name = "Histogram"))
            macd_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["Signal_line"],
                                        mode = "lines",
                                        name = "Signal line"))
            macd_fig.update_layout(title = f"{ticker} MACD",
                                    xaxis_title = "Date",
                                    yaxis_title = "MACD",
                                    height = 400,
                                    hovermode = "x unified")
            st.plotly_chart(macd_fig, width = "stretch")

        if "Bollinger Bands" in indicators:
            st.subheader("Bollinger Bands")
            bb_fig = go.Figure()
            bb_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["Close"],
                                        mode = "lines",
                                        name = "Closing Price"))
            bb_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["BB_middle"],
                                        mode = "lines",
                                        name = "Middle Band"))
            bb_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["BB_upper"],
                                        mode = "lines",
                                        name = "Upper Band"))
            bb_fig.add_trace(go.Scatter(x = data.index,
                                        y = data["BB_lower"],
                                        mode = "lines",
                                        name = "Lower Band"))
            bb_fig.update_layout(title = f"{ticker} Bollinger Bands",
                                        xaxis_title = "Date",
                                        yaxis_title = "Price",
                                        height = 500,
                                        hovermode = "x unified")
            st.plotly_chart(bb_fig, width = "stretch")
        if "ATR_14" in indicators:
            st.subheader("ATR")
            atr_fig = go.Figure()
            atr_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["ATR_14"],
                                            mode = "lines",
                                            name = "ATR"))
            atr_fig.update_layout(title = f"{ticker} ATR",
                                    xaxis_title = "Date",
                                    yaxis_title = "ATR",
                                    height = 400,
                                    hovermode = "x unified")
            st.plotly_chart(atr_fig, width = "stretch")
            
    with tab3:
        st.header("BACKTESTING")
        st.write("Investment Amount : ", investment)
    
        st.markdown("#### Strategy Settings")
        strategy = st.selectbox("Select Strategy", ["SMA Crossover", "EMA Crossover",
                                                    "RSI Strategy", "MACD Strategy",
                                                    "Bollinger Bands Strategy"],
                                                    index = None,
                                                    placeholder = "Select Strategy")
        
        if strategy == "SMA Crossover":
            short_period = st.number_input("Short SMA", min_value = 2,
                                        value = 20,
                                        step = 2)
            long_period = st.number_input("Long SMA", min_value = 3,
                                        value = 50,
                                        step = 2)

        elif strategy == "EMA Crossover":
            short_period = st.number_input("Short EMA",min_value=2,
                                        value=20,
                                        step=1)
            long_period = st.number_input("Long EMA",min_value=3,
                                        value=50,
                                        step=1)

        elif strategy == "RSI Strategy":
            rsi_period = st.number_input("RSI Period",min_value=2,
                                            value=14,
                                            step=1)
            oversold_level = st.number_input("Oversold Level",min_value=1,
                                                max_value=49,value=30,step=1)
            overbought_level = st.number_input("Overbought Level",min_value=51,
                                                max_value=99,
                                                value=70,
                                                step=1)

        elif strategy == "MACD Strategy":
            fast_period = st.number_input("Fast EMA", min_value=2,
                                          value=12, 
                                          step=1)
            slow_period = st.number_input("Slow EMA",min_value=3,
                                          value=26,
                                          step=1)
            signal_period = st.number_input("Signal Period", min_value=2,
                                            value=9,
                                            step=1)

        elif strategy == "Bollinger Bands Strategy":
            bb_period = st.number_input("Bollinger Period", min_value=2,
                                        value=20,
                                        step=1)
            bb_std = st.number_input("Standard Deviation", min_value=0.5,
                                     value=2.0, step=0.1)

        st.markdown("#### Risk Settings")
        transaction_cost = st.number_input("Transaction Cost (%)", min_value = 0.0,
                                            value = 0.1,
                                            step = 0.05)
        cost = transaction_cost / 100

        use_stop_loss = st.checkbox("Use Stop Loss")
        if use_stop_loss:
            stop_loss_percent = st.number_input("Stop Loss (%)",min_value=0.1,
                                                value=5.0,
                                                step=0.5)
        else:
            stop_loss_percent = None

        use_take_profit = st.checkbox("Use Take Profit")
        if use_take_profit:
            take_profit_percent = st.number_input("Take Profit (%)",min_value=0.1,
                                                    value=10.0,
                                                    step=0.5)
        else:
            take_profit_percent = None

        run_backtest = st.button("Run Backtest",
                                    key = "run_backtest_button")
        if run_backtest:
            backtest_ready = False
            st.session_state["backtest_ready"] = False

            if strategy is None:
                st.warning("Please Select a Strategy")
            else:
                backtest_data = extended_data.copy()

                if strategy == "SMA Crossover" or strategy == "EMA Crossover":
                    if short_period >= long_period:
                        st.warning("Short Period should be less than Long Period")
                    elif long_period > len(backtest_data):
                        st.warning(f"Not enough historical data for {long_period} period calculation")
                    else:
                        if strategy == "SMA Crossover":
                            short_column = f"SMA_{short_period}"
                            long_column = f"SMA_{long_period}"

                            if short_column not in backtest_data.columns:
                                backtest_data[short_column] = backtest_data["Close"].rolling(window = short_period).mean()
                            if long_column not in backtest_data.columns:
                                backtest_data[long_column] = backtest_data["Close"].rolling(window = long_period).mean()

                        elif strategy == "EMA Crossover":
                            short_column = f"EMA_{short_period}"
                            long_column = f"EMA_{long_period}"

                            if short_column not in backtest_data.columns:
                                backtest_data[short_column] = backtest_data["Close"].ewm(span = short_period, adjust = False).mean()
                            if long_column not in backtest_data.columns:
                                backtest_data[long_column] = backtest_data["Close"].ewm(span = long_period, adjust = False).mean()

                        backtest_data = backtest_data[backtest_data.index >= display_start_date].copy()
                        backtest_data =run_crossover_backtest(backtest_data, short_column, long_column)
                        
                        backtest_data = apply_risk_management(backtest_data, stop_loss_percent, take_profit_percent)
                        backtest_data = calculate_backtest_results(backtest_data, cost)

                        data = backtest_data

                        backtest_ready = True

                        st.session_state["short_period"] = short_period
                        st.session_state["long_period"] = long_period
                        st.session_state["short_column"] = short_column
                        st.session_state["long_column"] = long_column

                elif strategy == "RSI Strategy":
                    if rsi_period > len(backtest_data):
                        st.warning(f"Not enough historical data for RSI {rsi_period}")
                    else:
                        delta = backtest_data["Close"].diff()
                        gain = delta.clip(lower = 0)
                        loss = -delta.clip(upper = 0)
                        avg_gain = gain.ewm(alpha = 1/rsi_period, adjust = False).mean()
                        avg_loss = loss.ewm(alpha = 1/rsi_period, adjust = False).mean()
                        rs = avg_gain/avg_loss
                        backtest_data["RSI_BT"] = 100 - (100/(1+rs))

                        backtest_data = backtest_data[backtest_data.index >= display_start_date].copy()

                        backtest_data["BT_Signal"] = 0
                        holding = False

                        for i in range(len(backtest_data)):
                            rsi = backtest_data["RSI_BT"].iloc[i]
                            if  not holding and rsi < oversold_level:
                                holding = True
                            elif holding and rsi > overbought_level:
                                holding = False
                            if holding:
                                backtest_data.iloc[i, backtest_data.columns.get_loc("BT_Signal")] = 1
                        
                        backtest_data = apply_risk_management(backtest_data, stop_loss_percent, take_profit_percent)
                        backtest_data = calculate_backtest_results(backtest_data, cost)
                        data = backtest_data

                        backtest_ready = True

                        st.session_state["rsi_period"] = rsi_period
                        st.session_state["oversold_level"] = oversold_level
                        st.session_state["overbought_level"] = overbought_level

                elif strategy == "MACD Strategy":
                    if fast_period >= slow_period:
                        st.warning("Fast EMA should be less than Slow EMA")
                    elif slow_period > len(backtest_data):
                        st.warning(f"Not enough historical data for MACD {slow_period}")
                    else:
                        fast_ema = backtest_data["Close"].ewm(span=fast_period, adjust=False).mean()
                        slow_ema = backtest_data["Close"].ewm(span=slow_period, adjust=False).mean()

                        backtest_data["MACD_BT"] = fast_ema - slow_ema
                        backtest_data["MACD_Signal_BT"] = backtest_data["MACD_BT"].ewm(span=signal_period, adjust=False).mean()
                        backtest_data["MACD_Histogram_BT"] = backtest_data["MACD_BT"] - backtest_data["MACD_Signal_BT"]

                        backtest_data = backtest_data[backtest_data.index >= display_start_date].copy()

                        backtest_data["BT_Signal"] = 0
                        backtest_data.loc[backtest_data["MACD_BT"] > backtest_data["MACD_Signal_BT"], "BT_Signal"] = 1

                        backtest_data = apply_risk_management(backtest_data, stop_loss_percent, take_profit_percent)
                        backtest_data = calculate_backtest_results(backtest_data, cost)
                        data = backtest_data

                        backtest_ready = True

                        st.session_state["fast_period"] = fast_period
                        st.session_state["slow_period"] = slow_period
                        st.session_state["signal_period"] = signal_period


                elif strategy == "Bollinger Bands Strategy":
                    if bb_period > len(backtest_data):
                        st.warning(f"Not enough historical data for Bollinger Period {bb_period}")
                    else:
                        backtest_data["BB_Middle_BT"] = backtest_data["Close"].rolling(window=bb_period).mean()
                        bb_std_value = backtest_data["Close"].rolling(window=bb_period).std()
                        backtest_data["BB_Upper_BT"] = backtest_data["BB_Middle_BT"] + bb_std * bb_std_value
                        backtest_data["BB_Lower_BT"] = backtest_data["BB_Middle_BT"] - bb_std * bb_std_value

                        backtest_data = backtest_data[backtest_data.index >= display_start_date].copy()

                        backtest_data["BT_Signal"] = 0
                        holding = False

                        for i in range(len(backtest_data)):
                            price = backtest_data["Close"].iloc[i]
                            lower_band = backtest_data["BB_Lower_BT"].iloc[i]
                            upper_band = backtest_data["BB_Upper_BT"].iloc[i]

                            if not holding and price < lower_band:
                                holding = True
                            elif holding and price > upper_band:
                                holding = False
                            if holding:
                                backtest_data.loc[backtest_data.index[i], "BT_Signal"] = 1

                        backtest_data = apply_risk_management(backtest_data, stop_loss_percent, take_profit_percent)
                        backtest_data = calculate_backtest_results(backtest_data, cost)
                        data = backtest_data

                        backtest_ready = True

                        st.session_state["bb_period"] = bb_period
                        st.session_state["bb_std"] = bb_std

            if backtest_ready:
                st.session_state["backtest_ready"] = True
                st.session_state["backtest_data"] = data.copy()
                st.session_state["backtest_strategy"] = strategy
                st.session_state["backtest_cost"] = cost
                st.session_state["backtest_transaction_cost"] = transaction_cost

        if st.session_state["backtest_ready"]:
            data = st.session_state["backtest_data"].copy()
            strategy = st.session_state["backtest_strategy"]
            cost = st.session_state["backtest_cost"]
            transaction_cost = st.session_state["backtest_transaction_cost"]

            if strategy in ["SMA Crossover", "EMA Crossover"]:
                short_period = st.session_state["short_period"]
                long_period = st.session_state["long_period"]
                short_column = st.session_state["short_column"]
                long_column = st.session_state["long_column"]

            elif strategy == "RSI Strategy":
                rsi_period = st.session_state["rsi_period"]
                oversold_level = st.session_state["oversold_level"]
                overbought_level = st.session_state["overbought_level"]

            elif strategy == "MACD Strategy":
                fast_period = st.session_state["fast_period"]
                slow_period = st.session_state["slow_period"]
                signal_period = st.session_state["signal_period"]

            elif strategy == "Bollinger Bands Strategy":
                bb_period = st.session_state["bb_period"]
                bb_std = st.session_state["bb_std"]

            number_of_transactions = data["Position_Change"].sum()
            total_cost_percent = number_of_transactions * transaction_cost
            buy_hold_return = data["Buy_Hold"].iloc[-1] - 1
            strategy_return = data["Strategy_Equity"].iloc[-1] - 1
            net_strategy_return = data["Strategy_Equity_Net"].iloc[-1] - 1

            buy_points = data[data["Trade"] == 1]
            sell_points = data[data["Trade"] == -1]
            number_of_trades = min(len(buy_points), len(sell_points))
            open_position = data["BT_Signal"].iloc[-1] == 1

            data["Peak"] = data["Strategy_Equity"].cummax()
            data["Drawdown"] = (data["Strategy_Equity"] - data["Peak"]) / data["Peak"]
            max_drawdown = data["Drawdown"].min()

            buys = buy_points.iloc[:number_of_trades]
            sells = sell_points.iloc[:number_of_trades]
            Trade_Table = pd.DataFrame({"Buy_Date": buys.index,
                                        "Buy_Price": buys["Close"].values,
                                        "Sell_Date": sells.index,
                                        "Sell_Price": sells["Exit_Price"].values,
                                        "Exit_Reason": sells["Exit_Reason"].values})
            
            stop_loss_exits = len(Trade_Table[Trade_Table["Exit_Reason"] == "Stop Loss"])
            take_profit_exits = len(Trade_Table[Trade_Table["Exit_Reason"] == "Take Profit"])
            strategy_exits = len(Trade_Table[Trade_Table["Exit_Reason"] == "Strategy Exit"])

            Trade_Table["Return"] = Trade_Table["Sell_Price"]/ Trade_Table["Buy_Price"] - 1
            Trade_Table["Net_Return"] = Trade_Table["Return"] - (2 * cost)
            Trade_Table["Return_%"] = (Trade_Table["Return"] * 100).round(2)
            Trade_Table["Net_Return_%"] = (Trade_Table["Net_Return"] * 100).round(2)

            winning_trades = Trade_Table[Trade_Table["Net_Return"] > 0]
            losing_trades = Trade_Table[Trade_Table["Net_Return"] < 0]
            if number_of_trades > 0:
                    win_rate = (len(winning_trades) / number_of_trades)
            else:
                win_rate = 0
            loss_rate = 1 - win_rate
            if len(winning_trades) > 0:
                average_win = winning_trades["Net_Return"].mean()
            else:
                average_win = 0
            if len(losing_trades) > 0:
                average_loss = losing_trades["Net_Return"].mean()
            else:
                average_loss = 0

            if average_loss != 0:
                risk_reward = average_win / abs(average_loss)
            else:
                risk_reward = 0    
            expectancy = win_rate * average_win - loss_rate * abs(average_loss)

            years = (data.index[-1] - data.index[0]).days / 365.25              
            if years > 0:
                cagr = (data["Strategy_Equity"].iloc[-1] ** (1 / years)) - 1
            else:
                cagr = 0

            if data["Strategy_Return"].std() != 0:
                sharpe_ratio = (data["Strategy_Return"].mean() / data["Strategy_Return"].std()) * (252 ** 0.5)
            else:
                sharpe_ratio = 0

            strategy_final_value = investment * (1 + net_strategy_return)
            buy_hold_final_value = investment * (1 + buy_hold_return)

            st.divider()
            st.subheader("Backtest Results")

            if strategy in ["RSI Strategy", "MACD Strategy"]:
                backtest_fig = make_subplots(rows=2, cols=1,
                                             shared_xaxes=True,
                                             row_heights=[0.7, 0.3],
                                             vertical_spacing=0.05)
            else:
                backtest_fig = make_subplots(rows=1, cols=1)

            backtest_fig.add_trace(go.Scatter(x = data.index,
                                                y = data["Close"],
                                                mode = "lines",
                                                name = "Closing Price"))

            if strategy == "SMA Crossover" or strategy == "EMA Crossover":
                backtest_fig.add_trace(go.Scatter(x = data.index,
                                                    y = data[short_column],
                                                    mode = "lines",
                                                    name = short_column), row = 1, col = 1)
                backtest_fig.add_trace(go.Scatter(x = data.index,
                                                    y = data[long_column],
                                                    mode = "lines",
                                                    name = long_column), row = 1, col = 1)
                graph_title = (f"{ticker} : {short_period}/{long_period} {strategy}")

            elif strategy == "RSI Strategy":
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                    y=data["RSI_BT"],
                                                    mode="lines",
                                                    name=f"RSI_{rsi_period}"), row=2, col=1)
                backtest_fig.add_hline(y=overbought_level,
                                       line_dash="dash",
                                       annotation_text="Overbought",
                                       row=2, col=1)
                backtest_fig.add_hline(y=oversold_level,
                                       line_dash="dash",
                                       annotation_text="Oversold",
                                       row=2, col=1)
                backtest_fig.update_yaxes(title_text="RSI",
                                          range=[0, 100],
                                          row=2, col=1)
                graph_title = (f"{ticker} : RSI {rsi_period} Strategy")

            elif strategy == "MACD Strategy":
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                  y=data["MACD_BT"],
                                                  mode="lines",
                                                  name="MACD"),row=2, col=1)
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                  y=data["MACD_Signal_BT"],
                                                  mode="lines",
                                                  name="Signal Line"), row=2, col=1)
                backtest_fig.add_trace(go.Bar(x=data.index,
                                              y=data["MACD_Histogram_BT"],
                                              name="Histogram"),row=2, col=1)
                backtest_fig.add_hline(y=0,
                                       line_dash="dash",row=2, col=1)
                backtest_fig.update_yaxes(title_text="MACD",
                                          row=2, col=1)
                graph_title = (f"{ticker} : "
                               f"MACD {fast_period}/{slow_period}/{signal_period}")

            elif strategy == "Bollinger Bands Strategy":
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                    y=data["BB_Upper_BT"],
                                                    mode="lines",
                                                    name="Upper Band"),row=1, col=1)
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                y=data["BB_Middle_BT"],
                                                mode="lines",
                                                name="Middle Band"), row=1, col=1)
                backtest_fig.add_trace(go.Scatter(x=data.index,
                                                    y=data["BB_Lower_BT"],
                                                    mode="lines",
                                                    name="Lower Band"),row=1, col=1)
                graph_title = (f"{ticker} : "
                               f"Bollinger Bands {bb_period} / {bb_std}")
                

            backtest_fig.add_trace(go.Scatter(x=buy_points.index,
                                              y=buy_points["Close"],
                                                mode="markers",
                                                name="Buy",
                                                marker=dict(symbol="triangle-up",
                                                            size=12,
                                                            color = "green")))
            backtest_fig.add_trace(go.Scatter(x=sell_points.index,
                                                y=sell_points["Exit_Price"].astype(float),
                                                mode="markers",
                                                name="Sell",
                                                marker=dict(symbol="triangle-down",
                                                            size=12,
                                                            color = "red")))
            backtest_fig.update_yaxes(title_text="Price",
                                      row=1, col=1)
            if strategy in ["RSI Strategy", "MACD Strategy"]:
                backtest_fig.update_xaxes(title_text="Date",
                                          row=2, col=1)
                graph_height = 650
            else:
                backtest_fig.update_xaxes(title_text="Date",
                                          row=1, col=1)
                graph_height = 500  
            backtest_fig.update_layout(title=graph_title,
                                       height=graph_height,
                                       hovermode="x unified") 
            
            st.plotly_chart(backtest_fig, width = "stretch")

            st.subheader("Performance Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Strategy Returns",
                            f"{strategy_return * 100:.2f}%")
            with col2:
                st.metric("Buy & Hold Returns",
                            f"{buy_hold_return * 100:.2f}%")
            with col3:
                st.metric("Maximum Drawdown",
                            f"{max_drawdown * 100:.2f}%")

            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.metric("Transaction Cost",
                            f"{total_cost_percent:.2f}%")
            with t_col2:
                st.metric("Strategy Return After Cost",
                            f"{net_strategy_return * 100:.2f}%")

            bt_col1, bt_col2, bt_col3 = st.columns(3)
            with bt_col1:
                st.metric("Initial Investment",
                            f"{investment:.2f}")
            with bt_col2:
                st.metric("Final Strategy Value",
                            f"{strategy_final_value:.2f}")
            with bt_col3:
                st.metric("Final Buy & Hold Value",
                            f"{buy_hold_final_value:.2f}")

            equity_fig = go.Figure()
            equity_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["Buy_Hold"] * investment,
                                            mode = "lines",
                                            name = "Buy & Hold"))
            equity_fig.add_trace(go.Scatter(x = data.index,
                                            y = data["Strategy_Equity"] * investment,
                                            mode = "lines",
                                            name = "Strategy (Before Cost)"))
            equity_fig.update_layout(title = "Portfolio Growth",
                                        xaxis_title = "Date",
                                        yaxis_title = "Portfolio Value",
                                        height = 500,
                                        hovermode = "x unified")
            st.plotly_chart(equity_fig, width = "stretch")

            st.subheader("Trade Statistics")
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            with stat_col1:
                st.metric("Number of Trades",
                            number_of_trades)
            with stat_col2:
                st.metric("Win Rate",
                            f"{win_rate * 100:.2f}%")
            with stat_col3:
                st.metric("Average Win",
                            f"{average_win * 100:.2f}%")
            with stat_col4:
                st.metric("Average Loss",
                            f"{average_loss * 100:.2f}%")

            stat_col5, stat_col6, stat_col7, stat_col8 = st.columns(4)
            with stat_col5:
                st.metric("Risk / Reward",
                            f"{risk_reward:.2f}")
            with stat_col6:
                st.metric("Expectancy",
                            f"{expectancy * 100:.2f}%")
            with stat_col7:
                st.metric("CAGR",
                            f"{cagr * 100:.2f}%")
            with stat_col8:
                st.metric("Sharpe Ratio",
                            f"{sharpe_ratio:.2f}")

            risk_col1, risk_col2, risk_col3 = st.columns(3)
            with risk_col1:
                st.metric("Stop Loss Exits", stop_loss_exits)
            with risk_col2:
                st.metric("Take Profit Exits", take_profit_exits)
            with risk_col3:
                st.metric("Strategy Exits", strategy_exits)

            if open_position:
                open_buy = buy_points.iloc[-1]
                open_buy_date = open_buy.name
                open_buy_price = open_buy["Close"]
                current_price = data["Close"].iloc[-1]
                unrealized_return = (current_price / open_buy_price) - 1

                st.info(f"Open Position | "
                        f"Buy Date: {open_buy_date.date()} | "
                        f"Buy Price: {open_buy_price:.2f} | "
                        f"Current Price: {current_price:.2f} | "
                        f"Unrealized Return: {unrealized_return * 100:.2f}%")
            
            st.subheader("Trade History")
            with st.expander("View Trade History"):
                st.dataframe(Trade_Table[["Buy_Date", "Buy_Price", "Sell_Date",
                                        "Sell_Price", "Return_%", "Net_Return_%", "Exit_Reason"]],
                                        width="stretch")
                trade_csv = Trade_Table.to_csv(index=False).encode("utf-8")
                st.download_button(label="Download Trade History",
                                    data=trade_csv,
                                    file_name=f"{ticker}_trade_history.csv",
                                    mime="text/csv")



            


                


            
        
    