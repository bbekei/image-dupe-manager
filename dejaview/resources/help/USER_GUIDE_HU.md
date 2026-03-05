# DejaView — Felhasználói kézikönyv

## Mit csinál ez az alkalmazás?

A DejaView megkeresi a duplikált és vizuálisan hasonló fotókat a megadott mappákban. Az alkalmazás a képek vizuális tartalmát hasonlítja össze — ezért a duplikátumokat akkor is megtalálja, ha a fájlokat átnevezték, más beállításokkal mentették el, vagy módosult a metaadatuk.

A keresési ujjlenyomatokat meg is oszthatja családtagjaival, hogy megtalálja azokat a fotókat, amelyek több ember könyvtárában is megvannak — a tényleges képek sehová sem töltődnek fel.

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

A főablak bal oldalán egy **oldalsáv** található navigációs hivatkozásokkal, jobb oldalán pedig a **tartalomterület**:

- **Vezérlőpult** — Szkennelés indítása és a munkamenetek megtekintése
- **Duplikátumok böngészése** — Pontos duplikátum csoportok áttekintése, döntés a megtartásról vagy törlésről
- **Hasonlóságok böngészése** — Vizuálisan hasonló képek összehasonlítása egymás mellett
- **Terv áttekintése** — Az összes tervezett művelet összegzése végrehajtás előtt
- **Terv végrehajtása** — A törlés futtatása élő állapotjelzéssel
- **Duplikátum Lomtár** — Törölt fájlok visszaállítása vagy végleges eltávolítása
- **Családi Könyvtár** — Ujjlenyomatok megosztása családtagokkal Google Drive-on vagy fájlexporttal
- **Kérések** — Bejövő és kimenő fotókérések kezelése
- **Beállítások** — Nyelv, téma, teljesítmény-beállítások és szinkronizálási konfiguráció
- **Súgó** — Ez a kézikönyv

---

## Első lépések

### 1. lépés — Szkennelés indítása

1. Nyissa meg a **Vezérlőpultot**
2. Kattintson a **Új szkennelés indítása** gombra a jobb felső sarokban
3. Megnyílik a mappaválasztó — válasszon ki egy vagy több mappát, amelyek a fotókat tartalmazzák
4. A szkennelés automatikusan elindul

**Hasonlóság-felismerés:** A szkennelés indítása előtt bejelölheti a **Hasonlóság-felismerés engedélyezése** jelölőnégyzetet az Indítás gomb mellett. Ez egy további elemzési lépést ad hozzá, amely megtalálja a vizuálisan hasonló (de nem azonos) képeket. Tovább tart, de megtalálja a közel-duplikátumokat, mint a kivágások, átméretezések vagy újratömörített változatok.

### 2. lépés — Előrehaladás figyelése

A **Szkennelés folyamata** panel megjelenik a Vezérlőpulton a szkennelés során. A következőket mutatja:

