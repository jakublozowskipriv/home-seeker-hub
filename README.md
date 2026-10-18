# Home Seeker Hub

Osobisty asystent do szukania mieszkania w Poznaniu. Co kilka godzin przegląda portale
z ogłoszeniami, ocenia oferty według Twoich preferencji i wysyła najlepsze na Telegram.

## Jak to działa

```
GitHub Actions (co 3 h) ──► scrapery (Otodom, OLX)
                              │  normalizacja, analiza opisu (balkon, ogrzewanie, piętro…)
                              ▼
                       ocena: twarde kryteria + wynik 0–100
                              │  deduplikacja (ta sama oferta na kilku portalach)
                              ▼
                     baza Supabase (Postgres) ──► Telegram: nowe oferty i obniżki cen
```

* **Werdykty**: `match` (spełnia wszystko), `review` (brakuje danych, np. nie wiadomo czy jest
  balkon), `negotiable` (800–840 tys. zł, bez powiadomień), `rejected`.
* **Wynik 0–100** liczony z wag w `config/preferences.default.yaml`: lokalizacja, dojazd,
  piętro, rok budowy, cena, winda, metraż, pokoje.
* **Dojazd** jest na razie *szacowany* z odległości (tramwaj + pieszo). Dokładne czasy
  z rozkładu ZTM Poznań dojdą w kolejnym etapie.
* Pierwsze uruchomienie wysyła jedno podsumowanie z 10 najlepszymi ofertami; potem tylko
  nowości i obniżki. Gdy naraz pojawi się więcej niż 15 nowych ofert, przychodzi jedno
  podsumowanie zamiast lawiny wiadomości. Powiadomienia dotyczą tylko ofert z ceną
  i sprawdzonymi szczegółami.
* Inwestycje deweloperskie na Otodom (jeden kafelek = wiele mieszkań) są rozbijane na
  pojedyncze mieszkania, z terminem oddania z inwestycji.

## Konfiguracja (jednorazowo, wszystko za darmo)

### 1. Baza danych – Supabase

1. Załóż konto na <https://supabase.com> i utwórz projekt (region: Frankfurt/Central EU).
   Zapisz hasło do bazy.
2. W projekcie kliknij **Connect** → zakładka **Connection string** → wybierz
   **Session pooler** i skopiuj adres (`postgresql://postgres.xxxx:[YOUR-PASSWORD]@…pooler.supabase.com:5432/postgres`).
   Wstaw w nim swoje hasło.
3. Tabele utworzą się same przy pierwszym uruchomieniu.

> Darmowy projekt Supabase jest wstrzymywany po tygodniu bez aktywności – regularny
> scraping utrzymuje go aktywnym.

### 2. Bot Telegram

1. W Telegramie napisz do **@BotFather** → `/newbot` → nadaj nazwę → skopiuj **token**.
2. Otwórz rozmowę ze swoim nowym botem i wyślij mu `/start`.
3. Identyfikator czatu zostanie wykryty i zapisany automatycznie przy pierwszym przebiegu
   (albo ustaw go ręcznie jako `TELEGRAM_CHAT_ID`). Sprawdzić połączenie można workflowem
   **Actions → Telegram test → Run workflow** – wyśle wiadomość testową, a w logach pokaże,
   do którego bota należy token.

### 3. Sekrety w GitHubie

Repozytorium → **Settings → Secrets and variables → Actions → New repository secret**:

| Sekret | Wymagany | Wartość |
|---|---|---|
| `DATABASE_URL` | tak | adres z Supabase (punkt 1) |
| `TELEGRAM_BOT_TOKEN` | tak | token od BotFathera |
| `TELEGRAM_CHAT_ID` | nie | ustaw, by tylko Twój czat dostawał powiadomienia |
| `HOMESEEKER_PREFERENCES` | nie | cały YAML preferencji, jeśli nie chcesz ich trzymać w publicznym repo |

### 4. Uruchomienie

Workflow **Scrape listings** uruchamia się sam co 3 godziny (harmonogram działa z gałęzi
domyślnej `main`). Można go też odpalić ręcznie: **Actions → Scrape listings → Run workflow**.
Raport z każdego przebiegu jest widoczny w podsumowaniu joba.

**Pierwsze indeksowanie**: w Poznaniu jest ok. 2000 pasujących wstępnie ofert, a każda
wymaga pobrania strony szczegółów. Najszybciej: **Run workflow** z `max_details` = `2000`
(trwa ok. godziny). Bez tego zaindeksuje się samo w ciągu ok. doby (150 ofert na przebieg).
Przez ten czas bot milczy, a na koniec wysyła podsumowanie z 10 najlepszymi ofertami.

Bez `DATABASE_URL` workflow działa w trybie podglądu (`--dry-run`): nic nie zapisuje ani nie
wysyła, tylko pokazuje raport.

## Aplikacja webowa (iPhone / każdy telefon)

Strona na GitHub Pages: `https://<twoj-login>.github.io/home-seeker-hub/`. Lista ofert
z filtrami, szczegóły ze zdjęciami, mapą i historią ceny, statusy (interesujące,
oglądanie, …), 👍/👎 i komentarze, mapa wszystkich ofert, edycja preferencji i lista osób
z dostępem. Na iPhonie: Safari → Udostępnij → **Do ekranu początkowego**.

