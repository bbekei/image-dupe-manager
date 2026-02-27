# DejaView Home Photo Manager — Felhasználói kézikönyv

## Mit csinál ez az alkalmazás?

A DejaView Home Photo Manager megkeresi a duplikált fotókat a megadott mappákban, és megmutatja, pontosan hol léteznek duplikátumok. Az alkalmazás a képek vizuális tartalmát hasonlítja össze — ezért a duplikátumokat akkor is megtalálja, ha a fájlokat átnevezték, más beállításokkal mentették el, vagy módosult a metaadatuk.

A keresési eredményeket meg is oszthatja családtagjaival, hogy megtalálja azokat a fotókat, amelyek több ember könyvtárában is megvannak — a tényleges képek sehová sem töltődnek fel.

---

## Telepítés

### Telepítővel (ajánlott)

1. Töltse le a **DejaView_Setup.exe** fájlt a kiadások oldaláról
2. Futtassa a telepítőt — normál felhasználói fiókkal is működik (nem szükséges rendszergazda)
3. Válassza ki a kívánt nyelvet (angol vagy magyar) a telepítés során
4. Opcionálisan hozzon létre asztali parancsikont
5. Kattintson a **Befejezés** gombra a DejaView elindításához

Az alkalmazás alapértelmezetten a `C:\Users\<felhasználó>\AppData\Local\Programs\DejaView` mappába települ. Az adatbázis és az előnézeti képek külön tárolódnak: `%APPDATA%\DejaView\`.

### Eltávolítás

Használja a **Programok hozzáadása és eltávolítása** funkciót a Windows beállításokban, vagy futtassa az eltávolítót a Start menü csoportjából.

---

## A felület

A főablak három részből áll:

```
┌────────────────────────────────────────────────────────┐
│ Menü: Fájl | Szkennelés | Megosztás | Súgó              │
├──────────────┬─────────────────────────────────────────┤
│ MAPPAPANEL   │  EREDMÉNYPANEL                          │
│              │  [Összes | Csak duplikátumok | Könyvtárak│
│ [+ Hozzáad.] │                              közötti]   │
│ [- Eltávolít]│                                         │
│              │  Az eredmények itt jelennek meg         │
│ ▶ C:\Fotók   │                                         │
│ ▶ Z:\Család  │                                         │
├──────────────┴─────────────────────────────────────────┤
│ [▶ Indítás] [⏸ Szünet] [⏹ Leállítás] ████░░ 47% 230/490│
└────────────────────────────────────────────────────────┘
```

- **Mappapanel** (bal oldal) — a beolvasni kívánt mappák listája. Szkennelés közben minden mappa mellett élő fájlszám jelenik meg (pl. *120 fájl, 47 feldolgozva*)
- **Eredménypanel** (jobb oldal) — a talált fájlok, duplikátum-jelzőkkel
- **Vezérlősáv** (lent) — indítás, szünet, leállítás és az előrehaladás kijelzője

---

## 1. lépés — Mappák hozzáadása

1. Kattintson a **+ Hozzáadás...** gombra a mappapanelen, vagy válassza a **Fájl > Mappa hozzáadása** menüpontot
2. Megnyílik egy mappaböngésző — navigáljon a fotókönyvtárba, majd kattintson az OK gombra
3. A mappa megjelenik a listában

Tetszőleges számú mappát adhat hozzá, különböző meghajtókról vagy hálózati megosztásokról is (pl. `Z:\Közös fotók`). Egy mappa eltávolításához jelölje ki, majd kattintson az **– Eltávolítás** gombra.

---

## 2. lépés — Szkennelés

Kattintson a **▶ Indítás** gombra a vezérlősávban. A szkennelés két szakaszban zajlik:

### 1. szakasz — Feltérképezés
Az alkalmazás végigmegy az összes hozzáadott mappán, és megkeresi az összes fájlt. A fájlok azonnal megjelennek az eredménypanelen — még a duplikátum-ellenőrzés előtt. Az előrehaladás sávon ez jelenik meg: *Fájlok keresése...*

### 2. szakasz — Duplikátum-keresés
Az alkalmazás összehasonlítja a potenciálisan egyező fájlok vizuális tartalmát, több processzormagot használva a gyorsabb feldolgozáshoz. A fájlok a legmélyebb almappáktól felfelé haladva kerülnek feldolgozásra. Ahogy egy-egy mappa feldolgozása befejeződik, a **● DUPLIKÁLT MAPPA** jelölők azonnal frissülnek — a már kész mappákat böngészheti, miközben a szkennelés folytatódik. A **● DUPLIKÁTUM** jelzők rendszeres időközönként frissülnek, ahogy új csoportokat talál az alkalmazás. A mappapanelen élő előrehaladás jelenik meg mappánként (pl. *120 fájl, 47 feldolgozva*), az előrehaladás sávon pedig a feldolgozott fájlok száma és a becsült hátralévő idő látható (pl. *230 / 490 — ~3p 12mp*), amely másodpercenként frissül.

> Amelyik fájl mellett a szkennelés végén nincs jelző, az egyedi — nem találtunk hozzá vizuális másolatot a beolvasott mappákban.

### Szüneteltetés és folytatás
Kattintson a **⏸ Szünet** gombra, amikor csak szeretné. Az aktuális fájl feldolgozása befejeződik, majd a szkennelés megáll. Az állapotjelzőn megjelenik a **SZÜNETELTETVE** felirat. Az alkalmazást be is zárhatja — az előrehaladás el van mentve. Újra megnyitás után kattintson a **▶ Folytatás** gombra a folytatáshoz. A már feldolgozott fájlokat nem ellenőrzi újra.

### Leállítás
A **⏹ Leállítás** gomb megnyomásával véglegesen befejezi a szkennelést. A részleges eredmények megmaradnak.

### Letöltött fotók
Az internetről letöltött vagy e-mailben kapott fotókon Windows biztonsági jelölés ("Mark of the Web") lehet, amely megakadályozhatja az alkalmazást a fájl olvasásában. A DejaView szkennelés közben automatikusan eltávolítja ezt a jelölést a képfájlokról, így azok normálisan feldolgozhatók.

> A szkennelés befejezése után az alkalmazás automatikusan átvált a **Csak duplikátumok** nézetre, ha talált duplikátumokat. Az állapotsávon összefoglaló jelenik meg, például: *Vizsgálat kész: 150 fájl átvizsgálva, 12 duplikátum 5 csoportban.*

---

## 3. lépés — Eredmények áttekintése

A szkennelés után az eredménypanel tetején lévő szűrősávval választhatja ki, mit jelenítsen meg:

| Szűrő | Megjelenített fájlok |
|-------|---------------------|
| **Összes** | Minden fájl a beolvasott mappákból |
| **Csak duplikátumok** | Csak azok a fájlok, amelyeknek van legalább egy másolatuk |
| **Könyvtárak közötti** | Olyan fájlok, amelyek egy szinkronizált családtag könyvtárában is megvannak |

A **Csak duplikátumok** szűrőre váltva az eredménypanel csak az érintett fájlokat mutatja. A fájlok az eredeti mappaszerkezetükben jelennek meg, így jól látható, hol találhatók az egyes másolatok.

Jelöljön ki egy **● DUPLIKÁTUM** jelzővel ellátott fájlt, majd kattintson az **Összehasonlítás** gombra az eszközsávban. Dupla kattintással is megnyithatja, vagy jobb gombbal kattintva válassza a **Duplikátumok összehasonlítása** menüpontot.

Ha egy mappa összes fájlja duplikátum, a mappa maga is **● DUPLIKÁLT MAPPA** jelzőt kap a fájlszámmal együtt. Kibonthatja a mappát az egyes fájlok megtekintéséhez, vagy összehasonlíthatja a mappát egészben, hogy lássa, hol létezik a duplikált tartalom.

---

## 4. lépés — Duplikátumok összehasonlítása

Az Összehasonlítás nézet egymás mellett mutatja egy duplikátumcsoport összes másolatát:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   [kép]      │   │   [kép]      │   │   [kép]      │
│ C:\Fotók\    │   │ Z:\Család\   │   │ D:\Mentés\   │
│ tengerpart.  │   │ foto.jpg     │   │ img0041.jpg  │
│ jpg          │   │              │   │              │
│ 2,1 MB       │   │ 1,8 MB       │   │ 2,1 MB       │
│ 2023-06-15   │   │ 2023-07-30   │   │ 2023-06-15   │
└──────────────┘   └──────────────┘   └──────────────┘
                   [Bezárás]
```

