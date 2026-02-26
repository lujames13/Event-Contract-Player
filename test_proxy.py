import os
import requests
from dotenv import load_dotenv

load_dotenv()

p_addr = os.getenv("WEBSHARE_PROXY_ADDRESS")
p_port = os.getenv("WEBSHARE_PROXY_PORT")
p_user = os.getenv("WEBSHARE_PROXY_USERNAME")
p_pass = os.getenv("WEBSHARE_PROXY_PASSWORD")

if p_addr:
    proxy_url = f"http://{p_user}:{p_pass}@{p_addr}:{p_port}"
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    print(proxy_url)

try:
    resp = requests.get("https://api.ipify.org?format=json", timeout=5)
    print("My IP via requests:", resp.json())
except Exception as e:
    print("Error:", e)
