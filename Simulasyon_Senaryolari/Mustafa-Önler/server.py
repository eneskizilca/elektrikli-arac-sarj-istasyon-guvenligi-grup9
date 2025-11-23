import asyncio
import logging
from websockets.server import serve
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MITM-SUNUCU] - %(message)s')

class ServerChargePoint(cp):
    
    @on('BootNotification')
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"BAĞLANTI İSTEĞİ: {charge_point_model} ({charge_point_vendor})")
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on('Heartbeat')
    async def on_heartbeat(self, **kwargs):
        logging.info("Heartbeat alındı.")
        return call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

async def on_connect(websocket, path):
    try:
        charge_point_id = path.strip('/')
        logging.info(f"Cihaz Bağlandı: {charge_point_id}")
        
        cp_instance = ServerChargePoint(charge_point_id, websocket)
        
        # İstemci ile iletişimi arka planda başlat
        cp_task = asyncio.create_task(cp_instance.start())
        
        # 1. Bekle (Bağlantı otursun)
        await asyncio.sleep(5)
        
        # 2. SENARYOYU TETİKLE: Şarj Başlatma Komutu Gönder
        logging.info("--- SENARYO ADIMI: Sunucu 'RemoteStartTransaction' gönderiyor ---")
        logging.info("BEKLENTİ: İstemci şarjı başlatmalı (0x200 yollamalı).")
        
        try:
            # Rastgele bir kart ID ile başlatma isteği
            await cp_instance.call(call.RemoteStartTransaction(id_tag="MITM-TEST-USER"))
            logging.info("✅ SUNUCU: Komut gönderildi ve istemci 'KABUL' etti.")
            logging.info("⚠️  ANALİZ: Eğer istemci loglarında 'MANİPÜLASYON' görüyorsanız saldırı başarılıdır.")
        except Exception as e:
            logging.error(f"Komut gönderim hatası: {e}")

        # Bağlantıyı açık tut
        await cp_task
        
    except Exception as e:
        logging.error(f"Bağlantı hatası: {e}")

async def main():
    async with serve(on_connect, '0.0.0.0', 9000):
        logging.info("--- CSMS SUNUCUSU (MITM TEST) BAŞLATILDI (Port: 9000) ---")
        await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
