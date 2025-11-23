import asyncio
import logging
from websockets.server import serve
from datetime import datetime, timezone
from decimal import Decimal

from ocpp.v16 import ChargePoint as cp, call, call_result 
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SUNUCU] - %(message)s', handlers=[logging.StreamHandler()])

# --- Gözlemsel Savunma Parametreleri ---
# Finansal manipülasyonu hedefleyen Yanlış Veri Enjeksiyonu (YVE) tespiti için bir eşik belirleyelim.
# Normal bir şarj cihazının 10 saniye aralığında bu kadar enerji raporlaması mümkün değildir.
ANOMAL_SAYAC_ESIGI_WH = 2000000 # 2 MWh (2,000,000 Wh). Bu değer, anormal bir veri enjeksiyonunu işaret eder.

class SablonChargePoint(cp):
    
    def __init__(self, charge_point_id, websocket):
        super().__init__(charge_point_id, websocket)
        self.authorized_tags = {"USER-A123", "CPT-2024-001"} # Basit yetkili ID listesi simülasyonu
        logging.info(f"[{charge_point_id}] Yetkili ID'ler: {self.authorized_tags}")


    @on('BootNotification')
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"[{self.id}] BAĞLANTI İSTEĞİ: {charge_point_model} ({charge_point_vendor})")
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on('Authorize')
    async def on_authorize(self, id_tag, **kwargs):
        if id_tag in self.authorized_tags:
            logging.info(f"[{self.id}] YETKİLENDİRME: ID Tag '{id_tag}' KABUL EDİLDİ.")
            status = 'Accepted'
        else:
            # ANOMALİ TESPİTİ (Kaba Kuvvet/Kimlik Sahtekarlığı Denemesi)
            logging.warning(f"[{self.id}] 🚨 ANOMALİ DENEMESİ (ID Sahtekarlığı): Yetkisiz ID '{id_tag}' REDDEDİLDİ.")
            status = 'Invalid'
            
        return call_result.Authorize(id_tag_info={'status': status})


    @on('Heartbeat')
    async def on_heartbeat(self, **kwargs):
        logging.info(f"[{self.id}] Heartbeat (Yaşam Sinyali) alındı.")
        return call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        try:
            # Sadece ilk değeri alıp enerji okumasını kontrol et
            value_str = meter_value[0]['sampled_value'][0]['value']
            value = Decimal(value_str)
            
            # ANOMALİ TESPİTİ (Yanlış Veri Enjeksiyonu - YVE)
            if value > ANOMAL_SAYAC_ESIGI_WH:
                logging.critical(f"[{self.id}] ‼️ KRİTİK ANOMALİ TESPİTİ (YVE): Anormal sayaç değeri alındı: {value} Wh! Eşik: {ANOMAL_SAYAC_ESIGI_WH} Wh.")
                # Bu noktada, şarj noktasını karantinaya almak veya işlemi durdurmak gibi savunma eylemleri başlatılmalıdır.
            else:
                logging.info(f"[{self.id}] ENERJİ RAPORU: {value} Wh (Konnektör: {connector_id})")
                
        except Exception as e:
            logging.error(f"[{self.id}] MeterValues veri okuma hatası: {e}")
        return call_result.MeterValues()
    
    @on('StartTransaction')
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        if id_tag not in self.authorized_tags:
            # ANOMALİ TESPİTİ: StartTransaction yetkilendirme kontrolü (Kimlik Sahtekarlığı)
            logging.critical(f"[{self.id}] ⚠️ KRİTİK ANOMALİ TESPİTİ (Kimlik Sahtekarlığı): Yetkisiz ID ({id_tag}) ile İşlem Başlatma İsteği Alındı! StartTransaction RED
