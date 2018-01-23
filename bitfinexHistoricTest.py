import requests
import ast
import websocket
from websocket import create_connection
import json

test = requests.get('https://api.bitfinex.com/v2/candles/trade:1D:tBTCUSD/last')
myVal = ast.literal_eval(test.text)
print (myVal)

ws = create_connection("wss://api.bitfinex.com/ws/2")
msg = {'event': 'subscribe', 'channel': 'ticker', 'symbol': 'tBTCUSD'}
print type(msg)
msg = json.dumps(msg)
print str(msg)
ws.send(str(msg))
for i in xrange(100):
    result = ws.recv()
    print result

