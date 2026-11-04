# Value Engine — Chrome / web deploy

## Önemli doğruluk notu
Bu sürüm gerçek API bağlantıları kurabilen bir beta altyapısıdır; sıfıra yakın hata veya kâr garantisi vermez. Mevcut gol tahmini sezon gol ortalamalarından türetilen geçici Poisson/Dixon-Coles tabanıdır; xG modeli değildir ve henüz geçmiş maçlarda kalibre edilmemiştir. Kart, korner, İY/MS ve oyuncu marketleri bu sürümde tahmin edilmez. API'den gelmeyen veri uydurulmaz.

## Chrome'da yerel çalıştırma
1. Python 3.11+ kurun.
2. `backend` klasörüne girin.
3. `.env.example` dosyasını `.env` olarak kopyalayın ve API anahtarlarını ekleyin.
4. Terminal:
   ```bash
   pip install -r requirements.txt
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```
5. Chrome'da `http://127.0.0.1:8000` açın. API belgeleri `http://127.0.0.1:8000/docs`.

## Her yerden açılan HTTPS URL
Bu projeyi kendi Render hesabınıza yükleyin:
1. ZIP'i açın ve klasörü GitHub deposuna yükleyin.
2. Render'da **New > Blueprint** seçip depoyu bağlayın. `render.yaml` servisi tanımlar.
3. Render ortam değişkenlerine `APISPORTS_KEY` ve `ODDS_API_KEY` değerlerini girin.
4. Deploy tamamlanınca Render size `https://...onrender.com` adresi verir. Bu adresi Chrome'da açabilirsiniz.

Bu sohbet ortamından sizin adınıza Render/GitHub hesabı açıp deploy yapamam; dolayısıyla henüz gerçek bir herkese açık URL oluşturulmuş değildir.

## Veri sağlayıcıları
- API-Football: https://www.api-football.com/documentation-v3
- The Odds API: https://the-odds-api.com/liveapi/guides/v4/

API anahtarlarını HTML'e veya GitHub'a koymayın. Sadece sunucu ortam değişkenlerinde saklayın. Abonelik, lig kapsamı, kota ve kullanım koşulları sağlayıcıya bağlıdır.

## Otomatik market kapsamı
Bu beta sürüm, The Odds API'den eşleşen etkinlik ve şirket verisi geldiğinde `h2h`, yarım çizgili `totals` ve `btts` marketlerini eşleştirir. Diğer marketler için ayrı veri beslemesi ve bağımsız doğrulanmış model gerekir. Kullanıcının gerçek oynanabilir oranları ayrıca gönderilebilir; karşılaştırma şirketlerinin oranları kullanıcının iddaa oranı gibi gösterilmez.
