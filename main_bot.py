import os
import time
import math
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Load environment variables
load_dotenv()

session = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuration Parameters
WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
ORDER_VALUE_USDT = 6.0  # Fixed USDT allocation per trade
TIMEOUT_SECONDS = 15 * 60  # 15 Minutes Timeout (900 seconds)
COOL_DOWN_SECONDS = 10  # Idle wait between cycles
CSV_FILE_PATH = "trades_log.csv"

# Trailing Stop & Take Profit Parameters
TP_PCT = 0.015       # +1.5% Take Profit
TRAILING_PCT = 0.010 # 1.0% Trailing distance from highest peak
STOP_LOSS_PCT = 0.010 # -1.0% Initial Stop Loss from entry

def send_telegram_alert(message):
    """Sends an instant push notification to your Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Failed to send Telegram alert: {e}")

def get_available_usdt():
    """Queries Bybit Unified Trading Account for liquid available USDT."""
    try:
        res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        coins = res['result']['list'][0]['coin']
        for c in coins:
            if c['coin'] == 'USDT':
                # Return availableToWithdraw or walletBalance
                avail = float(c.get('availableToWithdraw', 0))
                if avail == 0:
                    avail = float(c.get('walletBalance', 0))
                return avail
    except Exception as e:
        print(f"⚠️ Error checking USDT balance: {e}")
    return 0.0

def init_csv_log():
    """Ensure the local CSV file exists with proper column headers."""
    if not os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Timestamp", "Cycle", "Symbol", "Order_ID", 
                "Entry_Price", "Exit_Price", "Quantity", 
                "Usdt_Allocated", "Net_Profit_USDT", "Status"
            ])
        print(f"📁 Initialized trade log file: {CSV_FILE_PATH}")

def log_trade_to_csv(cycle, symbol, order_id, entry_price, exit_price, qty, usdt_val, net_profit, status):
    """Append completed or canceled trade records to the CSV log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE_PATH, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp, cycle, symbol, order_id, 
            entry_price, exit_price, qty, 
            usdt_val, net_profit, status
        ])
    print(f"📝 Trade record logged to {CSV_FILE_PATH}")

def get_symbol_rules(symbol):
    """Fetch exact price tick size and quantity precision rules from Bybit."""
    response = session.get_instruments_info(category="spot", symbol=symbol)
    instrument = response["result"]["list"][0]
    
    price_filter = instrument["priceFilter"]
    lot_size_filter = instrument["lotSizeFilter"]
    
    tick_size = float(price_filter["tickSize"])
    base_precision = float(lot_size_filter["basePrecision"])
    
    price_decimals = len(price_filter["tickSize"].split(".")[1]) if "." in price_filter["tickSize"] else 0
    qty_decimals = len(lot_size_filter["basePrecision"].split(".")[1]) if "." in lot_size_filter["basePrecision"] else 0
    
    return tick_size, base_precision, price_decimals, qty_decimals

def get_market_prices(symbols):
    """Fetch 24h high and last price to compute percentage pullback for each symbol."""
    metrics = {}
    for sym in symbols:
        try:
            ticker = session.get_tickers(category="spot", symbol=sym)
            item = ticker["result"]["list"][0]
            last_price = float(item["lastPrice"])
            high_price = float(item["highPrice24h"])
            
            pullback_pct = ((high_price - last_price) / high_price) * 100.0
            metrics[sym] = {
                "lastPrice": last_price,
                "highPrice": high_price,
                "pullbackPct": pullback_pct
            }
        except Exception as e:
            print(f"⚠️ Warning: Could not fetch ticker metrics for {sym}: {e}")
    return metrics

def format_precision(val, decimals):
    return f"{val:.{decimals}f}"

def select_best_dip_candidate(rules_cache):
    """Scan watchlist symbols, rank by deepest % pullback, and format order parameters."""
    print("\n🔍 Evaluating 24h pullbacks across watchlist:", WATCHLIST)
    metrics = get_market_prices(WATCHLIST)
    
    for sym, data in metrics.items():
        print(f"  📊 {sym:<8} | Price: ${data['lastPrice']:<9,.2f} | 24h High: ${data['highPrice']:<9,.2f} | Dip: -{data['pullbackPct']:.2f}%")
    
    sorted_candidates = sorted(metrics.items(), key=lambda x: x[1]["pullbackPct"], reverse=True)
    selected_symbol, selected_data = sorted_candidates[0]
    
    current_price = selected_data["lastPrice"]
    pullback_pct = selected_data["pullbackPct"]
    
    print(f"\n⚡ Deepest Dip Detected: {selected_symbol} (-{pullback_pct:.2f}% from 24h High)")
    
    tick_size, base_precision, price_decimals, qty_decimals = rules_cache[selected_symbol]
    
    buy_price_val = round((current_price * 0.995) / tick_size) * tick_size
    buy_price = format_precision(buy_price_val, price_decimals)
    
    qty_val = math.floor((ORDER_VALUE_USDT / buy_price_val) / base_precision) * base_precision
    qty = format_precision(qty_val, qty_decimals)
    
    tp_price_val = round((buy_price_val * (1.0 + TP_PCT)) / tick_size) * tick_size
    tp_price = format_precision(tp_price_val, price_decimals)
    
    est_profit = round(ORDER_VALUE_USDT * TP_PCT, 4)
    
    return selected_symbol, buy_price_val, buy_price, qty_val, qty, tp_price_val, tp_price, current_price, est_profit

