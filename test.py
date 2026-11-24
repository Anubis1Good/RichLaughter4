import requests
print(requests.get("http://localhost:7777/debug-cluster-type").json())

