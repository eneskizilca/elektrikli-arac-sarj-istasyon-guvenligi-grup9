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
    else:
        # Donanım yoksa da loglayoruz (simülasyon için)
        logging.info(f"[SIM] Donanıma İletildi -> ID: {hex(can_id)} Data: {data}")

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
            # Normal davranışta gerçek MeterValues gönderimi (yorumda, isteğe bağlı)
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

    # ---------------------------
    # ANOMALİ (Evil Twin) MANTIKLARI
    # ---------------------------
    async def anomaly_monitor(self):
        """
        Arka planda çalışan görev:
        - Rastgele (veya kendi kuralınıza göre) anomali üretir.
        - Anomali tespit edilince send_anomaly_alert() çağrılır.
        - DONANIMA da uyarı (CAN) gönderilir.
        """
        logging.info("Anomali monitörü başlatıldı.")
        while True:
            # Her döngüde kısa bekle, sonra rastgele anomali olayı üretebiliriz.
            await asyncio.sleep(3)

            # Burada gerçek bir tespit mantığı/telemetri yerine simülasyon yapıyoruz.
            # Örnek: %10 olasılıkla "Evil Twin" türü bir anomali tetikleniyor.
            if random.random() < 0.10:
                # Simüle edilmiş anomali verileri
                anomaly_info = {
                    "type": "EvilTwin_SSID_Spoofing",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "details": {
                        "spoofed_ssid": "FreeWiFi-CHARGER-001",
                        "signal_strength_dbm": -30 + random.randint(-10, 10),
                        "source_mac": "AA:BB:CC:DD:EE:FF"
                    }
                }
                logging.warning(f"ANOMALİ TESPİTİ: {anomaly_info}")
                # Donanıma uyarı gönder (ör. alarm rölesi, LED vb)
                donanima_komut_yolla(0x300, [0xFF, 0x00])  # Simule alarm komutu
                # Sunucuya anomali raporu gönder
                try:
                    await self.send_anomaly_alert(anomaly_info)
                except Exception as e:
                    logging.error(f"Anomali raporu gönderilemedi: {e}")

                # Anomali tetiklendikten sonra kısa süre bekle (flood önleme)
                await asyncio.sleep(10)

    async def send_anomaly_alert(self, anomaly_info: dict):
        """
        Sunucuya 'anomaly' bilgisini gönderir.
        - OCPP standardının MeterValues çağrısını kullanıyoruz ama sampled_value içine
          context: "AnomalyDetected" ekleyerek sunucu tarafında ayrıştırılmasını kolaylaştırıyoruz.
        - İsterseniz burayı merkezi sunucunuza uygun başka bir OCPP çağrısına (vendor-specific)
          çevirebilirsiniz.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        # Birincil ölçüm: anomali id / kodunu veya 1/0 değeri gönderiyoruz.
        # Not: OCPP spesifikasyonu numerik string bekleyebilir, ama server tarafı
        # bu context'li kaydı "anomaly" olarak yorumlayabilir.
        payload = [{
            "timestamp": timestamp,
            "sampled_value": [
                {
                    "value": "1",  # 1 = anomaly present (sınırlı/sempatik gösterim)
                    "measurand": "Anomaly",
                    "context": "AnomalyDetected",
                    "format": "Raw",
                    "additional_info": str(anomaly_info)  # ekstra bilgi (parçalanıp loglanabilir)
                },
                # isteğe bağlı: aynı anda gerçek meter değeri de gönderebilirsiniz
                {
                    "value": str( random.randint(1000, 5000) ),
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh"
                }
            ]
        }]

        logging.info("Sunucuya anomali bildirimi gönderiliyor...")
        # OCPP MeterValues çağrısını kullanıyoruz
        await self.call(call.MeterValues(connector_id=1, meter_value=payload))
        logging.info("Anomali bildirimi gönderildi.")

async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("Sunucuya bağlanıldı.")
        client = SablonChargePoint('CHARGER-001', ws)

        # Mevcut davranışı bozmadan arka plan görevleri de başlatılıyor
        await asyncio.gather(
            client.start(),
            client.send_boot_notification(),
            client.anomaly_monitor()   # <-- anomali izleyicisini burada ekledik
        )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus: can_bus.shutdown()
