import os
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

session = HTTP(
    testnet=False,
    api_key=API_KEY,
    api_secret=API_SECRET,
)

def check_balances():
    print("==========================================")
    print("🔍 Fetching Bybit Wallet Balances...")
    print("==========================================")
    
    # 1. Fetch Unified Account USDT Balance
    try:
        res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        result = res.get("result", {}).get("list", [])
        if result:
            for item in result:
                for c in item.get("coin", []):
                    if c.get("coin") == "USDT":
                        print(f"[UNIFIED ACCOUNT]")
                        print(f"  Wallet Balance: {c.get('walletBalance')} USDT")
                        print(f"  Available     : {c.get('availableToWithdraw', c.get('equity'))} USDT")
                        print(f"  Total Equity  : {c.get('equity')} USDT")
                        print("------------------------------------------")
    except Exception as e:
        print(f"Unified Account query error: {e}")

    # 2. Fetch Funding Account USDT Balance
    try:
        res_fund = session.get_coins_balance(accountType="FUND", coin="USDT")
        result_fund = res_fund.get("result", {}).get("balance", [])
        for c in result_fund:
            if c.get("coin") == "USDT":
                print(f"[FUNDING ACCOUNT]")
                print(f"  Wallet Balance: {c.get('walletBalance')} USDT")
                print(f"  Transferable  : {c.get('transferBalance')} USDT")
                print("------------------------------------------")
    except Exception as e:
        print(f"Funding Account query error: {e}")

    print("==========================================")

if __name__ == "__main__":
    check_balances()