Minden cella tartalmaz egy előnézeti képet, a fájl teljes elérési útját, méretét és módosítási dátumát. Ez egy csak olvasható nézet — az összes duplikátum adatait áttekintheti, hogy pontosan lássa, hol találhatók a másolatok.

Ha egy duplikált mappát hasonlít össze, az Összehasonlítás nézet mappa szintű cellákat mutat a mappa elérési útjával, a fájlok számával és méretével. Ez megkönnyíti a teljes mappamásolatok azonosítását és kezelését.

A **Bezárás** gombra kattintva visszatér az eredménypanelhez.

---

## Megosztás családtagokkal

Megoszhatja a szkennelési ujjlenyomatokat megbízható személyekkel, hogy megtalálja a különböző könyvtárakban duplikálódott fotókat. **A tényleges képek sehová sem töltődnek fel.** Csak kompakt ujjlenyomatok (és opcionálisan fájlnevek) hagyják el a gépét.

### Google Drive-szinkronizálás beállítása

A csoport egyik tagja egyszer elvégzi az első beállítást:

1. Nyissa meg a **Megosztás > Szinkronizálás beállítása...** menüpontot
2. Adjon meg egy megjelenítési nevet (pl. `anna`) — ez azonosítja az Ön adatait a megosztott mappában
3. Kattintson a **Bejelentkezés Google-lel** gombra — megnyílik egy böngészőablak az engedélyezéshez. Az alkalmazás csak az általa létrehozott fájlokhoz kap hozzáférést, a teljes Google Drive-hoz nem.
4. A Google Drive webes felületén hozzon létre egy megosztott mappát, és ossza meg a kívánt személyekkel. Az alkalmazás közvetlen hivatkozást és rövid útmutatót jelenít meg ehhez a lépéshez.
5. Illessze be a megosztott mappa URL-jét vagy azonosítóját az alkalmazásba
6. Válasszon **adatvédelmi szintet** — azt szabályozza, mi kerüljön megosztásra:

   | Szint | Mit oszt meg |
   |-------|-------------|
   | **Csak fájlnév** *(alapértelmezett)* | Ujjlenyomatok és fájlnevek; a teljes elérési utak titkosak maradnak |
   | **Csak ujjlenyomat** | Kizárólag ujjlenyomatok; fájlnevek és elérési utak titkosak |
   | **Teljes elérési út** | Ujjlenyomatok és teljes fájlelérési utak |

