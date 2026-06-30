import urllib.request, urllib.error
req = urllib.request.Request(
    'https://ishimusa-psi.vercel.app/api/auth/register',
    data=b'{"email":"test@test.com","password":"password123"}',
    headers={'Content-Type': 'application/json'}
)
try:
    print(urllib.request.urlopen(req).read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTP ERROR:', e.code, e.read().decode('utf-8'))
