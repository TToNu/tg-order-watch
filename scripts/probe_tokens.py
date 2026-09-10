import base64
import json
import urllib.request

blob = "aHR0cHM6Ly9jbG91ZC5kb2xwaGluLnRlY2gvYXBpL3YxOjpleUowZVhBaU9pSktWMVFpTENKaGJHY2lPaUpTVXpJMU5pSjkuZXlKaGRXUWlPaUl4SWl3aWFuUnBJam9pT1dNd05UQTBZVFl4WkRFNE5EZGxaV0V3TURWaE16RmhaREUzTm1GaVpqRmtOamcxT0RjNFpUZ3haamxtTURoallUYzBNRFUxTlROak5USTBZVFZrTURFNU1qSmhNMlkwTlRNMU5qazJPV01pTENKcFlYUWlPakUzT0RnNU9ESXdOell1TURFNE1qYzFMQ0p1WW1ZaU9qRTNPRGc1T0RJd056WXVNREU0TWpnc0ltVjRjQ0k2TVRrME5qYzBPRFEzTmk0d01UUXlNaXdpYzNWaUlqb2lZelF5WkdRMU1qVXRZalEzTUMwMFltUXpMVGs0TW1FdE5UUTNNMlJtT0RVMk1XVTNJaXdpYzJOdmNHVnpJanBiWFgwLkVHRmRPd0hBNmUxWVF2cTJuUUNfTk95N2dsNHBQa0Q2WlQ3aHFUOUJ1dHVDcV8ySkFxZkJ4WjQ2M2xpdHdocDR1LW4zRV9JUXZGQWRVM2N1cHhUTlpaMDRmUkcyTTBxR0hWdUxsZ2F2cmlNZVhkX3Q3SXlOVThRcVlnX1gyenRSRGtISGU2MFhqQkFyTkVZUkMzYW9KYkFjV2llcTVMeFd1d25FU2Vhd3JlM1RQX0hGeEZoWFozRUNrWU1BSzVtckhFay1iNDBtZEVRaVRaU2gwOWI5SjdPTnU2WG9pTWo4YmREeDF3czBCN0ZQQkM0NmpkYUJfWGREQko5SkhyQUZKVHhNZmR3UXpYWGNmZmRSZ3JxQ2ZtMU8tbkJaNjVtUDBXRW5TTXIwdThXU1BiRzRFaG4tcHh1Z2o2SXo3b1ZNWnlUQlU2Zk9mR3hGNnZhbTRGNzYxc2xGS3dHN1p1cHZ3VzNMRC11anZRN2JQeEMzaWkydlVxaTdrYnVWaFlkT2o2V3IwZ0dNc0tqM2VsZWctNFJYNGw1ZXoyWk02X1p6TENUeTVmd0g0YktoQ25qUDFsQ09XeVpnWFZEbnVYMkFTVU5pMy1HMmNia0lsM1BTV3lxb01wMTN2UThZbmRYa0tKNFI3eE1BOGpkMmY5M2dpY3Y4Y1BDU1BBTEsybHc3bS04U0p0b2ViemFVVmlYRkE3bjdaNzZKQnJkWDU2cm9VSTdhZEVnSFpJOWZYclZvSTMxbjVWVy1TVk9UampUbF96bEFOcHRvVTlqMEpGbzJpQ1J4ZkVNNW90WlFxcU1aUWFhX3R6UHNXXzA2MEltbTUyOENZRWNGVWxYQy1xcnh0enJCOVZSRVpoaVQ3bXR2NmJScVNzMjdia0o0RDRueTZVUTZQRkRZMmpROjpjbG91ZA=="
decoded = base64.b64decode(blob).decode()
print("decoded cloud key:", decoded[:120], "...")

cloud_jwt = decoded.split(":", 1)[1].rsplit(":", 1)[0]

variants = {
    "session-token:integration-jwt": None,  # already tried
    "session-token:cloud-jwt": cloud_jwt,
    "session-token:full-blob": blob,
}
integration = json.load(open(r"C:\Users\alexa\.zcode\workspace\default\tg-order-watch\scripts\dolphin_token.json", encoding="utf-8"))["token"]

def try_local(header: str, value: str) -> None:
    req = urllib.request.Request("http://127.0.0.1:3001/browser_profiles?page=1&limit=5",
                                 headers={header: value})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode()
            print(f"OK   {header}: {body[:150]}")
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            body = e.read().decode()[:120]
        print(f"FAIL {header}: {body or e}")

try_local("session-token", cloud_jwt)
try_local("session-token", blob)
try_local("Authorization", f"Bearer {cloud_jwt}")
try_local("Authorization", f"Bearer {integration}")

# remote cloud API list profiles
for auth in (f"Bearer {cloud_jwt}", f"Bearer {blob}", blob, cloud_jwt):
    req = urllib.request.Request("https://cloud.dolphin.tech/api/v1/browser_profiles?page=1&limit=5",
                                 headers={"Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("CLOUD OK:", r.read().decode()[:200])
            break
    except Exception as e:
        detail = ""
        if hasattr(e, "read"):
            detail = e.read().decode()[:150]
        print("CLOUD FAIL:", detail or e)
