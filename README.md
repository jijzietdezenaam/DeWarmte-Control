# DeWarmte Control 3.4 – prijsslim verwarmen, rustige regeling, service-instellingen en dashboard

Eén integration (geen add-on) die via MQTT met je DR164 praat, alle pompen en meters uitleest
en **zelf regelt**: aanvoersetpoint, aan/uit en vermogensmodus van de SunRain, en het tapwatersetpoint van Pomp T.

## Installatie via HACS (aanbevolen)
1. HACS → ⋮ → **Custom repositories** → URL van deze repository, type **Integration** → Toevoegen.
2. Zoek **DeWarmte Control** in HACS → Downloaden → herstart Home Assistant.
3. Updates verschijnen daarna vanzelf onder Instellingen → Updates.

## Handmatige installatie
1. Maak een back-up van Home Assistant.
2. **Stop de add-on "DeWarmte Communication Core"** en zet automatisch starten uit (één Modbus-master tegelijk).
   Zet de oude integratie `dewarmte_control_center` uit, en ook je eigen tapwater-prijsautomation
   (anders vechten twee regelingen om hetzelfde setpoint).
3. Staat versie 3.0 al geïnstalleerd: overschrijf de map. Anders: kopieer `custom_components/dewarmte` naar
   `/config/custom_components/`. Herstart Home Assistant.
4. Integratie toevoegen → **DeWarmte Control** → de MQTT-topics van je DR164 (`<MAC>/up` en `<MAC>/down`),
   kamers (Versatile Thermostats), buitensensor, prijssensor en eventueel je notify-dienst
   (bijv. `mobile_app_mijn_telefoon`, staat onder Ontwikkelhulpmiddelen → Acties → zoek "notify.").
5. De regeling start meteen. Druk op **Uurrapport nu versturen** om de melding te testen.

## Wat er geschreven wordt (en verder niets)
| Register | Wat | Grenzen | Max. |
|---|---|---|---|
| SunRain 769 | aanvoersetpoint | 20–50 °C (en je min/max) | 1× per 15 min, 4/uur, 40/dag |
| SunRain 773 | aan/uit | 0/1, min. 30 min aan / 10 min uit | 4/uur, 12/dag |
| SunRain 775 | Stil/Normaal/Boost | 0–2 | 1× per 20 min, 3/uur, 16/dag |
| Pomp T 6 | tapwatersetpoint | 40–70 °C | 1× per 30 min, 2/uur, 12/dag |

Totaal maximaal 10 per uur en 80 per dag. Beveiligingen, ontdooien, compressorlimieten enz. kunnen niet
worden geschreven: de bus weigert elk ander register, ook als de code een fout zou bevatten.
Elke schrijfactie wordt bevestigd met het Modbus-echoantwoord en daarna direct teruggelezen.
**Geen enkele wijziging** bij: storing, ontdooien of als de SunRain-data niet vers is.
Na 3 mislukte schrijfacties achter elkaar zet de regeling zichzelf uit en krijg je een melding.

**Noodstop:** zet de schakelaar **Regeling actief** uit. Dan wordt alleen nog gelezen; de pomp blijft
staan op de laatste waarden. Deze keuze blijft bewaard na een herstart.

## Regelgedrag
- Aanvoer = 31 − 0,5 × buiten + 2 K per K kamertekort (max. +6) + geleerde offset (±4), begrensd 25–45 °C.
- **Basislast (nieuw):** in het stookseizoen onder 10 °C buiten blijft de unit aan op de stooklijn, ook
  zonder TRV-vraag, omdat de Jaga's in hal, toilet en bijkeuken geen TRV hebben. Instelbaar in de opties.
- Boven 10 °C: aan bij warmtevraag (klep ≥ 10 % of tekort ≥ 0,4 K), uit na 45 min zonder vraag.
- Geen verwarming boven 18 °C buiten (hervat onder 16 °C).
- Vermogensmodus: boven *Altijd Stil boven* (standaard 3 °C) altijd Stil; onder *Koud* (standaard 2 °C) minimaal Normaal en Boost bij aanhoudend tekort (instelbaar: *Bij kou minimaal Normaal* = 0 geeft het oude gedrag: start Stil, opschalen bij tekort).
- Pomp T: als die draait op koud bronwater (< 18 °C) gaat de pomp AO aan met minimaal 30 °C aanvoer.
- Tapwater: minimaal 45 °C, daarboven op prijs (< 0,20 → 60, < 0,26 → 55, < 0,30 → 50, anders 45, negatief → 70).

## Uurrapport
Elk heel uur (:00) een melding in Home Assistant (vervangt de vorige) en, als ingesteld, op je telefoon:
wat er is gewijzigd en waarom, gemiddelde buiten- en aanvoertemperatuur, looptijd van de compressor, verdeling
over de modi, kWh en COP van het afgelopen uur, tapwater, blokkades en uitgestelde wijzigingen.
De sensoren **Laatste actie** (laatste 30 acties als attribuut) en **Laatste uurrapport** tonen hetzelfde.

## Entiteiten
- Apparaat **DeWarmte**: ca. 45 hoofdentiteiten (metingen, beslissingen, schakelaar, knop).
- Apparaten **SunRain**, **Pomp T**, **kWh-meters** en **warmtemeters**: alle ca. 560 registers en statusbits uit de
  fabrikanttabellen (onder Diagnostiek, met registernummer in de naam). Ze zijn alleen-lezen.
  Wil je je database klein houden, sluit ze dan uit van de recorder of schakel ongebruikte uit.

## Controleer de eerste dag
- Of het **debiet** van de warmtemeters (factor 0,001667) klopt met het display van de meter.
- Of register 769 het aanvoer- of retoursetpoint is (sensor *Regelmethode unit (372)*); stel zo nodig
  de optie "Setpoint van de unit regelt op" in.
- Het uurrapport en het logboek: `Schrijfactie …` regels in het HA-log, CSV in `/config/dewarmte/`.

## Tests
`python3 tests/test_core.py`, `python3 tests/test_ha_glue.py` en `python3 tests/test_rooms.py` (geen Home Assistant nodig).

## Nieuw in 3.2
### Service-instellingen
Alle 198 schrijfbare registers van SunRain en Pomp T staan als instelling (number) bij de apparaten
*SunRain monoblock* en *Pomp T*, met de grenzen uit de fabrikanttabel. Wijzigen kan alleen als de schakelaar
**Servicemodus** aan staat; die gaat na 30 minuten vanzelf uit (na een wijziging blijft hij minimaal 10 min open).
Elke wijziging staat in het uurrapport en in `/config/dewarmte/servicelog.csv` met de oude waarde.
Niet schrijfbaar, ook niet in servicemodus: de commandobits 816/817 (ontdooien forceren, fabrieksinstellingen,
koudemiddel terugwinnen, compressor forceren) en de bytes van 780/781.

### Handmatige desinfectie
Knop **Desinfectie starten**: Pomp T gaat naar de desinfectietemperatuur (register 10, 60–70 °C) met alleen de
warmtepomp, houdt die vast zolang register 11 aangeeft (10–90 min) en zet daarna het prijs-setpoint terug.
Wordt de temperatuur binnen 4 uur niet gehaald, dan stopt hij en meldt de hoogste bereikte temperatuur.
**Desinfectie stoppen** breekt af. Tijdens de desinfectie pauzeert de prijsregeling van het tapwater.

### Dashboard
Bij elke start schrijft de integratie:
- `/config/www/dewarmte/` – het hydraulische schema en de stromingslagen (bewegen als er circulatie is);
- `/config/dewarmte/dashboard.yaml` – het dashboard met jouw echte entity-id's.