7. Kattintson a **Mentés** gombra

Minden más személy megismétli a 2–7. lépést a saját megjelenítési nevével, ugyanarra a megosztott mappára mutatva.

### A szinkronizálás menete

A szinkronizálás automatikusan zajlik:

- **Indításkor** — az alkalmazás csendben letölti a többiek legfrissebb eredményeit a háttérben
- **Szkennelés után** — automatikusan feltölti az Ön frissített eredményeit
- **Bezáráskor** — végső feltöltés, ha változás történt

Az állapotsávon látható:
- `↕ Szinkronizálás...` — folyamatban
- `✓ Szinkronizálva 2 perce` — naprakész

**Ha nem csatlakozik az internethez**, az állapotsávon ez jelenik meg: `⚠ Szinkronizálás nem elérhető – utolsó ismert adatok láthatók`. A Könyvtárak közötti szűrő az utolsó sikeres szinkronizálás eredményeit mutatja. A feltöltés várólistára kerül, és a következő online alkalommal automatikusan megtörténik.

### Könyvtárak közötti duplikátumok megtekintése

Váltson a **Könyvtárak közötti** szűrőre, hogy lássa, melyek azok a fotói, amelyek más valakinek a könyvtárában is megvannak.

Az Összehasonlítás nézetben a más könyvtárból származó cellák megjelenítik a tulajdonos nevét. Az összes cella csak olvasható — az adatvédelmi szintnek megfelelően láthatja a fájlnevet vagy az elérési utat, a méretét és a dátumát.

### Szinkronizált könyvtárak kezelése

Nyissa meg a **Megosztás > Szinkronizált könyvtárak kezelése** menüpontot, ahol láthatja az összes szinkronizált személyt. Bárkit eltávolíthat a listáról — az adataik törlődnek a helyi adatbázisból.

---

## Kézi export / import (Google Drive nélkül)

Ha nem szeretné használni a Google Drive-ot, az eredményeket fájlként is megoszthatja:

1. **Export** — nyissa meg a **Megosztás > Szkennelési eredmények exportálása...** menüpontot, adjon meg egy megjelenítési nevet, és mentse el a `.json` fájlt. Küldje el e-mailben vagy USB-n a másik személynek.
2. **Import** — nyissa meg a **Megosztás > Szkennelési eredmények importálása...** menüpontot, majd nyissa meg a kapott `.json` fájlt. A könyvtárak közötti egyezések azonnal megjelennek.

A **Megosztás > Szinkronizálás beállítása** menüpontban megadott adatvédelmi szint a kézi exportra is vonatkozik.

---

## Beállítások

### Nyelv módosítása

Az alkalmazás automatikusan a Windows rendszer nyelve alapján választ
magyart vagy angolt. Ha felül szeretné írni, nyissa meg a
**Fájl > Beállítások** menüpontot, válassza ki a kívánt nyelvet a
legördülő listából, majd kattintson a **Mentés** gombra. A változtatás
az alkalmazás újraindítása után lép érvénybe.

### Téma

A Beállítások ablakban elérhető egy témaválasztó. Jelenleg csak a
rendszer alapértelmezett téma támogatott; további témák egy jövőbeli
kiadásban lesznek elérhetők.