def monitor_position_with_trailing_stop(symbol, entry_price_val, qty, qty_decimals, price_decimals, tick_size, tp_price_val, cycle_count):
    """Monitors active position with dynamic trailing stop loss."""
    print(f"\n🛡️ Position Active on {symbol}! Initializing Trailing Stop-Loss Monitor...")
    
    highest_price = entry_price_val
    initial_sl = entry_price_val * (1.0 - STOP_LOSS_PCT)
    trailing_stop = initial_sl
    
    send_telegram_alert(
        f"🎉 *ORDER FILLED — {symbol}*\n\n"
        f"• *Entry Price:* ${entry_price_val:,.2f}\n"
        f"• *Take Profit Target:* ${tp_price_val:,.2f} (+{TP_PCT*100:.1f}%)\n"
        f"• *Initial Stop Loss:* ${initial_sl:,.2f} (-{STOP_LOSS_PCT*100:.1f}%)\n"
        f"• *Allocation:* ${ORDER_VALUE_USDT:.2f} USDT"
    )
    
    tp_order_id = None
    try:
        tp_price_str = format_precision(tp_price_val, price_decimals)
        qty_str = format_precision(qty, qty_decimals)
        tp_res = session.place_order(
            category="spot", symbol=symbol, side="Sell",
            orderType="Limit", qty=qty_str, price=tp_price_str, timeInForce="GTC"
        )
        tp_order_id = tp_res['result']['orderId']
    except Exception as e:
        print(f"⚠️ Warning: Could not place initial TP order: {e}")

    while True:
        try:
            # Check Take Profit Hit
            if tp_order_id:
                open_check = session.get_open_orders(category="spot", symbol=symbol, orderId=tp_order_id)
                if not open_check['result']['list']:
                    net_profit = round(ORDER_VALUE_USDT * TP_PCT, 4)
                    send_telegram_alert(
                        f"🟢 *TAKE PROFIT HIT — {symbol}*\n\n"
                        f"• *Exit Price:* ${tp_price_val:,.2f}\n"
                        f"• *Net Profit:* +${net_profit:.4f} USDT\n"
                        f"• *Status:* Cycle #{cycle_count} Completed Successfully!"
                    )
                    log_trade_to_csv(cycle_count, symbol, tp_order_id, entry_price_val, tp_price_val, qty, ORDER_VALUE_USDT, net_profit, "FILLED_TP")
                    break

            # Query Real-Time Price
            ticker = session.get_tickers(category="spot", symbol=symbol)
            curr_price = float(ticker["result"]["list"][0]["lastPrice"])
            
            # Update Trailing Stop Floor
            if curr_price > highest_price:
                highest_price = curr_price
                new_trailing = highest_price * (1.0 - TRAILING_PCT)
                if new_trailing > trailing_stop:
                    trailing_stop = new_trailing

            # Check Trailing Stop Trigger
            if curr_price <= trailing_stop:
                if tp_order_id:
                    try:
                        session.cancel_order(category="spot", symbol=symbol, orderId=tp_order_id)
                    except Exception:
                        pass
                
                try:
                    qty_str = format_precision(qty, qty_decimals)
                    sell_res = session.place_order(
                        category="spot", symbol=symbol, side="Sell",
                        orderType="Market", qty=qty_str
                    )
                    sell_id = sell_res['result']['orderId']
                    net_profit = round(((curr_price - entry_price_val) / entry_price_val) * ORDER_VALUE_USDT, 4)
                    
                    status_label = "TRAILING_STOP_PROFIT" if net_profit >= 0 else "TRAILING_STOP_LOSS"
                    icon = "📈" if net_profit >= 0 else "🛑"
                    
                    send_telegram_alert(
                        f"{icon} *TRAILING STOP EXECUTED — {symbol}*\n\n"
                        f"• *Exit Price:* ~${curr_price:,.2f}\n"
                        f"• *Net Profit/Loss:* {net_profit:+.4f} USDT\n"
                        f"• *Status:* {status_label}"
                    )
                    log_trade_to_csv(cycle_count, symbol, sell_id, entry_price_val, curr_price, qty, ORDER_VALUE_USDT, net_profit, status_label)
                    break
                except Exception as m_err:
                    print(f"❌ Failed to execute Market Sell: {m_err}")
                    break

            time.sleep(5)

        except Exception as err:
            print(f"⚠️ Error monitoring position: {err}")
            time.sleep(5)