Benodigd via HACS → Frontend: **Mushroom** en **ApexCharts Card**. Voeg toe aan `configuration.yaml`:
```yaml
lovelace:
  dashboards:
    dewarmte-dashboard:
      mode: yaml
      title: DeWarmte
      icon: mdi:heat-pump
      show_in_sidebar: true
      filename: dewarmte/dashboard.yaml
```
Tabbladen: Overzicht (schema met live waarden), Grafieken, Kamers, Tapwater (met desinfectie), Service, Diagnose.

## Nieuw in 3.3: rustige regeling
Gewenste aanvoer = stooklijn + preset-correctie + klepbijsturing + geleerde offset.
- **Klepbijsturing** (vervangt de directe kamerboost): elke 30 min kijkt de regeling naar de gemiddelde stand van
  de meest open klep. ≥ 90 % én echt tekort (≥ 0,3 K) → +0,5 °C; ≤ 60 % en geen tekort → −0,5 °C; daartussen gelijk.
  Zo zakt de aanvoer tot de kamer die het meest vraagt zijn klep ver open heeft (beste COP). Grenzen −3…+4 °C.
- **Preset-correctie**: staat een kamerdoel boven het gebruikelijke doel (meest voorkomend in 24 u), bijv. door
  goedkope stroom, dan gaat de aanvoer meteen 0,5 °C per graad mee. Na elke doelwijziging wacht de klepbijsturing 60 min.
- **Kamers met TRV-sensor** (optie *Kamers die meten met de sensor in de TRV*): hun tekort wordt 30 min gemiddeld en
  telt half mee, omdat die sensor op de convector zit en snel op-en-neer gaat. Selecteer hier slaapkamer groot en klein.
- **Geleerde offset**: bij de update teruggezet naar 0 (stond vast op +4). Nu leert hij hooguit 0,5 °C per 6 uur,
  omhoog én omlaag even makkelijk, maximaal ±2 °C.
- **Setpoint-hysterese**: het setpoint van de unit verandert pas bij 0,75 °C verschil (minder heen-en-weer).
Nieuwe sensoren: *Klepbijsturing* (met reden) en *Preset-correctie*.

## Nieuw in 3.4: prijsslim verwarmen
Schakelaar **Prijsslim verwarmen** (standaard aan). De integratie haalt elk half uur de prijzen van vandaag en
morgen op via een dienst (standaard `tibber.get_prices`, instelbaar) en stuurt dan zelf:

- **Kamerdoelen (Versatile Thermostat)**: normaal doel = comfort-preset overdag, eco-preset 's nachts
  (23:00–05:00, weekend tot 07:00), de *away*-varianten als niemand thuis is (optie *Aanwezigheid*).
  Daarop een prijs-offset: is het nu goedkoper dan gemiddeld in het venster rond nu, dan voorverwarmen
  (max. +1,5 °C); is het duurder, dan iets laten zakken (max. −1 °C). Stappen van 0,5 °C, minimaal 45 min
  vasthouden. Een negatieve prijs geeft meteen maximaal voorverwarmen.
- **Venster leren**: per kamer meet de integratie hoe snel hij afkoelt met dichte klep; daaruit volgt hoe lang
  het huis een graad extra vasthoudt (2–6 uur). Hoe trager het afkoelt, hoe verder vooruit hij plant.
- **Aanvoer gaat direct mee** met de prijs-offset (0,5 °C aanvoer per °C kamerdoel).
- **Boiler**: in de goedkoopste 10 % van het etmaal naar 60 °C, in de goedkoopste 25 % naar 55 °C, anders 45 °C;
  bij negatieve prijs 70 °C.
- **Handmatig ingrijpen** (zelf een kamer hoger/lager zetten) wordt gerespecteerd tot het volgende blok
  (dag/nacht), maximaal 3 uur.

