import asyncio
import logging
import can
import websockets
import random  # Anomali için eklendi
from datetime import datetime, timezone, timedelta # Time drift için eklendi

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SFED-ISTEMCI] - %(message)s')

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

    async def send_boot_notification(self):
        request = call.BootNotification(
            charge_point_model="SecVolt-Charger",
            charge_point_vendor="SecVolt-Team"
        )
        response = await self.call(request)
        if response.status == RegistrationStatus.accepted:
            logging.info("BootNotification KABUL EDİLDİ.")
        return response

    async def send_meter_values(self):
        """ 
        ANOMALİ SENARYOSU: SFED (Stealthy Federated Energy Drift)
        Normal enerji tüketimine %0.5 - %2 arasında rastgele, sinsi bir ekleme yapar
        ve zaman damgasını hafifçe kaydırır.
        """
        energy_register = 0.0  # Sayaç başlangıcı
        
        # Bekleme süresi (Simülasyonun başlaması için)
        await asyncio.sleep(2) 
        logging.info("SFED Anomali Döngüsü Başlatılıyor...")

        while True:
            # 1. Normal Tüketim (Örn: Her periyotta 10 Wh)
            base_increment = 10.0 

            # 2. SFED MANİPÜLASYONU: %0.5 ile %2 arası drift (kayma) ekle
            drift_percentage = random.uniform(0.005, 0.02) # %0.5 - %2
            drift_amount = base_increment * drift_percentage
            
            # Anomali uygulanmış artış
            total_increment = base_increment + drift_amount
            energy_register += total_increment

            # 3. ZAMAN SENKRONİZASYONU BOZMA (Time Drift)
            # Saati -3 ile +3 saniye arasında rastgele kaydır
            time_jitter = random.uniform(-3, 3)
            current_time = datetime.now(timezone.utc) + timedelta(seconds=time_jitter)

            # Payload Hazırlama
            payload = [{
                "timestamp": current_time.isoformat(),
                "sampled_value": [
                    {
                        "value": f"{energy_register:.2f}", 
                        "context": "Sample.Periodic",
                        "format": "Raw",
                        "measurand": "Energy.Active.Import.Register",
                        "location": "Outlet",
                        "unit": "Wh"
                    }
                ]
            }]

            try:
                # Sunucuya gönder
                logging.info(f"[ANOMALI] Gönderiliyor -> Enerji: {energy_register:.2f} Wh (Eklenen Drift: +{drift_amount:.4f} Wh)")
                await self.call(call.MeterValues(connector_id=1, meter_value=payload))
            except Exception as e:
                logging.error(f"MeterValues Gönderim Hatası: {e}")

            # 10 saniyede bir gönderim (Periyodik)
            await asyncio.sleep(10)

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
        logging.info("Sunucuya bağlanıldı (SFED İstemcisi).")
        client = SablonChargePoint('CHARGER-001', ws)
        
        # Hem sistemi başlatıyoruz, hem boot atıyoruz, hem de anomali döngüsünü tetikliyoruz
        await asyncio.gather(
            client.start(),
            client.send_boot_notification(),
            client.send_meter_values() # Anomali fonksiyonunu buraya ekledik
        )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus: can_bus.shutdown()
