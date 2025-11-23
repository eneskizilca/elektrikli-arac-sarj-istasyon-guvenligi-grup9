import asyncio
import logging
from websockets.server import serve
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result 
from ocpp.v16.enums import RegistrationStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MERKEZİ SİSTEM] - %(message)s')

# SİMÜLASYON PARAMETRELERİ
SITE_KAPASITESI = 50000  # Bu lokasyonun trafosu max 50kW kaldırır (50 Amper senaryosu)
DIGER_ARACLAR_YUKU = 30000 # Otoparktaki diğer araçlar halihazırda 30kW çekiyor

class SmartChargingCSMS(cp):
    
    @on('BootNotification')
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"Cihaz Bağlandı: {charge_point_model}")
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on('Heartbeat')
    async def on_heartbeat(self, **kwargs):
        return call_result.Heartbeat(current_time=datetime.now(timezone.utc).isoformat())

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        try:
            # 1. Gelen Veriyi Oku (Manipüle Edilmiş Veri)
            raw_value = meter_value[0]['sampled_value'][0]['value']
            bildirilen_tuketim = int(raw_value)
            
            logging.info(f"Rapor Alındı: İstasyon {bildirilen_tuketim}W tükettiğini iddia ediyor.")

            # 2. YÜK DENGELEME ALGORİTMASI (Smart Charging Logic)
            # Algoritma: (Toplam Kapasite) - (Bildirilen Tüketim) - (Diğer Araçlar) = Boş Kapasite
            # HATA BURADA: Algoritma "Bildirilen Tüketim"e güveniyor[cite: 2].
            
            tahmini_toplam_yuk = DIGER_ARACLAR_YUKU + bildirilen_tuketim
            bos_kapasite = SITE_KAPASITESI - tahmini_toplam_yuk
            
            logging.info(f"--- ALGORİTMA KARARI ---")
            logging.info(f"Algılanan Toplam Yük: {tahmini_toplam_yuk}W")
            logging.info(f"Hesaplanan Boş Kapasite: {bos_kapasite}W")

            if bos_kapasite > 10000:
                # CSMS kandırıldı! Boş yer var sanıyor.
                logging.info(f"✅ KARAR: Şebeke rahat. Diğer istasyonlara ek güç veriliyor (+10kW).")
                
                # --- FİZİKSEL GERÇEKLİK (SİMÜLASYON) ---
                # Gerçekte saldırgan 22000W çekiyor. Diğerleri 30000W çekiyor.
                # Ek güç verilirse diğerleri 40000W çekecek.
                # GERÇEK YÜK = 22000 (Saldırgan) + 40000 (Diğerleri) = 62000W
                # KAPASİTE = 50000W
                
                logging.error(f"🚨 SİBER-FİZİKSEL ÇÖKÜŞ: Gerçek Yük (62kW) > Kapasite (50kW)")
                logging.error(f"🔥🔥 SİGORTA ATTI! BÖLGESEL KESİNTİ (DoS) BAŞLADI 🔥🔥")
                
            else:
                logging.warning("Şebeke sınırda. Güç artırımı reddedildi.")

        except Exception as e:
            logging.error(f"Veri hatası: {e}")

        return call_result.MeterValues()

async def on_connect(websocket, path):
    cp = SmartChargingCSMS(path.strip('/'), websocket)
    await cp.start()

async def main():
    async with serve(on_connect, '0.0.0.0', 9000):
        logging.info(f"--- AKILLI ŞEBEKE YÖNETİMİ (Kapasite: {SITE_KAPASITESI}W) ---")
        await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass