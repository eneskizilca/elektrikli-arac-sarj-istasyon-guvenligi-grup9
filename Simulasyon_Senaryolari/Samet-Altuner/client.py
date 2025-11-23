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
        """
        NORMAL sayaç gönderimi (saldırı olmayan durum)
        """
        sayac = 0
        while True:
            sayac += 10
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{"value": str(sayac), "unit": "Wh"}]
            }]
            # await self.call(call.MeterValues(connector_id=1, meter_value=payload))
            await asyncio.sleep(5)

    # -------------------------------------------------------------
    #   ANOMALİ: Adaptive Sampling Manipülasyonu
    #   - Veri gönderim oranı düşürülüyor (8–25 sn arası)
    #   - Bazı paketler atlanıyor (missing samples)
    #   - Sayaç artışı düzensiz (flattening + jump)
    # -------------------------------------------------------------
    async def send_meter_values_anomalous(self):
        logging.info("!! ANOMALİ MODU AKTİF: Adaptive Sampling Manipülasyonu başlatıldı.")
        sayac = 0

        while True:

            # --- ÖRNEKLEME ORANI MANİPÜLASYONU (8–25 saniye) ---
            gecikme = asyncio.sleep.__defaults__
            anomalous_delay = asyncio.sleep
            rand_delay = int(8 + (17 * asyncio.get_running_loop().time()) % 17)
            await asyncio.sleep(rand_delay)

            # --- BAZI ÖLÇÜMLERİ GÖNDERMEME (missing sample) ---
            import random
            if random.random() < 0.30:  # %30 olasılık ile veri hiç gönderilmiyor
                logging.warning("Anomali: Kritik ölçüm SUNUCUYA gönderilmedi (missing sample).")
                continue

            # --- SAYAC BOZMA (flatten + jump) ---
            if random.random() < 0.40:
                sayac += 0  # düzleşme (ölçüm sabit kalıyor)
            else:
                sayac += random.randint(1, 40)  # düzensiz artış

            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{
                    "value": str(sayac),
                    "unit": "Wh"
                }]
            }]

            logging.info(f"Anomalili MeterValues → Sayaç: {sayac}, Gecikme: {rand_delay} s")

            await self.call(call.MeterValues(connector_id=1, meter_value=payload))


    # ----------- OCPP Komutları ------------
    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Başlat (Kart: {id_tag})")
        donanima_komut_yolla(0x200, [0x01, 0x01])
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction') 
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Durdur (TxID: {transaction_id})")
        donanima_komut_yolla(0x201, [0x00, 0x00])
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)


async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("Sunucuya bağlanıldı.")
        client = SablonChargePoint('CHARGER-001', ws)

        # --- NORMAL + ANOMALİ TASK'LARI ---
        await asyncio.gather(
            client.start(),
            client.send_boot_notification(),
            # client.send_meter_values(),              # Normal
            client.send_meter_values_anomalous()      # ANOMALİ: Adaptive Sampling Manipülasyonu
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus:
            can_bus.shutdown()