def run_single_cycle(cycle_count, rules_cache):
    print("==========================================")
    print(f"🤖 Starting Multi-Token Cycle #{cycle_count}")
    print("==========================================")
    
    # 1. Liquid Balance Check (Prevents Insufficient Balance Loops)
    avail_usdt = get_available_usdt()
    print(f"💵 Available Liquid USDT: ${avail_usdt:.2f}")

    if avail_usdt < ORDER_VALUE_USDT:
        print(f"⚠️ Liquid USDT (${avail_usdt:.2f}) is less than required order allocation (${ORDER_VALUE_USDT:.2f}).")
        print("ℹ️ Active position or unfilled order holding margin. Waiting for liquidation/settlement...")
        time.sleep(15)
        return

    # 2. Safety Cleanup: Clear open buy orders on watchlist
    for sym in WATCHLIST:
        try:
            session.cancel_all_orders(category="spot", symbol=sym)
        except Exception:
            pass
            
    # 3. Select Dip Candidate
    symbol, buy_price_val, buy_price, qty_val, qty, tp_price_val, tp_price, current_price, est_profit = select_best_dip_candidate(rules_cache)
    tick_size, base_precision, price_decimals, qty_decimals = rules_cache[symbol]
    
    # 4. Submit Limit Buy Order
    try:
        buy_order = session.place_order(
            category="spot", symbol=symbol, side="Buy",
            orderType="Limit", qty=qty, price=buy_price, timeInForce="GTC"
        )
        order_id = buy_order['result']['orderId']
        start_time = time.time()
        
        send_telegram_alert(
            f"🤖 *NEW DIP LIMIT ORDER — Cycle #{cycle_count}*\n\n"
            f"• *Token:* {symbol}\n"
            f"• *Current Price:* ${current_price:,.2f}\n"
            f"• *Target Dip Entry:* ${buy_price}\n"
            f"• *Take Profit Target:* ${tp_price}\n"
            f"• *Timeout:* 15 Minutes"
        )
    except Exception as e:
        print(f"❌ Failed to place entry order on {symbol}: {e}")
        return

    # 5. Order Monitoring Loop
    while True:
        try:
            elapsed_time = time.time() - start_time
            res = session.get_open_orders(category="spot", symbol=symbol, orderId=order_id)
            open_orders = res['result']['list']
            
            # CASE A: Order Filled
            if not open_orders:
                time.sleep(2)
                monitor_position_with_trailing_stop(
                    symbol, buy_price_val, qty_val, qty_decimals, 
                    price_decimals, tick_size, tp_price_val, cycle_count
                )
                break
            
            # CASE B: 15-Minute Timeout Reached
            elif elapsed_time >= TIMEOUT_SECONDS:
                try:
                    session.cancel_order(category="spot", symbol=symbol, orderId=order_id)
                    send_telegram_alert(f"⏰ *ORDER TIMEOUT — {symbol}*\n15-minute window expired. Order canceled; re-scanning market.")
                    log_trade_to_csv(cycle_count, symbol, order_id, buy_price, 0.0, qty, ORDER_VALUE_USDT, 0.0, "CANCELED_TIMEOUT")
                except Exception as cancel_err:
                    print(f"❌ Error canceling order: {cancel_err}")
                break

            else:
                remaining = int(TIMEOUT_SECONDS - elapsed_time)
                status = open_orders[0]['orderStatus']
                print(f"⏱️ [{symbol}] Entry Pending at ${buy_price}... Status: {status} | Timeout in: {remaining}s")
                time.sleep(10)
                
        except Exception as err:
            print(f"⚠️ Error monitoring entry order: {err}")
            time.sleep(5)

def main():
    print("🚀 Initializing Full-Suite Autonomous Trading Engine...")
    init_csv_log()
    send_telegram_alert("🚀 *Bybit Autonomous Trading Engine Started!*\nMonitoring BTCUSDT, ETHUSDT, and SOLUSDT...")
    
    rules_cache = {}
    for sym in WATCHLIST:
        try:
            rules_cache[sym] = get_symbol_rules(sym)
            print(f"✅ Loaded exchange precision rules for {sym}")
        except Exception as e:
            print(f"❌ Failed to load rules for {sym}: {e}")
            return
            
    cycle = 1
    while True:
        try:
            run_single_cycle(cycle, rules_cache)
            cycle += 1
            time.sleep(COOL_DOWN_SECONDS)
        except KeyboardInterrupt:
            send_telegram_alert("🛑 *Trading Bot Stopped Manually (Ctrl+C).*")
            print("\n🛑 Hand-stop detected (Ctrl+C). Exiting.")
            break
        except Exception as global_err:
            print(f"⚠️ Global loop exception: {global_err}. Resuming in 15 seconds...")
            time.sleep(15)

if __name__ == "__main__":
    main()