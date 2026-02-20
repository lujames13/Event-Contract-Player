import requests
import json
import time
import argparse
from datetime import datetime

# Polygon Public RPC list
POLYGON_RPCS = [
    "https://polygon.llamarpc.com",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.drpc.org",
    "https://rpc.ankr.com/polygon"
]

# BTC/USD Aggregator on Polygon
# https://data.chain.link/feeds/polygon/mainnet/btc-usd
BTC_USD_AGGREGATOR = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

def get_latest_round_data(rpc_url, contract_address):
    """
    Calls latestRoundData() on a Chainlink Price Feed aggregator.
    Function signature: latestRoundData() returns (uint80, int256, uint256, uint256, uint80)
    Sighash: 0xfeaf968c
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {
                "to": contract_address,
                "data": "0xfeaf968c" # latestRoundData()
            },
            "latest"
        ],
        "id": 1
    }
    
    resp = requests.post(rpc_url, json=payload, timeout=10)
    resp.raise_for_status()
    result = resp.json().get("result")
    
    if not result or result == "0x":
        return None
        
    # parse 32-byte chunks
    result = result[2:] # remove 0x
    chunks = [result[i:i+64] for i in range(0, len(result), 64)]
    
    round_id = int(chunks[0], 16)
    answer = int(chunks[1], 16)
    started_at = int(chunks[2], 16)
    updated_at = int(chunks[3], 16)
    answered_in_round = int(chunks[4], 16)
    
    return {
        "round_id": round_id,
        "price": answer / 1e8, # Chainlink BTC-USD is 8 decimals
        "started_at": datetime.fromtimestamp(started_at),
        "updated_at": datetime.fromtimestamp(updated_at),
        "answered_in_round": answered_in_round
    }

def main():
    parser = argparse.ArgumentParser(description="Investigate Chainlink Oracle specs on Polygon.")
    args = parser.parse_args()

    print(f"--- Chainlink BTC/USD Oracle Investigation (Polygon) ---")
    print(f"Aggregator Address: {BTC_USD_AGGREGATOR}")
    
    data = None
    for rpc in POLYGON_RPCS:
        try:
            print(f"Trying RPC: {rpc}...")
            data = get_latest_round_data(rpc, BTC_USD_AGGREGATOR)
            if data:
                break
        except Exception as e:
            print(f"RPC {rpc} failed: {e}")
            continue
            
    if data:
        print(f"\n[Latest Round Data]")
        print(f"Price: ${data['price']:,.2f}")
        print(f"Last Updated: {data['updated_at']} UTC (Round {data['round_id']})")
        
        # Calculate time since update
        # Result is UTC, so compare with UTC now
        now_utc = datetime.utcnow()
        time_since_update = (now_utc - data['updated_at']).total_seconds()
        print(f"Seconds since last update: {time_since_update:.1f}s")
        
    else:
        print("Failed to retrieve latest round data from all RPCs.")

    print("\nNext steps: Check official dokumentation for heartbeat/deviation threshold.")
    print("Search query results suggested:")
    print("- Heartbeat: 27000s (on-chain fallback)")
    print("- Deviation Threshold: 0.05%")
    print("- Polymarket uses 'Data Streams' for resolution, which is lower latency.")

if __name__ == "__main__":
    main()