Dostęp mają tylko osoby z listy (zakładka **Dostęp**) – pilnują tego reguły bezpieczeństwa
(RLS) w bazie, więc sam link nic nie daje. Ty (właściciel) zmieniasz preferencje,
statusy i listę osób; pozostali przeglądają, reagują i komentują.

### Konfiguracja (jednorazowo)

1. **GitHub → Settings → Pages → Source: GitHub Actions.**
2. **Supabase → Project Settings → API**: skopiuj *Project URL* i klucz *anon* /
   *publishable*. W GitHubie **Settings → Secrets and variables → Actions → zakładka
   Variables** dodaj `SUPABASE_URL` i `SUPABASE_ANON_KEY` (to wartości publiczne –
   zmienne, nie sekrety).
3. **Sekret `OWNER_EMAIL`** – Twój e-mail; przy najbliższym przebiegu scrapera staniesz się
   właścicielem aplikacji.
4. **Supabase → Authentication → URL Configuration → Site URL**: adres strony z GitHub Pages.
5. **Własny SMTP** (wymagany, żeby edytować szablon maila i żeby kody docierały do innych
   osób – wbudowana poczta Supabase wysyła tylko do członków zespołu projektu):
   **Authentication → Emails → Set up SMTP** – np. Gmail: host `smtp.gmail.com`, port 465,
   login = Twój Gmail, hasło = [hasło aplikacji](https://myaccount.google.com/apppasswords).
6. **Szablony „Magic link or OTP” i „Confirm signup”** (zakładka Source; pierwsze
   logowanie nowej osoby używa tego drugiego): dopisz
   `<p>Twój kod logowania: <strong>{{ .Token }}</strong></p>`. Na iPhonie logujemy się
   kodem, bo link z maila otworzyłby się w Safari, a nie w aplikacji z ekranu początkowego.

Po zmianach w `web/` strona wdraża się sama (workflow **Deploy web app**). Lokalnie:
`cd web && npm install && npm run dev` – bez zmiennych Supabase działa tryb demo
z przykładowymi danymi.

## Wydarzenia i kalendarz

* **Dni otwarte** z ogłoszeń Otodom (data z wyników, godziny ze strony oferty) – tylko dla
  ofert, które nie zostały odrzucone.
* **Targi mieszkaniowe w Poznaniu** ze strony organizatora (targimieszkan.pl).
* **Twoje oglądania** – status „Oglądanie” z terminem w aplikacji.
* Nowe dni otwarte i targi przychodzą na Telegram; w aplikacji zakładka **Wydarzenia**
  z przyciskami „Dodaj do kalendarza” (Apple / Google) i możliwością dopisania własnych.

**Subskrypcja kalendarza** (aktualizuje się sama, co przebieg): dodaj sekret
`SUPABASE_SERVICE_KEY` – Supabase → Project Settings → API Keys → **Secret key**
(`sb_secret_…`, albo legacy `service_role`). To klucz z pełnymi uprawnieniami: tylko jako
**sekret** GitHuba, nigdy jako zmienna ani w kodzie. Scraper publikuje plik `.ics` w
publicznym buckecie Storage pod losową, trudną do zgadnięcia nazwą; link zobaczysz
w aplikacji (Wydarzenia → Subskrypcja kalendarza) i dodasz go w kalendarzu iPhone'a lub
Google.

## Preferencje

Domyślne preferencje są w [`config/preferences.default.yaml`](config/preferences.default.yaml).
Kolejność ładowania: zapis w bazie (edycja w aplikacji – wkrótce) → sekret
`HOMESEEKER_PREFERENCES` → plik z `HOMESEEKER_PREFERENCES_FILE` → plik domyślny.

## Lokalnie

```bash
pip install -e ".[dev]"
python -m pytest
homeseeker run --dry-run --max-pages 1      # podgląd bez zapisu
homeseeker probe otodom                     # surowa struktura danych portalu (debug)
DATABASE_URL=sqlite:///local.db homeseeker run
homeseeker telegram-test                    # wiadomość testowa (TELEGRAM_BOT_TOKEN)
```

## Uwagi

* Portale zabraniają w regulaminach automatycznego pobierania danych. Aplikacja jest do
  użytku prywatnego, robi niewiele zapytań i z przerwami – mimo to portal może je blokować.
* Otodom i OLX odrzucają zapytania od klientów, które nie wyglądają jak przeglądarka,
  dlatego zapytania idą przez `curl_cffi` (odcisk TLS Chrome'a).
* Część ofert (zwłaszcza deweloperskich) ma tylko przybliżoną lokalizację – wtedy dojazd
  nie jest liczony, a ocena opiera się na dzielnicy.
* Workflow **Smoke test** uruchamia scrapery na żywo (bez zapisu) przy zmianach w kodzie,
  żeby szybko wychwycić zmiany w strukturze stron.

## Plan

- [x] Etap 0–1: scrapery Otodom + OLX, ocena i scoring, deduplikacja, historia cen, Telegram
- [x] Etap 2: webapp (PWA na iPhone'a): lista, filtry, mapa, statusy, reakcje, komentarze,
      edycja preferencji, dostęp dla rodziny
- [ ] Etap 3: dokładne dojazdy (GTFS ZTM), okolica (sklepy, przystanki), Geoportal, EKW
- [x] Etap 4: dni otwarte i targi mieszkaniowe, kalendarz `.ics` (Google / Apple)
- [ ] Etap 5: kalkulator kredytu, czerwone flagi (LLM), porównywarka, checklista oglądania
