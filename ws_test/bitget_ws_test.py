import asyncio
import json
import websockets


async def bitget_ws():
    url = "wss://ws.bitget.com/v2/ws/public"

    subscribe_payload = {
        "op": "subscribe",
        "args": [
            {
                "instType": "USDT-FUTURES",
                "channel": "ticker",
                "instId": "BTCUSDT"
            }
        ]
    }

    try:
        async with websockets.connect(url) as websocket:
            print("Terhubung ke Bitget WebSocket!")

            await websocket.send(json.dumps(subscribe_payload))
            print("Berhasil mengirim permintaan subscribe.")

            while True:
                response = await websocket.recv()
                data = json.loads(response)
                print("Data diterima:", json.dumps(data, indent=2))

    except Exception as e:
        print(f"Terjadi kesalahan: {e}")


if __name__ == "__main__":
    asyncio.run(bitget_ws())