Zet de automation *Nachtverlaging thermostaat* uit zodra je 3.4 gebruikt: de integratie doet dit nu zelf.
Sensor **Prijs-offset kamers** toont de reden, het geleerde venster, de afkoelsnelheid per kamer en de
planning voor de komende uren; het tabblad Grafieken heeft een prijs/offset-grafiek en een planningstabel.

## Nieuw in 3.4.1: warme periodes per kamer
Optie **Warme periodes per kamer** (Configureren), één regel per kamer:
```
climate.badkamer | 21 | ma-vr 05:30-07:30, 20:00-22:30 | za-zo 08:00-10:00, 20:00-22:30
```
Tijdens zo'n periode is het normale doel van die kamer de opgegeven temperatuur (hier 21 °C); de prijs-offset
geldt ook dan. De periode begint 30 minuten eerder zodat het op tijd warm is. Alleen als er iemand thuis is.
Dagen: ma, di, wo, do, vr, za, zo, reeksen als `ma-vr`, of `dagelijks`.

## Nieuw in 3.4.2: automatische legionella-cyclus
Is het tapwater 7 dagen (instelbaar, 0 = uit) niet boven 60 °C geweest, dan start de integratie zelf een
desinfectie (alleen warmtepomp, zoals de knop) op het goedkoopste moment van het komende etmaal, of uiterlijk
een dag later. Hooguit één automatische poging per 24 uur; je krijgt er een melding van.

## Nieuw in 3.5: meldingen, weekrapport, tapmomenten en pendelbewaking
**Directe meldingen** (push naar de notify-dienst, op iPhone als *time-sensitive*, en een melding in HA):
- geen verse Modbus-data van de SunRain gedurende 10 minuten (en een bericht als het hersteld is);
- storing pomp AO (foutcode/subcode) of Pomp T (foutregisters 50, 51, 62), na 2 minuten;
- een kamer blijft 2 uur lang meer dan 1 K onder het doel. Na een verhoging van het doel begint die
  2 uur opnieuw, en kamers met open raam of die uit staan tellen niet. Kamers uitsluiten kan in de opties
  (*Kamers zonder melding 'blijft te koud'*; standaard het toilet).
Dezelfde melding komt pas opnieuw nadat de situatie 30 minuten normaal is geweest.

**Weekrapport** elke zondag om 19:00 (push + tabblad *Week*): per kamer de gemiddelde afwijking, % van de tijd
binnen ±0,5 K en uren > 1 K te koud; energie en COP van de week; wat de warmtepompen hebben gekost en het verschil
met stoken tegen de weekgemiddelde prijs; compressorstarts; herkende tapmomenten; legionella. De knop
*Weekrapport nu versturen* stuurt een tussenstand (de week loopt door).

**Tapwater op gebruik**: snelle dalingen in de boiler (≥ 3 K onderin of ≥ 2 K bovenin binnen 20 minuten) worden
herkend als tapmoment. Per werkdag/weekend en per half uur onthoudt de integratie hoe vaak er getapt wordt
(laatste 28 dagen, recente dagen tellen zwaarder). Een tijdvak op ≥ 40 % van de dagen geldt als tapmoment. Is de
boiler dan naar verwachting kouder dan *Tapwater boven minimaal op geleerde tapmomenten* (standaard 50 °C), dan
warmt Pomp T vooraf op, in het goedkoopste stuk van de 6 uur ervoor. De opwarmsnelheid van Pomp T wordt geleerd.
Sensor *Tapwaterplanning* laat zien wat er geleerd is en wat er gepland staat. Op 0 zetten = uit.

**Pendelbewaking**: sensoren *Compressorstarts laatste uur* en *vandaag* (een stop korter dan 60 s telt niet),
grafiek per uur op het tabblad *Week* en een samenvatting in het weekrapport (waarschuwing bij ≥ 7 uur met
meer dan 3 starts in een week).

