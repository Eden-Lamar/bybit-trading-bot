import os
import math
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Load environment variables
load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

session = HTTP(
    testnet=False,
    api_key=API_KEY,
    api_secret=API_SECRET,
)

SYMBOL = "BTCUSDT"
ORDER_VALUE_USDT = 6.0  # Allocation ($6.00 USDT)

def get_symbol_rules(symbol):
    """Fetch exact price tick size and quantity precision rules from Bybit."""
    response = session.get_instruments_info(category="spot", symbol=symbol)
    instrument = response["result"]["list"][0]
    
    price_filter = instrument["priceFilter"]
    lot_size_filter = instrument["lotSizeFilter"]
    
    tick_size = float(price_filter["tickSize"])
    base_precision = float(lot_size_filter["basePrecision"])
    
    # Calculate decimal places from precision steps
    price_decimals = len(price_filter["tickSize"].split(".")[1]) if "." in price_filter["tickSize"] else 0
    qty_decimals = len(lot_size_filter["basePrecision"].split(".")[1]) if "." in lot_size_filter["basePrecision"] else 0
    
    return tick_size, base_precision, price_decimals, qty_decimals

def get_spot_price(symbol):
    ticker = session.get_tickers(category="spot", symbol=symbol)
    price = float(ticker["result"]["list"][0]["lastPrice"])
    return price

def format_precision(val, decimals):
    """Formats float value strictly to expected decimal places."""
    return f"{val:.{decimals}f}"

def place_limit_buy():
    print(f"🤖 Initializing Trading Bot Strategy for {SYMBOL}...")
    
    # 1. Get Precision Rules & Market Price
    tick_size, base_precision, price_decimals, qty_decimals = get_symbol_rules(SYMBOL)
    current_price = get_spot_price(SYMBOL)
    print(f"📈 Current Market Price: ${current_price:,.2f}")

    # 2. Calculate Dip Buy Entry (0.5% dip) & Snap to Tick Size
    raw_buy_price = current_price * 0.995
    buy_price_val = round(raw_buy_price / tick_size) * tick_size
    buy_price = format_precision(buy_price_val, price_decimals)
    
    # 3. Calculate Quantity & Snap to Qty Precision
    raw_qty = ORDER_VALUE_USDT / buy_price_val
    qty_val = math.floor(raw_qty / base_precision) * base_precision
    qty = format_precision(qty_val, qty_decimals)

    # 4. Calculate TP (+1.5%) and SL (-1.0%)
    tp_val = round((buy_price_val * 1.015) / tick_size) * tick_size
    sl_val = round((buy_price_val * 0.990) / tick_size) * tick_size
    take_profit = format_precision(tp_val, price_decimals)
    stop_loss = format_precision(sl_val, price_decimals)

    print(f"\n--- Strategy Order Calculations ---")
    print(f"  Target Buy Price : ${buy_price}")
    print(f"  Order Size (USDT): ${ORDER_VALUE_USDT:.2f}")
    print(f"  Quantity (BTC)   : {qty}")
    print(f"  Take Profit      : ${take_profit} (+1.5%)")
    print(f"  Stop Loss        : ${stop_loss} (-1.0%)")

    confirm = input("\n⚠️ Do you want to submit this LIVE Limit Buy order to Bybit? (y/n): ")
    
    if confirm.lower() == 'y':
        try:
            # Place Clean Spot Limit Order
            order = session.place_order(
                category="spot",
                symbol=SYMBOL,
                side="Buy",
                orderType="Limit",
                qty=qty,
                price=buy_price,
                timeInForce="GTC"
            )
            order_id = order['result']['orderId']
            print("==========================================")
            print(f"✅ Live Limit Buy Order Submitted to Bybit!")
            print(f"  Order ID: {order_id}")
            print(f"  Status  : Open on BTC/USDT Order Book at ${buy_price}")
            print("==========================================")
        except Exception as e:
            print(f"❌ Failed to place order: {e}")
    else:
        print("🛑 Execution canceled. No order submitted.")

if __name__ == "__main__":
    place_limit_buy()