- **Aktuális fázis** — Fájlok felderítése, Hash-ek kiszámítása, vagy Hasonlóság elemzése
- **Előrehaladás sáv** fájlszámmal (pl. „230 / 490 fájl")
- **Duplikátumszámláló** — élőben frissül, ahogy új duplikátumokat talál
- **Hibaszámláló** — olvashatatlan fájlok (az utolsó hiba megjelenik)

**Vezérlőelemek szkennelés közben:**

| Gomb | Művelet |
|------|---------|
| **Szünet** | Szünetelteti a szkennelést. Az előrehaladás el van mentve — bezárhatja az alkalmazást, és később folytathatja. |
| **Leállítás** | Véglegesen leállítja a szkennelést. A részleges eredmények elérhetők maradnak. |
| **Folytatás** | Folytatja a szüneteltetett szkennelést a korábbi állapotból. A már feldolgozott fájlokat kihagyja. |

A szkennelés befejezésekor megjelenik az **Eredmények megtekintése** gomb, amely egyenesen a Duplikátumok böngészéséhez vezet.

> **Letöltött fotók:** Az internetről letöltött fotókon Windows biztonsági jelölés („Mark of the Web") lehet. A DejaView szkennelés közben automatikusan eltávolítja ezt a jelölést, így a fájlok normálisan feldolgozhatók.

---

## Duplikátumok böngészése

A **Duplikátumok böngészése** képernyő kétpaneles elrendezésű:

- **Bal panel** — A duplikátum csoportok görgethető listája, mindegyik rövid hash-sel és fájlszámmal azonosítva
- **Jobb panel** — A kiválasztott csoport fájljai, előnézeti képekkel, fájlelérési utakkal, méretekkel és felbontással

### Fájlok megjelölése

Minden fájlhoz három műveletgomb tartozik a csoportban:

| Gomb | Szín aktív állapotban | Jelentés |
|------|----------------------|----------|
| **Megtartás** (pipa) | Zöld | Fájl megtartása |
| **Törlés** (kuka) | Piros | Fájl áthelyezése a Duplikátum Lomtárba |
| **Mellőzés** (szem) | Sárga | Fájl kihagyása — nincs művelet |

Az aktív gombra ismét kattintva a művelet kikapcsol.

### Megtartás és a többi törlése

4 vagy több fájlt tartalmazó csoportoknál a Megtartás gombnak van egy legördülő nyila. Kattintson a nyílra, majd válassza a **Megtartás és a többi törlése** opciót — ezzel egy fájlt megtartásra, az összes többit pedig törlésre jelöli egyetlen lépésben.

### Intelligens kiválasztási előbeállítások

Az előbeállítás eszközsáv a csoportlista felett lehetővé teszi a fájlok automatikus jelölését az összes csoportban:

| Előbeállítás | Szabály |
|-------------|---------|
| **Legnagyobb megtartása** | Az egyes csoportokban a legnagyobb fájlméretű fájlt tartja meg |
| **Legújabb megtartása** | A legutóbb módosított fájlt tartja meg |
| **Legrégebbi megtartása** | A legrégebbi módosítási dátumú fájlt tartja meg |
| **Legrövidebb útvonal megtartása** | A legrövidebb fájlelérési úttal rendelkező fájlt tartja meg |
| **Legnagyobb felbontás megtartása** | A legnagyobb képpontos felbontású fájlt tartja meg |

### Mappa hatókör

Az egyes fájlok műveletgombjai mellett található mappaikon gomb engedélyezi a **mappa hatókört**. Aktiváláskor a beállított művelet az azonos mappában lévő összes szkennelt fájlra alkalmazódik, az összes duplikátum csoportban. Alkalmazás előtt megerősítő kérdés jelenik meg.

---

## Hasonlóságok böngészése

A **Hasonlóságok böngészése** képernyő a vizuálisan hasonló (de nem azonos) képcsoportok áttekintésére szolgál. Ez a képernyő csak akkor tartalmaz adatokat, ha a szkennelés során engedélyezte a hasonlóság-felismerést.

### Összehasonlító csúszka

A képernyő tetején egy **összehasonlító csúszka** mutat két képet egymás mellett húzható elválasztóval. Ez segít felismerni a hasonló fájlok közötti finom vizuális különbségeket.

### Fájlok kiválasztása összehasonlításra

Kattintson bármelyik előnézeti képre az alábbi rácsban, hogy hozzárendelje a bal (L) vagy jobb (R) helyhez az összehasonlító csúszkában. A már kiválasztott képre kattintva megszüntetheti a kijelölést. Minden csoportban az első két kép automatikusan kiválasztásra kerül.

### Megtartási ajánlás

Egy zöld szalag mutatja az **ajánlott megtartandó fájlt** az indoklással együtt (pl. legnagyobb felbontás, legnagyobb fájl). Ez egy javaslat — felülírhatja a saját döntéseivel.

### Csoportnavigáció

A **Vissza** és **Következő** gombokkal lépkedhet a hasonlósági csoportok között. Az aktuális pozíció „1 / 5" stb. formátumban jelenik meg.

### Műveletek és előbeállítások

Ugyanazok a Megtartás / Törlés / Mellőzés gombok és intelligens előbeállítások érhetők el, mint a Duplikátumok böngészésénél.

---

## Terv áttekintése

A módosítások végrehajtása előtt látogasson el a **Terv áttekintése** oldalra, ahol megtekintheti az összes döntés összegzését:

- **Megtartás száma** — érintetlen maradó fájlok
- **Törlés száma** — a Duplikátum Lomtárba kerülő fájlok
- **Mellőzés száma** — kihagyott fájlok (nincs művelet)
- **Visszanyerhető összméret** — felszabaduló lemezterület

Egy görgethető lista mutatja az egyes tervezett műveleteket a fájlelérési úttal és mérettel.

Az **Összes törlése** gomb visszaállítja az összes döntést, ha újra szeretné kezdeni.

---

## Terv végrehajtása

Kattintson a **Terv végrehajtása** gombra a Terv áttekintése képernyőn. Egy megerősítő párbeszédpanel emlékezteti, hogy a fájlok a Duplikátum Lomtárba kerülnek, és 30 napon belül visszaállíthatók.

A **Végrehajtás** képernyő a következőket mutatja:

- **Előrehaladás sáv** aktuális/összesített számmal
- **Fázisjelző** — „Helyi tisztítás" (fájlok lomtárba helyezése), majd „Felhő szinkronizálás", ha a családi megosztás be van állítva
- **Valós idejű napló** — minden fájlművelet megjelenése
- **Befejezési összegzés** — sikeres és hibás műveletek száma

A végrehajtás befejezésekor megjelenik a **Duplikátum Lomtár megtekintése** gomb.

---

## Duplikátum Lomtár

A törölt fájlok nem törlődnek azonnal a lemezről. A **Duplikátum Lomtárba** kerülnek, ahol 30 napig visszaállíthatók.

Minden elem a következőket mutatja:

- Az eredeti fájlelérési út és méret
- **Lejárati visszaszámláló** — „Lejár X nap múlva" vagy „Lejárt"
- **Visszaállítás** gomb — visszahelyezi a fájlt az eredeti helyére

### Végleges törlés

- Jelöljön ki elemeket a jelölőnégyzetekkel, majd kattintson a **Végleges törlés** gombra a lemezről való eltávolításukhoz. Ez nem vonható vissza.
- A **Lejártak törlése** eltávolítja az összes 30 napon túli elemet. Megerősítő párbeszédpanel jelenik meg.

---

## Családi megosztás

Megoszhatja a szkennelési ujjlenyomatokat megbízható családtagjaival, hogy megtalálja a különböző könyvtárakban duplikálódott fotókat. **A tényleges képek sehová sem töltődnek fel.** Csak kompakt ujjlenyomatok (és opcionálisan fájlnevek) hagyják el a gépét.

### Google Drive szinkronizálás beállítása

1. Nyissa meg a **Beállítások** oldalt, és görgessen a **Google Drive szinkronizálás** részhez
2. Adjon meg egy **Megjelenítési nevet** (pl. `anna`) — ez azonosítja az Ön adatait a megosztott mappában
3. Kattintson a **Bejelentkezés Google-lal** gombra — megnyílik egy böngészőablak az engedélyezéshez. Az alkalmazás csak az általa létrehozott fájlokhoz kap hozzáférést, a teljes Google Drive-hoz nem.
4. A Google Drive webes felületén hozzon létre egy megosztott mappát, és ossza meg a családtagjaival
5. Illessze be a megosztott mappa azonosítóját a **Megosztott mappa azonosító** mezőbe
6. Válasszon **adatvédelmi szintet** — azt szabályozza, mi kerül megosztásra:

   | Szint | Mit oszt meg |
   |-------|-------------|
   | **Csak fájlnév** *(alapértelmezett)* | Ujjlenyomatok és fájlnevek; a teljes elérési utak titkosak maradnak |
   | **Csak hash** | Kizárólag ujjlenyomatok; fájlnevek és elérési utak titkosak |
   | **Teljes útvonal** | Ujjlenyomatok és teljes fájlelérési utak |

7. Kattintson a **Szinkronizálási beállítások mentése** gombra

Minden más családtag megismétli ezeket a lépéseket a saját megjelenítési nevével, ugyanarra a megosztott mappára mutatva.

### Kézi export / import

Ha nem szeretné használni a Google Drive-ot, nyissa meg a **Családi Könyvtár** képernyőt:

- **Hash-ek exportálása** — elmenti a szkennelési ujjlenyomatokat egy `.json` fájlba. Küldje el e-mailben vagy USB-n a másik személynek.
- **Hash-ek importálása** — megnyit egy kapott `.json` fájlt. A könyvtárak közötti egyezések azonnal megjelennek.

A Beállításokban megadott adatvédelmi szint az exportált fájlokra is vonatkozik.

### Szinkronizált könyvtárak kezelése

A **Családi Könyvtár** képernyő az összes csatlakozott családtagot mutatja az utolsó szinkronizálás dátumával. A **Szinkronizálás most** gombbal lekérheti a legfrissebb adatokat, vagy eltávolíthatja a családtagot (adataik törlődnek a helyi adatbázisból).

---

## Kérések

A **Kérések** képernyő két fület tartalmaz:

- **Bejövő** — családtagok fotókérései. Minden kérést **jóváhagyhat** vagy **elutasíthat**.
- **Kimenő** — az Ön által küldött kérések. Megjelenik az aktuális állapot (Függő, Jóváhagyott, Elutasított vagy Visszavont).

---

## Beállítások

### Nyelv

Választhat az **Angol**, **Magyar** vagy **Automatikus felismerés** (a Windows rendszernyelv alapján) közül.

### Téma

Váltás **Sötét** és **Világos** mód között.

### Teljesítmény

| Beállítás | Leírás |
|-----------|--------|
| **Max szkennelési szálak** | A szkennelés során használt CPU szálak száma (1–16). Magasabb értékek gyorsabb szkennelést, de nagyobb CPU-használatot eredményeznek. |
| **Szkennelés késleltetés (ms)** | Műveletek közötti késleltetés (0–5000). Magasabb értékek csökkentik a CPU-használatot szkennelés közben. 0 = nincs késleltetés. |
| **Teljesítménynaplózás** | Bekapcsolva részletes időzítési adatokat ír egy CSV fájlba diagnosztikai célokra. |

### Google Drive szinkronizálás

Lásd a fenti [Családi megosztás](#családi-megosztás) részt a beállítási utasításokért.