## Nieuw in 3.5.1: oude MQTT-discovery automatisch opruimen
Bij elke start luistert de integratie 15 seconden naar `homeassistant/#` en wist ze retained discovery-berichten
van de oude DeWarmte-app (unique_id `dewarmte_…` met availability onder `dewarmte/`), plus hun state-topics.
Andere MQTT-apparaten worden niet aangeraakt. Daarmee verdwijnen de honderden foutmeldingen
"Entity category 'config' is not supported" uit het logboek.

## Nieuw in 3.5.2: prijsslim kijkt alleen vooruit
De prijs-offset vergeleek het huidige uur met het gemiddelde van W uur terug én vooruit. Een duur moment ná een
dure ochtend leek daardoor "gemiddeld", terwijl er over een paar uur een goedkoop dal komt. Nu wordt het huidige
uur vergeleken met het goedkoopste en het duurste uurblok dat binnen W + 1 uur (3–6 u) begint:
`offset = gain × ((duurst − nu) + (goedkoopst − nu)) / (2 × spreiding)`, begrensd op +1,5 / −1 K.
Komt er straks een dal: nu laten zakken. Komt er straks een piek: nu voorverwarmen.

## Nieuw in 3.5.3: watersysteem ontluchten vanuit HA
Knoppen **Watersysteem ontluchten** en **Ontluchten stoppen** (tabblad Service). Zet SunRain-register 816 bit 4
("System Emptying mode", 排空 = ontluchten) via lezen-aanpassen-schrijven: het register wordt vers gelezen en alleen
bit 4 verandert; alle andere bits (o.a. fabrieksinstellingen, koudemiddel terugwinnen) zijn hard geblokkeerd.
Alleen in servicemodus. Tijdens het ontluchten schrijft de regeling niets naar pomp AO. Bevestigt de SunRain de bit
niet binnen 2 minuten, of duurt het langer dan 30 minuten, dan zet de integratie de bit zelf terug. Zet de SunRain
de bit zelf uit, dan is het programma klaar. Ook: een kamer die uit staat telt na aanzetten niet meer als
handmatige wijziging.

## Nieuw in 3.5.4: warmtemeter-fout ≠ geen debiet
Meldt een warmtemeter een foutcode (bijv. 128: geen ultrasoon meetsignaal, meestal lucht), dan zijn debiet en warmte
"onbekend" in plaats van 0, en telt de COP niet mee. *Circulatie pomp AO* volgt nu de pomprelais-bit van de SunRain
(reg 25 bit 6) in plaats van het debiet. Duurt de meterfout langer dan 10 minuten, dan komt er een melding.

## Nieuw in 3.5.5: bij kou gewoon Normaal, geen setpoint-dip na ontdooien
- Onder de koud-grens (*Koud: Normaal/opschalen onder*, standaard 2 °C, hysterese tot *Altijd Stil boven*) draait de
  unit minimaal **Normaal**. Voorheen begon hij Stil en schaalde pas na 10 min tekort op, en zakte bij een overshoot
  na het ontdooien weer terug naar Stil: elke ~20 min wisselen. Uit te zetten met *Bij kou minimaal Normaal* = 0.
- Na een herstart in de hysteresezone kiest de regeling op het midden van de twee grenzen in plaats van altijd "warm".
- Valt de buitentemperatuur even weg (rond het ontdooien gaf de SunRain soms geen waarde), dan houdt de regeling de
  laatste geldige waarde tot 2 uur vast. Voorheen rekende de stooklijn dan met 5 °C en zakte het aanvoersetpoint 2 K.

## Nieuw in 3.5.6: absoluut maximum per kamer
- Optie *Kamers met een absoluut maximum* (standaard: alle kamers met "slaapkamer" in de naam) en
  *Absoluut maximum kamerdoel* (standaard 20 °C). Prijsslim voorverwarmen en warme periodes gaan daar nooit
  boven; een handmatig hoger doel wordt ook teruggezet. Lager zetten blijft gewoon gerespecteerd.
