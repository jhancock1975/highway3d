"""Exit 0 when Open WebUI's banner for the director's model is shown (present) or not (absent).

    python3 banner.py http://127.0.0.1:18081 present|absent
"""
import json
import sys
import urllib.request

base, want = sys.argv[1], sys.argv[2]


def call(method, path, body=None, token=None):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


token = call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})["token"]
shown = any(b.get("id") == "studio-llm-waiting" for b in call("GET", "/api/v1/configs/banners", token=token))
print("banner shown" if shown else "no banner")
sys.exit(0 if shown == (want == "present") else 1)
