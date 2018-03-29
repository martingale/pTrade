import requests
import ast
import websocket
from websocket import create_connection
import json
import time
import hmac
import hashlib
from datetime import datetime

# historic
test = requests.get('https://api.bitfinex.com/v2/candles/trade:1m:tBTCUSD/hist')
myVal = ast.literal_eval(test.text)
print (myVal)


secret = 'CgeKhF7zf2hccD2o5bNZPNJCKFMis8O6gHqKrRmPkxD'
api_key = 'NWAnC6UF2CI9PlHL5JIuztZ1juaVEKnniop5uzvXWF9'

nonce = str(int(time.time() * 10000000))
auth_string = 'AUTH' + nonce
auth_sig = hmac.new(secret.encode(), auth_string.encode(),
                    hashlib.sha384).hexdigest()

payload = {'event': 'auth', 'apiKey': api_key, 'authSig': auth_sig,
           'authPayload': auth_string, 'authNonce': nonce}
payload = json.dumps(payload)

# websocket
ws = create_connection("wss://api.bitfinex.com/ws/2")

# [
#   0,
#   "on",
#   null,
#   {
#     "gid": 1,
#     "cid": 12345,
#     "type": "LIMIT",
#     "symbol": "tBTCUSD",
#     "amount": "1.0",
#     "price": "500",
#     "hidden": 0
#   }
# ]


# msg = {'event': 'subscribe', 'channel': 'ticker', 'symbol': 'tBTCUSD'}
# print type(msg)
# msg = json.dumps(msg)
# print str(msg)

cid = int(time.time())

order_msg = json.dumps([0, 'on', None,  {"gid": 1, "cid": cid, "type": "EXCHANGE MARKET", "symbol": "tBTCUSD", "amount": '-0.002', "hidden": 0}])
ws.send(str(payload))
for i in xrange(100):
    result = ws.recv()
    # if i == 6:
    #     # ws.send(order_msg)EXCHANGE LIMIT
    print result