- Labels voor *Koud: Normaal/opschalen onder* en *Bij kou minimaal Normaal* toegevoegd aan de vertalingen.

## Nieuw in 3.5.7: vakantiemodus
- Schakelaar **Vakantiemodus** en datum/tijd **Vakantie terug op**.
- Aan: alle kamers naar *Vakantiemodus: kamerdoel* (standaard 17 °C, ook over handmatige wijzigingen heen) en de
  boiler vast op *Vakantiemodus: tapwater* (standaard 45 °C, geen prijsslim laden of tapmomenten).
- Met een terugkomstmoment: *Vakantiemodus: zoveel uur vóór terugkomst opwarmen* (standaard 6 uur) ervoor regelt
  alles weer normaal, op het terugkomstmoment gaat de modus vanzelf uit (met melding).
- De automatische legionella-desinfectie (elke 7 dagen) blijft gewoon doorlopen.
- Basislast (hal/toilet/bijkeuken zonder TRV) draait tijdens vakantie alleen onder *Vakantiemodus: basislast alleen onder* (standaard 3 °C buiten, 3.5.9).

## Nieuw in 3.5.10: uitzetten altijd toegestaan
- De schrijfbeveiliging telde ook het *uitzetten* van de unit mee voor het aan/uit-budget (12 per 24 uur). Was dat op,
  dan bleef de unit draaien zonder warmtevraag. Uitzetten is altijd veilig en telt nu niet meer mee; alleen starts
  zijn begrensd (plus de bestaande minimale loop- en stilstandtijd).

## Nieuw in 3.6: zelflerende kamerregeling (vervangt Versatile Thermostat)

DeWarmte kan de TRV-kleppen (Sonoff TRVZB), radiatorfans en aanvoer nu zelf regelen. Per kamer
leert het een warmtemodel met recursieve kleinste kwadraten:

    dT/dt = (a + af·fan) · klep · (T_aanvoer − T_kamer) · circulatie − b · (T_kamer − T_buiten) + d

- **Klep per kamer:** precies zoveel open als nodig om het doel vast te houden, plus een P- en een
  trage I-correctie. Onder 10 % gaat de klep dicht (geen druppelen en pendelen). Er wordt alleen
  geschreven bij ≥ 10 % verschil en hooguit 1× per 10 min. Dat spaart de batterijen.
  Uitzonderingen zijn raam open, te warm (+0,5 K), uit en vorst. Klepstand X wordt geschreven als
  `opening_degree = X` en `closing_degree = 100 − X`.
- **Radiatorfans (optioneel):** 20–50 % bij circulatie en een klep ≥ 30 %. Het effect wordt mee geleerd (`af`).
- **Aanvoer:** de laagste aanvoer waarbij de moeilijkste kamer zijn doel haalt met de klep op 85 %.
  De aanvoer blijft begrensd op stooklijn −6 / +3 K. Het model neemt de stooklijn geleidelijk over,
  naarmate het meer heeft geleerd (± 12 uur aan metingen met warmteafgifte). Klepbijsturing en
  offset blijven daarbovenop werken.
- **Raam open:** 0,5 K daling binnen 10 min → klep 30 min dicht.
- **Kamerdoelen:** dag/nacht per kamer, afwezig −1 K, prijsslim, warme periodes, maximum, vakantiemodus.
  Een handmatig doel (op de thermostaat) geldt tot het volgende dag/nacht-blok, maximaal 3 uur.
  Preset `schema` zet het weer terug.
- **Entiteiten:**
  - `climate.dewarmte_<kamer>` per kamer, met de attributen `valve_open_percent`, `klep_reden`,
    `fan_percentage`, `raam_open`, `model` (geleerde waarden) en meer.
  - Schakelaar **Kamerregeling**: uit = de TRV's krijgen hun eigen regeling terug
    (opening 100 / closing 0, setpoint = kamerdoel). Dat gebeurt ook als *Regeling actief* uitgaat.
