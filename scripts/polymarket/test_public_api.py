
import requests
import json
import time

def check_endpoint(name, url, method="GET", data=None):
    print(f"Testing {name}: {url}")
    start_time = time.time()
    try:
        if method == "GET":
            response = requests.get(url, timeout=10.0)
        else:
            response = requests.post(url, json=data, timeout=10.0)
        
        latency = (time.time() - start_time) * 1000
        print(f"  Status: {response.status_code}")
        print(f"  Latency: {latency:.2f}ms")
        
        try:
            body = response.json()
            print(f"  Body (truncated): {json.dumps(body)[:200]}...")
            return {
                "name": name,
                "url": url,
                "status": response.status_code,
                "latency": latency,
                "body": body
            }
        except:
            print(f"  Body: {response.text[:200]}...")
            return {
                "name": name,
                "url": url,
                "status": response.status_code,
                "latency": latency,
                "body": response.text
            }
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        print(f"  Error: {str(e)}")
        return {
            "name": name,
            "url": url,
            "status": "Error",
            "latency": latency,
            "error": str(e)
        }

def main():
    endpoints = [
        ("Geoblock API", "https://polymarket.com/api/geoblock"),
        ("Gamma API", "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5"),
        ("CLOB Public", "https://clob.polymarket.com/markets"),
        ("CLOB Health", "https://clob.polymarket.com/health"),
    ]
    
    results = []
    for name, url in endpoints:
        res = check_endpoint(name, url)
        results.append(res)
        time.sleep(1) # Be nice
        
    print("\nSummary:")
    for r in results:
        print(f"{r['name']}: {r['status']} ({r.get('latency', 0):.2f}ms)")

if __name__ == "__main__":
    main()
