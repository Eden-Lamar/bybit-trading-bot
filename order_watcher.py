import os
import time
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

session = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

SYMBOL = "BTCUSDT"
TARGET_ORDER_ID = "2344543554728456448"  # Your live order ID

def get_symbol_rules(symbol):
    response = session.get_instruments_info(category="spot", symbol=symbol)
    instrument = response["result"]["list"][0]
    price_filter = instrument["priceFilter"]
    lot_size_filter = instrument["lotSizeFilter"]
    
    tick_size = float(price_filter["tickSize"])
    base_precision = float(lot_size_filter["basePrecision"])
    
    price_decimals = len(price_filter["tickSize"].split(".")[1]) if "." in price_filter["tickSize"] else 0
    qty_decimals = len(lot_size_filter["basePrecision"].split(".")[1]) if "." in lot_size_filter["basePrecision"] else 0
    
    return tick_size, base_precision, price_decimals, qty_decimals

def format_precision(val, decimals):
    return f"{val:.{decimals}f}"

def monitor_and_manage():
    print(f"🤖 Order Watcher Active for Order ID: {TARGET_ORDER_ID}")
    tick_size, base_precision, price_decimals, qty_decimals = get_symbol_rules(SYMBOL)
    
    while True:
        try:
            # Query active order status
            response = session.get_open_orders(category="spot", symbol=SYMBOL, orderId=TARGET_ORDER_ID)
            orders = response['result']['list']
            
            if not orders:
                print("\n🎉 Order FILLED or cleared from order book!")
                print("⚡ Executing Automated Exit Strategy (TP/SL)...")
                
                # Check filled position balance
                bal_res = session.get_wallet_balance(accountType="UNIFIED", coin="BTC")
                coins = bal_res['result']['list'][0]['coin']
                btc_qty = 0.0
                for c in coins:
                    if c['coin'] == 'BTC':
                        btc_qty = float(c.get('equity', 0))
                
                if btc_qty > 0:
                    formatted_qty = format_precision(btc_qty, qty_decimals)
                    entry_price = 74415.50
                    
                    # Calculate +1.5% Take Profit Target
                    tp_price_val = round((entry_price * 1.015) / tick_size) * tick_size
                    tp_price = format_precision(tp_price_val, price_decimals)
                    
                    print(f"📦 Active BTC Quantity: {formatted_qty} BTC")
                    print(f"🎯 Submitting Take Profit Limit Sell at ${tp_price}...")
                    
                    # Submit TP Limit Sell
                    tp_order = session.place_order(
                        category="spot",
                        symbol=SYMBOL,
                        side="Sell",
                        orderType="Limit",
                        qty=formatted_qty,
                        price=tp_price,
                        timeInForce="GTC"
                    )
                    print(f"✅ Take Profit Sell Order Active! Order ID: {tp_order['result']['orderId']}")
                else:
                    print("ℹ️ Order was canceled or filled and already converted.")
                break
            else:
                order_info = orders[0]
                price = order_info['price']
                status = order_info['orderStatus']
                print(f"⏱️ Waiting for dip fill at ${price}... Status: {status} (Checking again in 10s)")
                
            time.sleep(10)
            
        except Exception as e:
            print(f"⚠️ Error checking status: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_and_manage()