- **Ook als de kamerregeling uit staat**, leert het model al mee met de kleppen die VTherm/de TRV zelf stuurt.

Configuratie: optie *Zelflerende kamerregeling*, één regel per kamer:

    climate.woonkamer_2 | Woonkamer | sensor.woonkamer_temp | climate.woonkamer_trv | number.trv_valve_opening_degree | number.trv_valve_closing_degree | 20,5 | 19 | fan.jaga

Het kamer-id (eerste kolom) is ook de sleutel voor warme periodes, maximum en TRV-sensorkamers. Na het
verwijderen van VTherm kan de DeWarmte-thermostaat dat entity-id overnemen.

## Nieuw in 3.6.1
- TRV- en fan-opdrachten lopen op de achtergrond, met maximaal 30 s per opdracht. Een TRV die niet
  antwoordt, houdt de warmtepompregeling niet meer op.
- Thermostaten gebruiken de nieuwe `native_*`-temperatuureigenschappen (HA 2026.11).

## Nieuw in 3.6.2
- Herstel: 3.6.1 startte niet (achtergrondtaak verkeerd aangemaakt). Een fout in de kamerregeling
  kan de warmtepompregeling nu nooit meer stoppen.

## Nieuw in 3.6.3: kordater bijsturen
- Te koud (≥ 0,8 K): klep meteen volledig open. Kleinere tekorten worden sterker bijgestuurd
  (P 2,0 K/u per K, I 0,3 per K·uur).
- De regeling gebruikt standaardwaarden zolang er weinig geleerd is, en schuift pas mee naar de
  geleerde waarden naarmate er meer metingen zijn. Eén vreemde meting kan de kleppen niet meer laten dichtknijpen.
- Geen raamdetectie in kamers die met de TRV-sensor meten (die sensor koelt na het dichtgaan van de
  klep snel af). Elders: ≥ 0,8 K daling binnen 15 min.
- Klep max. 1× per 15 min wijzigen, behalve volledig dicht (te warm, raam, uit) of open (te koud).
- Bij overname van een klep mag DeWarmte direct bijsturen.

## Nieuw in 3.6.4: uurrapport alleen bij problemen
Op de telefoon alleen nog een kort bericht als er iets mis is:
- regeling uit;
- een kamer het hele uur > 1 °C te koud;
- meer dan 3 compressorstarts per uur;
- een mislukte opdracht (Modbus, TRV, fan) of een TRV die zijn klepstand niet bevestigt;
- COP < 2,5 (bij ≥ 0,2 kWh stroom);
- tapwater onder het minimum.

Het volledige rapport blijft in de HA-meldingen en in de sensor *Laatste uurrapport* staan. De knop
*Uurrapport nu versturen* stuurt het altijd.

## Nieuw in 3.7.0: zuiniger bij kou
- **Boost niet meer door voorverwarmen:** voorverwarmen op goedkope stroom leidt nooit meer tot
  opschalen naar Boost. Het opschalen kijkt alleen naar het aanvoertekort zonder de prijsverhoging.
- **Aanvoer op het gewone doel:** de aanvoer van het kamermodel wordt gekozen op het gewone
  kamerdoel, zonder prijsverhoging. Voorverwarmen gaat alleen via de kleine feedforward.
- **Kwaliteitscontrole van het model:** een kamermodel dat slecht voorspelt (voorspelfout boven
  0,5 K/u, bij 1 K/u niet meer) telt minder of niet mee. DeWarmte regelt die kamer dan met
  standaardwaarden en bijsturing.
- **Nieuw model bij een andere sensor:** krijgt een kamer een andere sensor, dan begint het model
  voor die kamer opnieuw.
- **Alleen werkende fans:** radiatorfans tellen alleen mee in de aanvoerberekening als ze echt werken.
