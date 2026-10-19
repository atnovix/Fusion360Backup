# Fusion360Backup

Fusion-script dat alle bestanden uit je Fusion-cloud naar een lokale map exporteert, in dezelfde mappenstructuur als het Data Panel. Bedoeld voor als je abonnement afloopt of je een volledige lokale kopie wilt hebben.

Per type bestand:

- Ontwerpen (`.f3d`) worden een Fusion-archief met de volledige tijdlijn, plus een `.step`. Linkt een ontwerp naar andere ontwerpen, dan wordt het archief een `.f3z` met de gelinkte onderdelen erin.
- Tekeningen (`.f2d`) worden een `.pdf`.
- Alle andere bestanden (electronics, libraries, geüploade PDF's en afbeeldingen) worden gedownload zoals ze in de cloud staan.

Het script loopt alle hubs langs waar je toegang toe hebt, dus ook projecten die iemand met je gedeeld heeft.

## Installeren

1. Download deze repo als zip en pak hem uit.
2. Kopieer de map `FusionBackup` naar `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\`, of klik in Fusion bij Scripts and Add-Ins (Shift+S) op het plusje en kies de map `FusionBackup`.
3. Start Fusion opnieuw als het script niet in de lijst staat.

## Gebruik

1. Open bovenin `FusionBackup.py` en pas `EXPORT_ROOT` aan (standaard `D:\Fusion360`).
2. Shift+S, kies FusionBackup en klik Run.
3. Het script telt eerst alle bestanden en vraagt dan of het mag beginnen. Fusion is tijdens de export niet bruikbaar. Met Cancel in het voortgangsvenster stop je.

Bij elke run komen in de exportmap een log en een rapport (`_backup_rapport_<datum>.csv`) met per cloudbestand de status. Zoek in het rapport op `FOUT` om te zien wat niet gelukt is.

Opnieuw starten is veilig. Bestanden die al bestaan worden overgeslagen, dus na een crash of annulering ga je verder waar je was.

## Instellingen

Bovenin het script:

- `EXPORT_F3D`, `EXPORT_STEP`, `EXPORT_PDF`, `DOWNLOAD_OTHER` zetten de exporttypen aan of uit.
- `UNHIDE_ALL_FOR_STEP` neemt verborgen bodies en componenten mee in de STEP. De `.f3d` wordt eerst geëxporteerd en blijft dus zoals hij was.
- `SKIP_PROJECTS` en `SKIP_FOLDERS` zijn lijsten met namen van projecten of mappen die je wilt overslaan.

## Beperkingen

- Alleen de laatste versie van elk bestand wordt geëxporteerd, niet de oudere versies uit de versiegeschiedenis.
- STEP bevat alleen solid bodies. Een ontwerp met alleen sketches of mesh bodies krijgt alleen een `.f3d`; het rapport vermeldt dat.
- Electronics-bestanden worden gedownload in het formaat van Fusion. Wil je ze buiten Fusion gebruiken, exporteer ze dan met de hand naar Eagle `.sch` en `.brd`.
- Fusion staat twee bestanden met dezelfde naam in één map toe, Windows niet. In dat geval krijgt de bestandsnaam een korte code tussen blokhaken, bijvoorbeeld `Beugel [a3f9c1].f3d`.

## Herkomst

Gebaseerd op [aconz2/Fusion360Exporter](https://github.com/aconz2/Fusion360Exporter). Toegevoegd: export van alle hubs, `.f3z` voor ontwerpen met links, download van niet-ontwerp bestanden standaard aan, controle of elk exportbestand echt is aangemaakt, en een CSV-rapport per run.
