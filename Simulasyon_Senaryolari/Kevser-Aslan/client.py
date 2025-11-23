import asyncio
import logging
import can
import websockets
import random
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
        """ NORMAL MeterValues Davranışı (değiştirmiyoruz) """
        sayac = 0
        while True:
            sayac += 10
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{"value": str(sayac), "unit": "Wh"}]
            }]
            # NORMAL davranış istersen burayı aç
            # await self.call(call.MeterValues(connector_id=1, meter_value=payload))

            await asyncio.sleep(5)


    # -------------------------------------------------------------
    #  ANOMALİ FONKSİYONU  (MeterValues Yeniden Ataması + Veri Bozma)
    # -------------------------------------------------------------
    async def send_anomalous_meter_values(self):
        """
        MeterValues Yeniden Ataması ile Haksız Faturalama ve Veri Bozması
        ANOMALİ SİMÜLASYONU:
        - Sayaç değerleri geri düşüyor / rastgele sıçrıyor
        - Sahte transactionId gönderiliyor (yeniden atama etkisi)
        - Değerler tutarsız ilerliyor (AI tarafından anomali olarak yakalanabilir)
        """
        sahte_transaction_id = random.randint(9000, 9999)
        sayac = 100

        logging.info(f"[ANOMALİ] Başlatıldı – Sahte Transaction ID: {sahte_transaction_id}")

        while True:
            # 🔥 Tutarsız sayaç oluşturma (ör: 100 → 250 → 120 → 500 → 80)
            sayac += random.choice([-50, 20, -10, 200, 300, -80, 150])

            if sayac < 0:
                sayac = random.randint(50, 150)

            # 🔥 Manipüle edilmiş veri paketi
            anomalous_payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{
                    "value": str(sayac),
                    "unit": "Wh",
                }]
            }]

            logging.warning(
                f"[ANOMALİ] Gönderilen Manipüle MeterValues -> "
                f"TxID: {sahte_transaction_id}, Değer: {sayac} Wh"
            )

            # 🔥 ANOMALİLİ MeterValues Gönderimi
            await self.call(
                call.MeterValues(
                    connector_id=1,
                    meter_value=anomalous_payload,
                    transaction_id=sahte_transaction_id
                )
            )

            await asyncio.sleep(5)


    # -------------------------------------------------------------
    #  REMOTE KONTROLLER
    # -------------------------------------------------------------
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


# -------------------------------------------------------------
#  İSTEMCİ BAŞLATMA (ANOMALİ FONKSİYONU EKLENDİ)
# -------------------------------------------------------------
async def main():
    uri = "ws://localhost:9000/CP001"
    async with websockets.connect(uri) as ws:
        global client
        client = SablonChargePoint("CP001", ws)

        # BootNotification gönder
        asyncio.create_task(client.send_boot_notification())

        # ANOMALİ BAŞLAT
        asyncio.create_task(client.send_anomalous_meter_values())

        # Normal OCPP döngüsünü başlat
        await client.start()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus:
            can_bus.shutdown()
