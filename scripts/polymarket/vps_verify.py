#!/usr/bin/env python3
import sys
import json
import time
import socket
import ssl
import subprocess
from datetime import datetime, timezone
import argparse

def get_vm_info():
    info = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "vm_provider": "GCP/Unknown",
        "vm_region": "unknown",
        "vm_ip_masked": "unknown",
        "python_version": sys.version.split()[0]
    }
    
    # Try to get GCP region from metadata
    try:
        # http://metadata.google.internal/computeMetadata/v1/instance/zone
        resp = subprocess.check_output([
            "curl", "-s", "-H", "Metadata-Flavor: Google", 
            "http://metadata.google.internal/computeMetadata/v1/instance/zone"
        ], timeout=2).decode().strip()
        if resp:
            info["vm_provider"] = "GCP"
            info["vm_region"] = resp.split("/")[-1]
    except:
        pass
        
    # Try to get public IP
    try:
        ip = subprocess.check_output(["curl", "-s", "ifconfig.me"], timeout=2).decode().strip()
        if ip:
            parts = ip.split(".")
            if len(parts) == 4:
                info["vm_ip_masked"] = f"{parts[0]}.{parts[1]}.xxx.xxx"
    except:
        pass
        
    return info

def test_geoblock():
    try:
        import requests
    except ImportError:
        return {"status": "FAIL", "error": "requests not installed"}
        
    url = "https://polymarket.com/api/geoblock"
    start = time.time()
    try:
        resp = requests.get(url, timeout=10)
        latency = (time.time() - start) * 1000
        data = resp.json()
        return {
            "status": "PASS" if resp.status_code == 200 else "FAIL",
            "blocked": data.get("blocked", True),
            "raw_response": data,
            "latency_ms": round(latency, 2)
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_clob_latency(samples=100):
    try:
        import requests
    except ImportError:
        return {"status": "FAIL", "error": "requests not installed"}

    url = "https://clob.polymarket.com/time"
    latencies = []
    # Reduce samples for local testing if needed, but spec says 100
    for _ in range(samples):
        start = time.time()
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                latencies.append((time.time() - start) * 1000)
        except:
            pass
    
    if not latencies:
        return {"status": "FAIL", "error": "All requests failed"}
    
    latencies.sort()
    mean_val = sum(latencies) / len(latencies)
    
    return {
        "status": "PASS",
        "samples": len(latencies),
        "p50_ms": round(latencies[int(len(latencies)*0.5)], 2),
        "p95_ms": round(latencies[int(len(latencies)*0.95)], 2),
        "p99_ms": round(latencies[int(len(latencies)*0.99)], 2),
        "mean_ms": round(mean_val, 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2)
    }

def test_gamma_api():
    try:
        import requests
    except ImportError:
        return {"status": "FAIL", "error": "requests not installed"}

    url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5"
    start = time.time()
    try:
        resp = requests.get(url, timeout=10)
        latency = (time.time() - start) * 1000
        data = resp.json()
        return {
            "status": "PASS" if resp.status_code == 200 else "FAIL",
            "http_status": resp.status_code,
            "events_count": len(data) if isinstance(data, list) else 0,
            "latency_ms": round(latency, 2)
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_clob_markets():
    try:
        import requests
    except ImportError:
        return {"status": "FAIL", "error": "requests not installed"}

    url = "https://clob.polymarket.com/markets"
    start = time.time()
    try:
        resp = requests.get(url, timeout=10)
        latency = (time.time() - start) * 1000
        data = resp.json()
        count = 0
        token_id = None
        if isinstance(data, list):
            count = len(data)
            if count > 0:
                # Find a token_id for the next test
                for m in data:
                    tokens = m.get("tokens")
                    if tokens and isinstance(tokens, list) and len(tokens) > 0:
                        token_id = tokens[0].get("token_id")
                        if token_id: break
        
        return {
            "status": "PASS" if resp.status_code == 200 else "FAIL",
            "http_status": resp.status_code,
            "markets_count": count,
            "latency_ms": round(latency, 2),
            "_token_id": token_id
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_clob_orderbook(token_id):
    if not token_id:
        return {"status": "SKIPPED", "error": "No token_id provided"}
    try:
        import requests
    except ImportError:
        return {"status": "FAIL", "error": "requests not installed"}

    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    start = time.time()
    try:
        resp = requests.get(url, timeout=10)
        latency = (time.time() - start) * 1000
        data = resp.json()
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        best_bid = bids[0].get("price") if bids else None
        best_ask = asks[0].get("price") if asks else None
        spread = None
        if best_bid and best_ask:
            try:
                spread = round(abs(float(best_ask) - float(best_bid)), 6)
            except: pass
            
        return {
            "status": "PASS" if resp.status_code == 200 else "FAIL",
            "token_id": token_id,
            "bids_count": len(bids),
            "asks_count": len(asks),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": str(spread) if spread is not None else None,
            "latency_ms": round(latency, 2)
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def test_websocket():
    url = "ws-subscriptions-clob.polymarket.com"
    port = 443
    start = time.time()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((url, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=url) as ssock:
                request = (
                    f"GET /ws/market HTTP/1.1\r\n"
                    f"Host: {url}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                    f"Sec-WebSocket-Version: 13\r\n"
                    f"\r\n"
                )
                ssock.sendall(request.encode())
                
                ssock.settimeout(2.0)
                response = b""
                try:
                    while True:
                        chunk = ssock.recv(4096)
                        if not chunk: break
                        response += chunk
                        if b"\r\n\r\n" in response: break
                except socket.timeout:
                    pass
                
                resp_text = response.decode(errors='ignore')
                duration = time.time() - start
                
                if "101 Switching Protocols" in resp_text:
                    return {
                        "status": "PASS",
                        "connected": True,
                        "duration_seconds": round(duration, 2),
                        "error": None
                    }
                else:
                    status_line = resp_text.splitlines()[0] if resp_text else "No response"
                    return {
                        "status": "FAIL",
                        "connected": False,
                        "duration_seconds": round(duration, 2),
                        "error": f"Handshake failed: {status_line}"
                    }
    except Exception as e:
        return {
            "status": "FAIL",
            "connected": False,
            "error": str(e)
        }

def test_l1_auth():
    try:
        from eth_account import Account
        import requests
    except ImportError:
        return {"status": "SKIPPED", "error": "eth-account not installed"}
        
    try:
        # Create a temp wallet
        acc = Account.create()
        wallet_address = acc.address
        
        # Test endpoint to check for geoblock on authenticated routes
        url = "https://clob.polymarket.com/auth/api-key"
        
        # We don't sign a real message because we don't need a VALID key, 
        # just to see if the IP is blocked (403 vs 401/400)
        headers = {
            "POLY-ADDRESS": wallet_address,
            "POLY-SIGNATURE": "0x" + "0" * 130, # Dummy signature
            "POLY-TIMESTAMP": str(int(time.time())),
            "POLY-NONCE": "0"
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            is_geoblocked = False
            if resp.status_code == 403:
                try:
                    if "blocked" in resp.text.lower():
                        is_geoblocked = True
                except: pass
            
            # If we get 400 or 401, it means the IP passed WAF and reached the app
            status = "PASS" if not is_geoblocked else "FAIL"
            
            return {
                "status": status,
                "wallet_address": wallet_address,
                "api_key_derived": False,
                "http_status": resp.status_code,
                "is_geoblocked": is_geoblocked,
                "error": None if status == "PASS" else f"Geoblocked: {resp.text[:200]}"
            }
        except Exception as e:
            return {"status": "FAIL", "error": str(e)}
            
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-l1-auth", action="store_true")
    args = parser.parse_args()
    
    results = {
        "meta": get_vm_info(),
        "tests": {}
    }
    
    # Run tests
    results["tests"]["geoblock"] = test_geoblock()
    results["tests"]["clob_latency"] = test_clob_latency(100)
    results["tests"]["gamma_api"] = test_gamma_api()
    
    m_res = test_clob_markets()
    token_id = m_res.pop("_token_id", None)
    results["tests"]["clob_markets"] = m_res
    
    results["tests"]["clob_orderbook"] = test_clob_orderbook(token_id)
    results["tests"]["websocket"] = test_websocket()
    
    if args.with_l1_auth:
        results["tests"]["l1_auth"] = test_l1_auth()
    else:
        results["tests"]["l1_auth"] = {"status": "SKIPPED", "reason": "CLI flag not set"}
        
    # Conclusion
    geoblock = results["tests"]["geoblock"]
    clob_lat = results["tests"]["clob_latency"]
    l1 = results["tests"].get("l1_auth", {})
    
    geoblock_passed = geoblock.get("status") == "PASS" and not geoblock.get("blocked", True)
    datacenter_ip_accepted = geoblock_passed
    clob_latency_acceptable = clob_lat.get("status") == "PASS" and clob_lat.get("p95_ms", 999) < 100
    l1_auth_works = l1.get("status") == "PASS"
    
    overall = "PASS"
    if not geoblock_passed: overall = "FAIL"
    elif not l1_auth_works and args.with_l1_auth: overall = "CONDITIONAL_PASS"
    
    results["conclusion"] = {
        "geoblock_passed": geoblock_passed,
        "datacenter_ip_accepted": datacenter_ip_accepted,
        "clob_latency_acceptable": clob_latency_acceptable,
        "l1_auth_works": l1_auth_works,
        "overall": overall
    }
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
