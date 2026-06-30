import urllib.request, urllib.error
try:
    print(urllib.request.urlopen('https://ishimusa-psi.vercel.app/api/auth/fix-db').read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code)
    print(e.read().decode('utf-8'))
except Exception as e:
    print("OTHER ERROR:", str(e))
