import asyncio
import logging
import can
import websockets
import random
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus, Measurand, UnitOfMeasure
from ocpp.routing import on

# Log formatını biraz detaylandırdım
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SECVOLT-CLIENT] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
try:
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan')
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI.")
except Exception:
    logging.warning("Donanım bulunamadı, simülasyon modunda devam ediliyor.")
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
    
    # Sızdırılacak Gizli Veri (Covert Data)
    SECRET_DATA = "SECVOLT_PASS" 

    def text_to_bits(self, text):
        """Metni binary (010101...) stringine çevirir."""
        bits = bin(int.from_bytes(text.encode(), 'big'))[2:]
        return bits.zfill(8 * ((len(bits) + 7) // 8))

    async def send_boot_notification(self):
        """Sunucuya 'Ben geldim' der."""
        request = call.BootNotification(
            charge_point_model="SecVolt-Simulator",
            charge_point_vendor="CyberSecLink"
        )
        response = await self.call(request)
        if response.status == RegistrationStatus.accepted:
            logging.info("BootNotification KABUL EDİLDİ. Şarj noktası hazır.")
            # Bağlantı kabul edildikten sonra veri sızdırma başlasın
            asyncio.create_task(self.send_meter_values())

    async def send_meter_values(self):
        """
        Energy Covert Channel Anomali Simülasyonu:
        Voltaj değerlerindeki mikro oynamalarla (dalgalanma) veri sızdırır.
        """
        sayac_wh = 1000 # Başlangıç enerji değeri
        secret_bits = self.text_to_bits(self.SECRET_DATA)
        bit_index = 0
        
        logging.info(f"ANOMALI BAŞLATILIYOR: '{self.SECRET_DATA}' verisi voltaj dalgalanmalarıyla sızdırılıyor...")

        while True:
            # 1. Normal Enerji Artışı (Şarj devam ediyor gibi görünsün)
            sayac_wh += 10 

            # 2. Anomali Enjeksiyonu (Covert Channel Logic)
            # Sıradaki biti al
            current_bit = secret_bits[bit_index % len(secret_bits)]
            bit_index += 1

            # Temel Voltaj Değeri (Türkiye Standartı)
            base_voltage = 220.0
            
            # Eğer bit '1' ise mikro dalgalanma yarat (+0.5V), '0' ise stabil kal
            if current_bit == '1':
                fluctuation = 0.5  # Bu değer anomaliyi oluşturur
                status_msg = "[BIT: 1] Dalgalanma Enjekte Edildi"
            else:
                fluctuation = 0.0
                status_msg = "[BIT: 0] Normal Seyir"

            injected_voltage = base_voltage + fluctuation

            # 3. Payload Hazırlığı (OCPP Standartlarına Uygun)
            # Hem toplam enerjiyi (Wh) hem de anomali içeren voltajı (V) gönderiyoruz
            payload = [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampled_value": [
                        # Normal Sayaç Verisi
                        {"value": str(sayac_wh), "context": "Sample.Periodic", "format": "Raw", "measurand": "Energy.Active.Import.Register", "location": "Outlet", "unit": "Wh"},
                        # ANOMALİ İÇEREN VOLTAJ VERİSİ
                        {"value": str(injected_voltage), "context": "Sample.Periodic", "format": "Raw", "measurand": "Voltage", "location": "Outlet", "unit": "V"}
                    ]
                }
            ]

            logging.info(f"Rapor Gönderiliyor -> Enerji: {sayac_wh}Wh | Voltaj: {injected_voltage}V -> {status_msg}")

            # Sunucuya gönder
            try:
                await self.call(call.MeterValues(connector_id=1, meter_value=payload))
            except Exception as e:
                logging.error(f"Veri gönderim hatası: {e}")

            # Bir sonraki veri paketi için bekle (Gerçekçilik için 5 saniye)
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
    # URL'i kendi sunucu adresine göre düzenle
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("OCPP Sunucusuna (CSMS) bağlanıldı.")
        client = SablonChargePoint('CHARGER-001', ws)
        
        # Boot notification ve dinlemeyi aynı anda başlat
        await asyncio.gather(client.start(), client.send_boot_notification())

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("İstemci kapatılıyor...")
        if can_bus: can_bus.shutdown()
