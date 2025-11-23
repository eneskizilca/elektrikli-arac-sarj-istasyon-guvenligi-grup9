import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [İSTEMCİ] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
try:
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan')
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI.")
except Exception:
    # Hata vermemesi için pass geçiyoruz, donanım yoksa simülasyon devam eder
    can_bus = None

def donanima_komut_yolla(can_id, data):
    if can_bus:
        try:
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            can_bus.send(msg)
            logging.info(f"Donanıma İletildi -> ID: {hex(can_id)} Data: {data}")
        except Exception as e:
            logging.error(f"Donanım Hatası: {e}")

class SablonChargePoint(cp):

    async def send_meter_values(self):
        """ Düzenli enerji raporu gönderir (NORMAL DAVRANIŞ) """
        sayac = 0
        while True:
            sayac += 10 # Normal artış
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{"value": str(sayac), "unit": "Wh"}]
            }]
            # Göndermek için alttaki satırı aktif edebilirsiniz
            # await self.call(call.MeterValues(connector_id=1, meter_value=payload))
            await asyncio.sleep(5)

    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Başlat (Kart: {id_tag})")
        donanima_komut_yolla(0x200, [0x01, 0x01]) # Röleyi aç
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction')
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Durdur (TxID: {transaction_id})")
        donanima_komut_yolla(0x201, [0x00, 0x00]) # Röleyi kapat
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("Sunucuya bağlanıldı.")
        client = SablonChargePoint('CHARGER-001', ws)
        await asyncio.gather(client.start(), client.send_boot_notification())

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus: can_bus.shutdown()