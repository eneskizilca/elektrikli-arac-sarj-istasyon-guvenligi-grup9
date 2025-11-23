# Elektrikli Araç Şarj İstasyon Güvenliği (Grup 9)

BSG dersi kapsamında yürüttüğümüz projeye ait repodur.

<p align="center">
  <img width="123" height="123" src="https://github.com/user-attachments/assets/8d1d4847-de45-4b7a-9277-758020bf8200" />
</p>

# ⚡ SecVolt: EV Şarj İstasyonu Güvenlik ve Anomali Tespit Sistemi

[![Project Status](https://img.shields.io/badge/Status-Development-orange)]()
[![Focus](https://img.shields.io/badge/Focus-Cyber--Physical%20Security-blue)]()
[![Domain](https://img.shields.io/badge/Domain-Smart%20Grid%20%2F%20EVSE-green)]()

**SecVolt**, Elektrikli Araç (EV) şarj altyapılarını hedef alan siber-fiziksel saldırılara karşı geliştirilen, yapay zeka destekli bir **Karar Destek ve Savunma Mekanizması** projesidir.

Bu depo (repository); SecVolt projesinin teknik dokümantasyonunu, mimari tasarımlarını, geliştirilen anomali senaryolarını ve simülasyon kodlarını barındıran merkezi bilgi havuzudur.

---

## 📖 Proje Özeti ve Vizyon

Elektrikli araç ekosisteminin güvenliği, sadece veri gizliliği değil, fiziksel şebeke kararlılığı için de kritik öneme sahiptir. Şarj istasyonları (CP), internet tabanlı yönetim sistemleri (**OCPP**) ile fiziksel donanım (**CAN-bus**) arasında bir köprü görevi görür.

**SecVolt Projesinin Amacı:**
Bu köprü üzerindeki zafiyetleri (Man-in-the-Middle, Firmware Manipülasyonu vb.) analiz etmek ve **"Siber-Fiziksel Çöküş"** senaryolarına karşı proaktif, yapay zeka tabanlı bir savunma sistemi geliştirmektir.

---

## 📄 **Detaylı İnceleme:**
[Proje Gelişim Fazları ve Detaylı Gelişim Dokümanı - Toplantılarımız](https://docs.google.com/document/d/1XRKAa9kGEwEvim2WuKtIdeapeiyGzDRf_tdyihQIFXw/edit?usp=sharing)

[Proje Tanıtım Websitemiz (Github.io ile)](https://eneskizilca.github.io/secvolt.github.io/)

---

## 📂 Depo Yapısı ve İçerik

Bu depo, 10 kişilik proje ekibimizin geliştirdiği farklı modülleri ve senaryoları bir araya getirir:

```text
SecVolt-Repo/
├── 📁 Docs/                    # Proje raporları, C4 diyagramları ve teknik dokümanlar
├── 📁 Dashboard/               # (Planlanan) Web tabanlı yönetim paneli frontend kodları
├── 📁 Simulasyon_Senaryolari/  # EKİP ÇALIŞMA ALANI
│   ├── _SABLONLAR/             # Temel (Temiz) Simülasyon Kodları (Server/Client)
│   ├── [Ad_Soyad]/             # Her üyenin geliştirdiği spesifik saldırı senaryosu
│   │   ├── client.py           # (Örn: Enerji Hırsızlığı yapan modifiye istemci)
│   │   └── server.py           # (Örn: Saldırı altındaki sunucu simülasyonu)
│   └── ...
└── README.md                   # Proje Genel Bilgileri
```

🎯 Proje Hedefleri (SMART)
Projemiz, aşağıdaki 6 temel hedefi gerçekleştirmek üzere kurgulanmıştır:

🔍 Anomali Tespiti: Şarj ağındaki anormal davranışları ≥%95 doğrulukla tespit eden bir AI modeli geliştirmek.

🛡️ Güvenlik Skoru: İstasyonlar için 50 maddelik siber/fiziksel güvenlik kontrol listesi (Checklist) oluşturmak.

⚡ Enerji Hırsızlığı Tespiti: MeterValues manipülasyonlarını ve sahte tüketim verilerini ≥%90 hassasiyetle yakalamak.

⏱️ Gerçek Zamanlı Müdahale: Bir tehdit algılandığında sistemi <30 saniye içinde otomatik korumaya almak (RemoteStopTransaction).

📜 Standartlara Uygunluk: Geliştirilen mimarinin ISO 15118 ve OCPP 1.6/2.0 güvenlik standartlarıyla uyumlu olması.

🏭 Pilot Uygulama: Geliştirilen savunma sistemini, endüstriyel standartlardaki CSMS yazılımlarına (örn: SteVe) karşı test etmek.

## 🏗️ Teknik Mimari ve Tehdit Modeli

Proje,Siber-Fiziksel Sistem (CPS) güvenliği üzerine kuruludur.

<img width="761" height="538" alt="Ekran Resmi 2025-11-23 20 58 49" src="https://github.com/user-attachments/assets/a140729d-9faf-4c43-a9b0-31cad7fb6e3f" />

Saldırı Yüzeyi: Şarj İstasyonu (CP) ve Merkezi Sistem (CSMS) arasındaki Ağ Hattı + İstasyon içi Donanım Hattı.

Simülasyon Ortamı:

Ağ: websockets ve ocpp kütüphaneleri ile TCP/IP haberleşmesi.

Donanım: Linux vcan0 (Virtual CAN) arayüzü ile araç/istasyon içi donanım haberleşmesi.

Savunma Katmanı:

Kural Motoru: Bilinen saldırı imzalarını (Signature-based) yakalar.

AI Modeli: Bilinmeyen davranışsal sapmaları (Behavioral Analysis) yakalar.

## ⚠️ Yasal Uyarı

Bu repo ve içerdiği kodlar, yalnızca akademik araştırma ve eğitim amaçlıdır. Geliştirilen saldırı senaryoları, yalnızca izole edilmiş sanal ortamlarda (Sandbox) test edilmek üzere tasarlanmıştır.





