import os
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

session = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

def check_open_orders():
    try:
        response = session.get_open_orders(category="spot", symbol="BTCUSDT")
        orders = response['result']['list']
        
        print("==========================================")
        print("📋 Active Bybit Spot Open Orders:")
        print("==========================================")
        
        if not orders:
            print("ℹ️ No open orders found (Order may have filled or been canceled).")
        else:
            for order in orders:
                print(f"Order ID  : {order['orderId']}")
                print(f"Side      : {order['side']} {order['symbol']}")
                print(f"Price     : ${order['price']}")
                print(f"Qty (BTC) : {order['qty']}")
                print(f"Status    : {order['orderStatus']}")
                print("------------------------------------------")
    except Exception as e:
        print(f"❌ Error querying open orders: {e}")

if __name__ == "__main__":
    check_open_orders()