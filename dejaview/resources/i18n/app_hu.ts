<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="hu_HU">
<!--
  app_hu.ts — Hungarian translations for DejaView (plan §Architecture).
  All UI-visible self.tr() strings are listed here, organized by class context.
  Edit translations here, then run:
    lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm
  The compiled .qm is bundled by the installer (plan §Phase 7).

  IMPORTANT: Source strings must exactly match the runtime output of self.tr() calls.
  Python unicode escapes (e.g. \u2026) resolve to actual characters at runtime.
-->

<!-- ═══════════════════════════════════════════════════════════════════════════
     MainWindow (ui/main_window.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>MainWindow</name>
    <!-- Window title -->
    <message>
        <source>DejaView</source>
        <translation>DejaView</translation>
    </message>
    <!-- Menu bar -->
    <message>
        <source>File</source>
        <translation>Fájl</translation>
    </message>
    <message>
        <source>Add Folder…</source>
        <translation>Mappa hozzáadása…</translation>
    </message>
    <message>
        <source>Settings…</source>
        <translation>Beállítások…</translation>
    </message>
    <message>
        <source>Exit</source>
        <translation>Kilépés</translation>
    </message>
    <message>
        <source>Scan</source>
        <translation>Vizsgálat</translation>
    </message>
    <message>
        <source>Start Scan</source>
        <translation>Vizsgálat indítása</translation>
    </message>
    <message>
        <source>Pause</source>
        <translation>Szünet</translation>
    </message>
    <message>
        <source>Stop</source>
        <translation>Leállítás</translation>
    </message>
    <message>
        <source>Share</source>
        <translation>Megosztás</translation>
    </message>
    <message>
        <source>Export Scan Results…</source>
        <translation>Vizsgálati eredmények exportálása…</translation>
    </message>
    <message>
        <source>Import Scan Results…</source>
        <translation>Vizsgálati eredmények importálása…</translation>
    </message>
    <message>
        <source>Configure Sync…</source>
        <translation>Szinkronizálás beállítása…</translation>
    </message>
    <message>
        <source>Manage Synced Libraries…</source>
        <translation>Szinkronizált könyvtárak kezelése…</translation>
    </message>
    <!-- Status bar messages -->
    <message>
        <source>Add folders to get started.</source>
        <translation>Adjon hozzá mappákat a kezdéshez.</translation>
    </message>
    <message>
        <source>Scan paused. Click Resume to continue.</source>
        <translation>Vizsgálat szüneteltetve. Kattintson a Folytatás gombra.</translation>
    </message>
    <message>
        <source>Scan {0}</source>
        <translation>Vizsgálat {0}</translation>
    </message>
    <message>
        <source>Select Folder to Scan</source>
        <translation>Válasszon mappát a vizsgálathoz</translation>
    </message>
    <message>
        <source>Scan complete.</source>
        <translation>Vizsgálat kész.</translation>
    </message>
    <message>
        <source>Error: {0}</source>
        <translation>Hiba: {0}</translation>
    </message>
    <message>
        <source>Comparing duplicate group (SHA: {0}…)</source>
        <translation>Duplikátum csoport összehasonlítása (SHA: {0}…)</translation>
    </message>
    <message>
        <source>Ready.</source>
        <translation>Kész.</translation>
    </message>
    <!-- Export (Phase 5) -->
    <message>
        <source>No scan session to export.</source>
        <translation>Nincs exportálható vizsgálat.</translation>
    </message>
    <message>
        <source>Export Scan Results</source>
        <translation>Vizsgálati eredmények exportálása</translation>
    </message>
    <message>
        <source>Display name (used as filename):</source>
        <translation>Megjelenítési név (fájlnévként használva):</translation>
    </message>
    <message>
        <source>Invalid Name</source>
        <translation>Érvénytelen név</translation>
    </message>
    <message>
        <source>Display name must be 1–64 characters, letters, digits, dash, or underscore only.</source>
        <translation>A megjelenítési név 1–64 karakter lehet, csak betűk, számok, kötőjel vagy aláhúzás.</translation>
    </message>
    <message>
        <source>Export Error</source>
        <translation>Exportálási hiba</translation>
    </message>
    <message>
        <source>Save Export File</source>
        <translation>Exportfájl mentése</translation>
    </message>
    <message>
        <source>JSON files (*.json)</source>
        <translation>JSON fájlok (*.json)</translation>
    </message>
    <message>
        <source>Could not write file: {0}</source>
        <translation>Nem sikerült írni a fájlt: {0}</translation>
    </message>
    <message>
        <source>Exported {0} files to {1}.</source>
        <translation>{0} fájl exportálva ide: {1}.</translation>
    </message>
    <!-- Import (Phase 5) -->
    <message>
        <source>Import Scan Results</source>
        <translation>Vizsgálati eredmények importálása</translation>
    </message>
    <message>
        <source>Import Error</source>
        <translation>Importálási hiba</translation>
    </message>
    <message>
        <source>Could not read file: {0}</source>
        <translation>Nem sikerült olvasni a fájlt: {0}</translation>
    </message>
    <message>
        <source>Imported scan results from &apos;{0}&apos;.</source>
        <translation>Vizsgálati eredmények importálva: „{0}".</translation>
    </message>
    <!-- Sync (Phase 6) -->
    <message>
        <source>Sync not configured.</source>
        <translation>Szinkronizálás nincs beállítva.</translation>
    </message>
    <message>
        <source>Signing in with Google…</source>
        <translation>Bejelentkezés a Google-ba…</translation>
    </message>
    <message>
        <source>Signed in to Google Drive.</source>
        <translation>Bejelentkezve a Google Drive-ba.</translation>
    </message>
    <message>
        <source>Google sign-in failed: {0}</source>
        <translation>A Google bejelentkezés sikertelen: {0}</translation>
    </message>
    <message>
        <source>Unknown error</source>
        <translation>Ismeretlen hiba</translation>
    </message>
    <message>
        <source>Removed peer &apos;{0}&apos;.</source>
        <translation>„{0}" eltávolítva.</translation>
    </message>
    <message>
        <source>Sync settings saved.</source>
        <translation>Szinkronizálási beállítások mentve.</translation>
    </message>
    <message>
        <source>↕ Syncing…</source>
        <translation>↕ Szinkronizálás…</translation>
    </message>
    <message>
        <source>✓ Synced.</source>
        <translation>✓ Szinkronizálva.</translation>
    </message>
    <message>
        <source>⚠ Sync unavailable — showing last known data</source>
        <translation>⚠ Szinkronizálás nem elérhető — legutóbbi adatok megjelenítése</translation>
    </message>
    <message>
        <source>✓ Sync complete.</source>
        <translation>✓ Szinkronizálás kész.</translation>
    </message>
    <!-- Scan summary (Feature Request 2) -->
    <message>
        <source>Scan complete: {0} files scanned, {1} duplicates in {2} groups.</source>
        <translation>Vizsgálat kész: {0} fájl átvizsgálva, {1} duplikátum {2} csoportban.</translation>
    </message>
    <message>
        <source>Scan complete: {0} files scanned. No duplicates found.</source>
        <translation>Vizsgálat kész: {0} fájl átvizsgálva. Nem találtunk duplikátumot.</translation>
    </message>
    <message>
        <source>Comparing duplicated folder: {0}</source>
        <translation>Duplikált mappa összehasonlítása: {0}</translation>
    </message>
    <message>
        <source>Settings saved.</source>
        <translation>Beállítások mentve.</translation>
    </message>
    <!-- Help menu (Feature Request 1) -->
    <message>
        <source>Help</source>
        <translation>Súgó</translation>
    </message>
    <message>
        <source>User Guide…</source>
        <translation>Felhasználói kézikönyv…</translation>
    </message>
    <!-- Planning mode (Pluggable Views) -->
    <message>
        <source>Plan Actions…</source>
        <translation>Műveletek tervezése…</translation>
    </message>
    <message>
        <source>Planning mode — mark duplicates with actions.</source>
        <translation>Tervezési mód — jelölje meg a duplikátumokat műveletekkel.</translation>
    </message>
    <!-- UX Redesign Phase 3 — Execution -->
    <message>
        <source>Confirm Deletion</source>
        <translation>Törlés megerősítése</translation>
    </message>
    <message>
        <source>Move {0} files to .dejaview_trash?
Files are recoverable for 30 days.</source>
        <translation>{0} fájl áthelyezése a .dejaview_trash mappába?
A fájlok 30 napig helyreállíthatók.</translation>
    </message>
    <message>
        <source>Execution complete: {0} files deleted, {1} errors.</source>
        <translation>Végrehajtás kész: {0} fájl törölve, {1} hiba.</translation>
    </message>
    <message>
        <source>Execution complete: {0} files deleted.</source>
        <translation>Végrehajtás kész: {0} fájl törölve.</translation>
    </message>
    <message>
        <source>Executing plan…</source>
        <translation>Terv végrehajtása…</translation>
    </message>
    <message>
        <source>Plan cleared.</source>
        <translation>Terv törölve.</translation>
    </message>
    <!-- UX Redesign Phase 1 (deferred strings) -->
    <message>
        <source>Family Discovery — coming soon.</source>
        <translation>Családi felfedezés — hamarosan.</translation>
    </message>
    <message>
        <source>Request Approval — coming soon.</source>
        <translation>Kérés jóváhagyása — hamarosan.</translation>
    </message>
    <message>
        <source>Welcome to DejaView.</source>
        <translation>Üdvözli a DejaView.</translation>
    </message>
    <message>
        <source>Last scan: {0} files, {1} duplicates in {2} groups.</source>
        <translation>Utolsó vizsgálat: {0} fájl, {1} duplikátum {2} csoportban.</translation>
    </message>
    <message>
        <source>Last scan: {0} files scanned. No duplicates found.</source>
        <translation>Utolsó vizsgálat: {0} fájl átvizsgálva. Nem találtunk duplikátumot.</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     FolderPanel (ui/folder_panel.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>FolderPanel</name>
    <message>
        <source>Scan Folders:</source>
        <translation>Vizsgálandó mappák:</translation>
    </message>
    <message>
        <source>+ Add…</source>
        <translation>+ Hozzáadás…</translation>
    </message>
    <message>
        <source>- Remove</source>
        <translation>- Eltávolítás</translation>
    </message>
    <message>
        <source>Select Folder to Scan</source>
        <translation>Válasszon mappát a vizsgálathoz</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     ScanControl (ui/scan_control.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ScanControl</name>
    <message>
        <source>▶ Start</source>
        <translation>▶ Indítás</translation>
    </message>
    <message>
        <source>⏸ Pause</source>
        <translation>⏸ Szünet</translation>
    </message>
    <message>
        <source>▶ Resume</source>
        <translation>▶ Folytatás</translation>
    </message>
    <message>
        <source>⏹ Stop</source>
        <translation>⏹ Leállítás</translation>
    </message>
    <message>
        <source>PAUSED</source>
        <translation>SZÜNETELTETETT</translation>
    </message>
    <message>
        <source>Complete</source>
        <translation>Kész</translation>
    </message>
    <message>
        <source>Similar</source>
        <translation>Hasonló</translation>
    </message>
    <message>
        <source>Also detect similar images (slower)</source>
        <translation>Hasonló képek keresése is (lassabb)</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     ResultsPanel (ui/results_panel.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ResultsPanel</name>
    <message>
        <source>All</source>
        <translation>Mind</translation>
    </message>
    <message>
        <source>Duplicates Only</source>
        <translation>Csak duplikátumok</translation>
    </message>
    <message>
        <source>Cross-Library</source>
        <translation>Könyvtárak között</translation>
    </message>
    <message>
        <source>● DUPLICATE</source>
        <translation>● DUPLIKÁTUM</translation>
    </message>
    <message>
        <source>Compare</source>
        <translation>Összehasonlítás</translation>
    </message>
    <message>
        <source>Compare Duplicates</source>
        <translation>Duplikátumok összehasonlítása</translation>
    </message>
    <message>
        <source>● DUPLICATED FOLDER ({0} files)</source>
        <translation>● DUPLIKÁLT MAPPA ({0} fájl)</translation>
    </message>
    <message>
        <source>✦ CROSS-LIB ({0})</source>
        <translation>✦ KÖNYVTÁRAK KÖZÖTT ({0})</translation>
    </message>
    <message>
        <source>Name</source>
        <translation>Név</translation>
    </message>
    <message>
        <source>Status</source>
        <translation>Állapot</translation>
    </message>
    <message>
        <source>Action</source>
        <translation>Művelet</translation>
    </message>
    <message>
        <source>★ MASTER</source>
        <translation>★ MESTER</translation>
    </message>
    <message>
        <source>Tree View</source>
        <translation>Fa nézet</translation>
    </message>
    <message>
        <source>Cluster View</source>
        <translation>Csoport nézet</translation>
    </message>
    <message>
        <source>Search files...</source>
        <translation>Fájlok keresése...</translation>
    </message>
    <message>
        <source>{0} groups · {1} files · {2} potential savings</source>
        <translation>{0} csoport · {1} fájl · {2} lehetséges megtakarítás</translation>
    </message>
    <message>
        <source>{0} duplicate groups found</source>
        <translation>{0} duplikátum csoport található</translation>
    </message>
    <message>
        <source>Previous</source>
        <translation>Előző</translation>
    </message>
    <message>
        <source>Next</source>
        <translation>Következő</translation>
    </message>
    <message>
        <source>Page {0} of {1}</source>
        <translation>{0}. oldal / {1}</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     _FileTile (ui/compare_view.py — per-file tile widget)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>_FileTile</name>
    <message>
        <source>No thumbnail</source>
        <translation>Nincs előnézet</translation>
    </message>
    <message>
        <source>Remote</source>
        <translation>Távoli</translation>
    </message>
    <message>
        <source>({0}&apos;s copy)</source>
        <translation>({0} másolata)</translation>
    </message>
    <message>
        <source>(read only)</source>
        <translation>(csak olvasható)</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     CompareView (ui/compare_view.py — read-only comparison widget)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>CompareView</name>
    <message>
        <source>Close</source>
        <translation>Bezárás</translation>
    </message>
    <message>
        <source>DUPLICATE GROUP ({0} files · SHA: {1}…)</source>
        <translation>DUPLIKÁTUM CSOPORT ({0} fájl · SHA: {1}…)</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     SettingsDialog (ui/settings_dialog.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>SettingsDialog</name>
    <message>
        <source>Settings</source>
        <translation>Beállítások</translation>
    </message>
    <message>
        <source>Language</source>
        <translation>Nyelv</translation>
    </message>
    <message>
        <source>Auto (system default)</source>
        <translation>Automatikus (rendszer alapértelmezett)</translation>
    </message>
    <message>
        <source>Theme</source>
        <translation>Téma</translation>
    </message>
    <message>
        <source>System Default</source>
        <translation>Rendszer alapértelmezett</translation>
    </message>
    <message>
        <source>Additional themes coming in a future release.</source>
        <translation>További témák egy jövőbeli kiadásban lesznek elérhetők.</translation>
    </message>
    <message>
        <source>Please restart DejaView to apply the new language.</source>
        <translation>Kérjük, indítsa újra a DejaView-t az új nyelv alkalmazásához.</translation>
    </message>
    <message>
        <source>Save</source>
        <translation>Mentés</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Mégse</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     FolderCompareView (ui/compare_view.py — folder-level comparison)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>FolderCompareView</name>
    <message>
        <source>Close</source>
        <translation>Bezárás</translation>
    </message>
    <message>
        <source>DUPLICATED FOLDER (no hash data)</source>
        <translation>DUPLIKÁLT MAPPA (nincs hash adat)</translation>
    </message>
    <message>
        <source>DUPLICATED FOLDER ({0} locations · {1} files each)</source>
        <translation>DUPLIKÁLT MAPPA ({0} helyen · egyenként {1} fájl)</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     ShareDialog (ui/share_dialog.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ShareDialog</name>
    <message>
        <source>Configure Sync</source>
        <translation>Szinkronizálás beállítása</translation>
    </message>
    <message>
        <source>Identity</source>
        <translation>Azonosító</translation>
    </message>
    <message>
        <source>Display name:</source>
        <translation>Megjelenítési név:</translation>
    </message>
    <message>
        <source>e.g. alice</source>
        <translation>pl. alice</translation>
    </message>
    <message>
        <source>Google Drive</source>
        <translation>Google Drive</translation>
    </message>
    <message>
        <source>Sign in with Google</source>
        <translation>Bejelentkezés Google-lal</translation>
    </message>
    <message>
        <source>Shared folder ID:</source>
        <translation>Megosztott mappa azonosító:</translation>
    </message>
    <message>
        <source>Paste Google Drive folder ID here</source>
        <translation>Illessze be a Google Drive mappa azonosítóját</translation>
    </message>
    <message>
        <source>Privacy</source>
        <translation>Adatvédelem</translation>
    </message>
    <message>
        <source>Export privacy level:</source>
        <translation>Exportálási adatvédelmi szint:</translation>
    </message>
    <message>
        <source>Filename only</source>
        <translation>Csak fájlnév</translation>
    </message>
    <message>
        <source>Hash only</source>
        <translation>Csak hash</translation>
    </message>
    <message>
        <source>Full path</source>
        <translation>Teljes elérési út</translation>
    </message>
    <message>
        <source>Synced Libraries</source>
        <translation>Szinkronizált könyvtárak</translation>
    </message>
    <message>
        <source>Remove Peer</source>
        <translation>Partner eltávolítása</translation>
    </message>
    <message>
        <source>Sync Now</source>
        <translation>Szinkronizálás most</translation>
    </message>
    <message>
        <source>Save</source>
        <translation>Mentés</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Mégse</translation>
    </message>
    <message>
        <source>Signed in</source>
        <translation>Bejelentkezve</translation>
    </message>
    <message>
        <source>Not signed in</source>
        <translation>Nincs bejelentkezve</translation>
    </message>
    <message>
        <source>Invalid Name</source>
        <translation>Érvénytelen név</translation>
    </message>
    <message>
        <source>Display name must be 1–64 characters, letters, digits, dash, or underscore only.</source>
        <translation>A megjelenítési név 1–64 karakter lehet, csak betűk, számok, kötőjel vagy aláhúzás.</translation>
    </message>
    <message>
        <source>Invalid folder ID format.</source>
        <translation>Érvénytelen mappa azonosító formátum.</translation>
    </message>
    <message>
        <source>Remove &apos;{0}&apos; and all their synced data?</source>
        <translation>Eltávolítja „{0}" felhasználót és összes szinkronizált adatát?</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Scanner (core/scanner.py — status messages emitted to UI)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>Scanner</name>
    <message>
        <source>Discovering files…</source>
        <translation>Fájlok keresése…</translation>
    </message>
    <message>
        <source>Folder unreachable, skipping: {0}</source>
        <translation>Mappa nem elérhető, kihagyás: {0}</translation>
    </message>
    <message>
        <source>Hashing {0} candidate(s)…</source>
        <translation>{0} jelölt hashelése…</translation>
    </message>
</context>
<!-- ═══════════════════════════════════════════════════════════════════════════
     HelpDialog (ui/help_dialog.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>HelpDialog</name>
    <message>
        <source>User Guide</source>
        <translation>Felhasználói kézikönyv</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Bezárás</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     ScanProgressWidget (ui/scan_progress.py — progress panel during scanning)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ScanProgressWidget</name>
    <message>
        <source>Scanning in progress…</source>
        <translation>Vizsgálat folyamatban…</translation>
    </message>
    <message>
        <source>Scan complete</source>
        <translation>Vizsgálat kész</translation>
    </message>
    <message>
        <source>Scan paused</source>
        <translation>Vizsgálat szüneteltetve</translation>
    </message>
    <message>
        <source>Scan stopped</source>
        <translation>Vizsgálat leállítva</translation>
    </message>
    <message>
        <source>Discovery</source>
        <translation>Keresés</translation>
    </message>
    <message>
        <source>Hashing</source>
        <translation>Hashelés</translation>
    </message>
    <message>
        <source>Similarity</source>
        <translation>Hasonlóság</translation>
    </message>
    <message>
        <source>Finalize</source>
        <translation>Véglegesítés</translation>
    </message>
    <message>
        <source>searching…</source>
        <translation>keresés…</translation>
    </message>
    <message>
        <source>{0} files found</source>
        <translation>{0} fájl találva</translation>
    </message>
    <message>
        <source>{0} / {1} files</source>
        <translation>{0} / {1} fájl</translation>
    </message>
    <message>
        <source>{0} files</source>
        <translation>{0} fájl</translation>
    </message>
    <message>
        <source>complete</source>
        <translation>kész</translation>
    </message>
    <message>
        <source>processing…</source>
        <translation>feldolgozás…</translation>
    </message>
    <message>
        <source>Completed in {0}</source>
        <translation>{0} alatt kész</translation>
    </message>
    <message>
        <source>~{0} left</source>
        <translation>~{0} van hátra</translation>
    </message>
    <message>
        <source>{0}s</source>
        <translation>{0} mp</translation>
    </message>
    <message>
        <source>{0}m {1}s</source>
        <translation>{0} p {1} mp</translation>
    </message>
    <message>
        <source>{0}h {1}m</source>
        <translation>{0} ó {1} p</translation>
    </message>
    <message>
        <source>{0}d {1}h</source>
        <translation>{0} n {1} ó</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Dashboard (ui/dashboard.py — home screen with status cards)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>Dashboard</name>
    <message>
        <source>DejaView</source>
        <translation>DejaView</translation>
    </message>
    <message>
        <source>Family photo deduplication and synchronization</source>
        <translation>Családi fotók deduplikálása és szinkronizálása</translation>
    </message>
    <message>
        <source>Local Duplicates</source>
        <translation>Helyi duplikátumok</translation>
    </message>
    <message>
        <source>Family Photos</source>
        <translation>Családi fotók</translation>
    </message>
    <message>
        <source>Pending Requests</source>
        <translation>Függő kérések</translation>
    </message>
    <message>
        <source>Last synced: never</source>
        <translation>Utolsó szinkronizálás: soha</translation>
    </message>
    <message>
        <source>Sync Now</source>
        <translation>Szinkronizálás most</translation>
    </message>
    <message>
        <source>Start New Scan</source>
        <translation>Új vizsgálat indítása</translation>
    </message>
    <message>
        <source>No scan yet</source>
        <translation>Még nincs vizsgálat</translation>
    </message>
    <message>
        <source>{0} duplicate groups</source>
        <translation>{0} duplikátum csoport</translation>
    </message>
    <message>
        <source>No duplicates found</source>
        <translation>Nem találtunk duplikátumot</translation>
    </message>
    <message>
        <source>Photos your family has that you don&apos;t</source>
        <translation>Fotók, amelyek a családnál megvannak, de nálad nincsenek</translation>
    </message>
    <message>
        <source>Import or sync to discover family photos</source>
        <translation>Importáljon vagy szinkronizáljon a családi fotók felfedezéséhez</translation>
    </message>
    <message>
        <source>No pending requests</source>
        <translation>Nincsenek függő kérések</translation>
    </message>
    <message>
        <source>{0} pending photo requests</source>
        <translation>{0} függő fotókérés</translation>
    </message>
    <message>
        <source>Last synced: {0}</source>
        <translation>Utolsó szinkronizálás: {0}</translation>
    </message>
    <message>
        <source>Similar Images</source>
        <translation>Hasonló képek</translation>
    </message>
    <message>
        <source>Enable similarity scan to detect</source>
        <translation>Hasonlóság-keresés engedélyezése</translation>
    </message>
    <message>
        <source>{0} similarity groups</source>
        <translation>{0} hasonlósági csoport</translation>
    </message>
    <!-- Data Compression: sync error recovery (§5.2) -->
    <message>
        <source>Sync Failed — {0}: {1}</source>
        <translation>Szinkronizálás sikertelen — {0}: {1}</translation>
    </message>
    <message>
        <source>Retry Download</source>
        <translation>Letöltés újrapróbálása</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     CleanupScreen (ui/cleanup_screen.py — scan/results/planning container)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>CleanupScreen</name>
    <message>
        <source>Comparing duplicate group (SHA: {0}…)</source>
        <translation>Duplikátum csoport összehasonlítása (SHA: {0}…)</translation>
    </message>
    <message>
        <source>Comparing duplicated folder: {0}</source>
        <translation>Duplikált mappa összehasonlítása: {0}</translation>
    </message>
    <message>
        <source>Ready.</source>
        <translation>Kész.</translation>
    </message>
    <message>
        <source>Planning mode — mark duplicates with actions.</source>
        <translation>Tervezési mód — jelölje meg a duplikátumokat műveletekkel.</translation>
    </message>
    <message>
        <source>Smart select: {0} kept, {1} marked for deletion</source>
        <translation>Intelligens kiválasztás: {0} megtartva, {1} törlésre jelölve</translation>
    </message>
    <message>
        <source>Smart Select Complete</source>
        <translation>Intelligens kiválasztás kész</translation>
    </message>
    <message>
        <source>{0} files kept, {1} marked for deletion.

Would you like to review the plan?</source>
        <translation>{0} fájl megtartva, {1} törlésre jelölve.

Szeretné áttekinteni a tervet?</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     PlanningPanel (ui/planning_panel.py — action planning view)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>PlanningPanel</name>
    <message>
        <source>← Back to Results</source>
        <translation>← Vissza az eredményekhez</translation>
    </message>
    <message>
        <source>Planning Mode</source>
        <translation>Tervezési mód</translation>
    </message>
    <message>
        <source>Keep Newest Only</source>
        <translation>Csak a legújabb megtartása</translation>
    </message>
    <message>
        <source>Local Duplicates</source>
        <translation>Helyi duplikátumok</translation>
    </message>
    <message>
        <source>Cross-Library</source>
        <translation>Könyvtárak között</translation>
    </message>
    <message>
        <source>All</source>
        <translation>Mind</translation>
    </message>
    <message>
        <source>Review Plan »</source>
        <translation>Terv áttekintése »</translation>
    </message>
    <message>
        <source>No actionable items</source>
        <translation>Nincs elvégezhető művelet</translation>
    </message>
    <message>
        <source>All {0} items decided</source>
        <translation>Mind a(z) {0} elem eldöntve</translation>
    </message>
    <message>
        <source>{0} / {1} decided</source>
        <translation>{0} / {1} eldöntve</translation>
    </message>
    <message>
        <source>Automatically mark all older copies for deletion,
keeping only the newest copy of each duplicate group.</source>
        <translation>Automatikusan törölésre jelöli az összes régebbi másolatot,
csak a legújabb példányt tartja meg minden duplikátum csoportban.</translation>
    </message>
    <message>
        <source>This will mark {0} older copies for deletion, keeping only the newest copy of each duplicate group.

Cross-library matches are excluded.

Continue?</source>
        <translation>{0} régebbi másolat törlésre jelölése, minden duplikátum csoportból csak a legújabb példány megtartása.

A könyvtárak közötti egyezések ki vannak zárva.

Folytatja?</translation>
    </message>
    <message>
        <source>Mark Others for Deletion?</source>
        <translation>Többi másolat törlésre jelölése?</translation>
    </message>
    <message>
        <source>You kept {0}.

Mark the other {1} copies for deletion?</source>
        <translation>Megtartotta: {0}.

Törölésre jelöli a többi {1} másolatot?</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     PlanReviewScreen (ui/plan_review.py — Plan Review safety gate)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>PlanReviewScreen</name>
    <message>
        <source>← Back to Planning</source>
        <translation>← Vissza a tervezéshez</translation>
    </message>
    <message>
        <source>Plan Review</source>
        <translation>Terv áttekintése</translation>
    </message>
    <message>
        <source>Clear Plan</source>
        <translation>Terv törlése</translation>
    </message>
    <message>
        <source>Files to Delete (0)</source>
        <translation>Törlendő fájlok (0)</translation>
    </message>
    <message>
        <source>Files to Delete ({0})</source>
        <translation>Törlendő fájlok ({0})</translation>
    </message>
    <message>
        <source>Path</source>
        <translation>Elérési út</translation>
    </message>
    <message>
        <source>Size</source>
        <translation>Méret</translation>
    </message>
    <message>
        <source>Files to Request (0)</source>
        <translation>Kérendő fájlok (0)</translation>
    </message>
    <message>
        <source>Request queue will be available
after Family Discovery is enabled.</source>
        <translation>A kérési sor a Családi felfedezés
engedélyezése után lesz elérhető.</translation>
    </message>
    <message>
        <source>Storage saved: 0 B</source>
        <translation>Megtakarított tárhely: 0 B</translation>
    </message>
    <message>
        <source>Storage saved: {0}</source>
        <translation>Megtakarított tárhely: {0}</translation>
    </message>
    <message>
        <source>Files kept: 0</source>
        <translation>Megtartott fájlok: 0</translation>
    </message>
    <message>
        <source>Files kept: {0}</source>
        <translation>Megtartott fájlok: {0}</translation>
    </message>
    <message>
        <source>Apply Changes »</source>
        <translation>Módosítások alkalmazása »</translation>
    </message>
    <message>
        <source>Remove folder from plan</source>
        <translation>Mappa eltávolítása a tervből</translation>
    </message>
    <message>
        <source>Remove from plan</source>
        <translation>Eltávolítás a tervből</translation>
    </message>
    <message>
        <source>Peer / Hash</source>
        <translation>Partner / Hash</translation>
    </message>
    <message>
        <source>Files to Request ({0})</source>
        <translation>Kérendő fájlok ({0})</translation>
    </message>
    <message>
        <source>No photo requests yet.
Use Family Discovery to request photos.</source>
        <translation>Még nincsenek fotókérések.
Használja a Családi felfedezést fotók kéréséhez.</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     ExecutionScreen (ui/execution_screen.py — Phase 3 execution progress)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ExecutionScreen</name>
    <message>
        <source>Executing plan…</source>
        <translation>Terv végrehajtása…</translation>
    </message>
    <message>
        <source>Local Cleanup</source>
        <translation>Helyi tisztítás</translation>
    </message>
    <message>
        <source>Cloud Sync</source>
        <translation>Felhő szinkronizálás</translation>
    </message>
    <message>
        <source>Waiting for cleanup to complete…</source>
        <translation>Várakozás a tisztítás befejezésére…</translation>
    </message>
    <message>
        <source>▶ Show Log</source>
        <translation>▶ Napló megjelenítése</translation>
    </message>
    <message>
        <source>▼ Hide Log</source>
        <translation>▼ Napló elrejtése</translation>
    </message>
    <message>
        <source>Minimize to Tray</source>
        <translation>Kicsinyítés a tálcára</translation>
    </message>
    <message>
        <source>Done</source>
        <translation>Kész</translation>
    </message>
    <message>
        <source>Syncing…</source>
        <translation>Szinkronizálás…</translation>
    </message>
    <message>
        <source>Complete</source>
        <translation>Befejezve</translation>
    </message>
    <message>
        <source>Execution complete — {0} deleted, {1} errors</source>
        <translation>Végrehajtás kész — {0} törölve, {1} hiba</translation>
    </message>
    <message>
        <source>Execution complete — {0} files deleted</source>
        <translation>Végrehajtás kész — {0} fájl törölve</translation>
    </message>
    <message>
        <source>{0} / {1} files — {2}</source>
        <translation>{0} / {1} fájl — {2}</translation>
    </message>
    <message>
        <source>{0} / {1} files</source>
        <translation>{0} / {1} fájl</translation>
    </message>
    <message>
        <source>~{0} left</source>
        <translation>~{0} van hátra</translation>
    </message>
    <message>
        <source>{0}s</source>
        <translation>{0}mp</translation>
    </message>
    <message>
        <source>{0}m {1}s</source>
        <translation>{0}p {1}mp</translation>
    </message>
    <message>
        <source>{0}h {1}m</source>
        <translation>{0}ó {1}p</translation>
    </message>
    <message>
        <source>{0}d {1}h</source>
        <translation>{0}n {1}ó</translation>
    </message>
    <!-- Data Compression substage messages (§5.1) -->
    <message>
        <source>Compressing database…</source>
        <translation>Adatbázis tömörítése…</translation>
    </message>
    <message>
        <source>Compressed {0} → {1} ({2}% reduction)</source>
        <translation>Tömörítve {0} → {1} ({2}% csökkenés)</translation>
    </message>
    <message>
        <source>Uploading compressed data…</source>
        <translation>Tömörített adatok feltöltése…</translation>
    </message>
    <message>
        <source>Upload skipped — data unchanged</source>
        <translation>Feltöltés kihagyva — az adatok nem változtak</translation>
    </message>
    <message>
        <source>Downloading peer data: {0}…</source>
        <translation>Partner adatainak letöltése: {0}…</translation>
    </message>
    <message>
        <source>Decompressing peer data: {0}…</source>
        <translation>Partner adatainak kicsomagolása: {0}…</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Phase 5: FilterSidebar (ui/filter_sidebar.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>FilterSidebar</name>
    <message>
        <source>⚙ Filters</source>
        <translation>⚙ Szűrők</translation>
    </message>
    <message>
        <source>Date Range</source>
        <translation>Dátumtartomány</translation>
    </message>
    <message>
        <source>From:</source>
        <translation>Ettől:</translation>
    </message>
    <message>
        <source>To:</source>
        <translation>Eddig:</translation>
    </message>
    <message>
        <source>Any</source>
        <translation>Bármikor</translation>
    </message>
    <message>
        <source>Enable date filter</source>
        <translation>Dátumszűrő engedélyezése</translation>
    </message>
    <message>
        <source>File Type</source>
        <translation>Fájltípus</translation>
    </message>
    <message>
        <source>Redundancy</source>
        <translation>Redundancia</translation>
    </message>
    <message>
        <source>Min copies:</source>
        <translation>Min. példányszám:</translation>
    </message>
    <message>
        <source>Full duplicate folders only</source>
        <translation>Csak teljesen duplikált mappák</translation>
    </message>
    <message>
        <source>Show only folders where every file is a duplicate</source>
        <translation>Csak olyan mappák megjelenítése, ahol minden fájl duplikátum</translation>
    </message>
    <message>
        <source>Sort By</source>
        <translation>Rendezés</translation>
    </message>
    <message>
        <source>Waste (total size)</source>
        <translation>Pazarlás (összes méret)</translation>
    </message>
    <message>
        <source>Number of copies</source>
        <translation>Példányszám</translation>
    </message>
    <message>
        <source>Path length</source>
        <translation>Elérési út hossza</translation>
    </message>
    <message>
        <source>Apply</source>
        <translation>Alkalmaz</translation>
    </message>
    <message>
        <source>Reset</source>
        <translation>Visszaállítás</translation>
    </message>
    <message>
        <source>Similarity Threshold</source>
        <translation>Hasonlósági küszöb</translation>
    </message>
    <message>
        <source>Lower = stricter matching</source>
        <translation>Alacsonyabb = szigorúbb egyezés</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Phase 5: ClusterModel (ui/cluster_model.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>ClusterModel</name>
    <message>
        <source>Name</source>
        <translation>Név</translation>
    </message>
    <message>
        <source>Copies</source>
        <translation>Példányok</translation>
    </message>
    <message>
        <source>Size</source>
        <translation>Méret</translation>
    </message>
    <message>
        <source>Modified</source>
        <translation>Módosítva</translation>
    </message>
    <message>
        <source>{0} copies · {1} total</source>
        <translation>{0} példány · {1} összesen</translation>
    </message>
    <message>
        <source>★ Master Copy</source>
        <translation>★ Mesterpéldány</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Phase 5: BatchActions (ui/batch_actions.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>BatchActions</name>
    <message>
        <source>✨ Smart Select</source>
        <translation>✨ Intelligens kiválasztás</translation>
    </message>
    <message>
        <source>Apply a selection preset to all duplicate groups</source>
        <translation>Kiválasztási szabály alkalmazása minden duplikátum csoportra</translation>
    </message>
    <message>
        <source>✱ Select by Pattern</source>
        <translation>✱ Kiválasztás mintával</translation>
    </message>
    <message>
        <source>Mark files matching a pattern for deletion</source>
        <translation>Mintának megfelelő fájlok törlésre jelölése</translation>
    </message>
    <message>
        <source>Keep Largest File</source>
        <translation>Legnagyobb fájl megtartása</translation>
    </message>
    <message>
        <source>Keep Newest</source>
        <translation>Legújabb megtartása</translation>
    </message>
    <message>
        <source>Keep Deepest Path</source>
        <translation>Legmélyebb útvonal megtartása</translation>
    </message>
    <message>
        <source>Keep Shortest Path</source>
        <translation>Legrövidebb útvonal megtartása</translation>
    </message>
    <message>
        <source>Smart Select</source>
        <translation>Intelligens kiválasztás</translation>
    </message>
    <message>
        <source>Choose a selection rule:</source>
        <translation>Válasszon kiválasztási szabályt:</translation>
    </message>
    <message>
        <source>Confirm Smart Select</source>
        <translation>Intelligens kiválasztás megerősítése</translation>
    </message>
    <message>
        <source>Apply "{0}" to all duplicate groups?

This will mark files for keep/delete.
Existing decisions will be overwritten.</source>
        <translation>Alkalmazza a(z) „{0}" szabályt minden duplikátum csoportra?

Ez megtartásra/törlésre jelöli a fájlokat.
A meglévő döntések felülíródnak.</translation>
    </message>
    <message>
        <source>Select by Pattern</source>
        <translation>Kiválasztás mintával</translation>
    </message>
    <message>
        <source>Enter a filename pattern (e.g. *_copy*, *(1)*):
Files matching this pattern will be marked for deletion.</source>
        <translation>Adjon meg egy fájlnév-mintát (pl. *_copy*, *(1)*):
A mintának megfelelő fájlok törlésre lesznek jelölve.</translation>
    </message>
    <message>
        <source>No Matches</source>
        <translation>Nincs találat</translation>
    </message>
    <message>
        <source>No duplicate files matched the pattern "{0}".</source>
        <translation>Egyetlen duplikált fájl sem felelt meg a(z) „{0}" mintának.</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Phase 4: FamilyDiscoveryScreen (ui/family_discovery.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>FamilyDiscoveryScreen</name>
    <message>
        <source>← Dashboard</source>
        <translation>← Kezdőlap</translation>
    </message>
    <message>
        <source>Family Photos</source>
        <translation>Családi fotók</translation>
    </message>
    <message>
        <source>Request Selected (0)</source>
        <translation>Kijelöltek kérése (0)</translation>
    </message>
    <message>
        <source>Request Selected ({0})</source>
        <translation>Kijelöltek kérése ({0})</translation>
    </message>
    <message>
        <source>Filter:</source>
        <translation>Szűrő:</translation>
    </message>
    <message>
        <source>All Providers</source>
        <translation>Összes szolgáltató</translation>
    </message>
    <message>
        <source>All</source>
        <translation>Összes</translation>
    </message>
    <message>
        <source>Not Requested</source>
        <translation>Nem kért</translation>
    </message>
    <message>
        <source>Requested</source>
        <translation>Kért</translation>
    </message>
    <message>
        <source>Showing {0} family photos from {1} providers</source>
        <translation>{0} családi fotó megjelenítése {1} szolgáltatótól</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Similar Image Detection: SimilarityScreen (ui/similarity_screen.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>SimilarityScreen</name>
    <message>
        <source>&#x2190; Back</source>
        <translation>&#x2190; Vissza</translation>
    </message>
    <message>
        <source>Similar Images</source>
        <translation>Hasonló képek</translation>
    </message>
    <message>
        <source>Smart Select</source>
        <translation>Okos kijelölés</translation>
    </message>
    <message>
        <source>Apply a preset to select files to keep/delete</source>
        <translation>Előbeállítás alkalmazása a megtartandó/törlendő fájlok kijelöléséhez</translation>
    </message>
    <message>
        <source>{0} groups &#x00b7; {1} files</source>
        <translation>{0} csoport &#x00b7; {1} fájl</translation>
    </message>
    <message>
        <source>Review Plan &#x00bb;</source>
        <translation>Terv áttekintése &#x00bb;</translation>
    </message>
    <message>
        <source>Recommendation: Keep {0} ({1})</source>
        <translation>Javaslat: {0} megtartása ({1})</translation>
    </message>
    <message>
        <source>Marked file {0} to keep</source>
        <translation>{0}. fájl megtartásra jelölve</translation>
    </message>
    <message>
        <source>Marked file {0} for deletion</source>
        <translation>{0}. fájl törlésre jelölve</translation>
    </message>
    <message>
        <source>Keep Highest Resolution</source>
        <translation>Legnagyobb felbontás megtartása</translation>
    </message>
    <message>
        <source>Keep Largest File</source>
        <translation>Legnagyobb fájl megtartása</translation>
    </message>
    <message>
        <source>Keep Newest</source>
        <translation>Legújabb megtartása</translation>
    </message>
    <message>
        <source>Keep Oldest</source>
        <translation>Legrégebbi megtartása</translation>
    </message>
    <message>
        <source>Keep Shortest Path</source>
        <translation>Legrövidebb elérési út megtartása</translation>
    </message>
    <message>
        <source>Choose which file to keep in each group:</source>
        <translation>Válassza ki, melyik fájlt tartsa meg minden csoportban:</translation>
    </message>
    <message>
        <source>Smart Select: {0} keep, {1} delete</source>
        <translation>Okos kijelölés: {0} megtartás, {1} törlés</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Similar Image Detection: SimilarityComparePanel (ui/similarity_compare.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>SimilarityComparePanel</name>
    <message>
        <source>No preview</source>
        <translation>Nincs előnézet</translation>
    </message>
    <message>
        <source>&#x2605; RECOMMENDED</source>
        <translation>&#x2605; AJÁNLOTT</translation>
    </message>
    <message>
        <source>distance: {0}</source>
        <translation>távolság: {0}</translation>
    </message>
    <message>
        <source>Keep</source>
        <translation>Megtartás</translation>
    </message>
    <message>
        <source>Delete</source>
        <translation>Törlés</translation>
    </message>
    <message>
        <source>Select a similarity group to compare</source>
        <translation>Válasszon hasonlósági csoportot az összehasonlításhoz</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     Similar Image Detection: SimilarityModel (ui/similarity_model.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>SimilarityModel</name>
    <message>
        <source>Name</source>
        <translation>Név</translation>
    </message>
    <message>
        <source>Members</source>
        <translation>Tagok</translation>
    </message>
    <message>
        <source>Resolution</source>
        <translation>Felbontás</translation>
    </message>
    <message>
        <source>Size</source>
        <translation>Méret</translation>
    </message>
    <message>
        <source>Distance</source>
        <translation>Távolság</translation>
    </message>
    <message>
        <source>max {0}</source>
        <translation>max {0}</translation>
    </message>
    <message>
        <source>{0} similar files &#x00b7; {1} total</source>
        <translation>{0} hasonló fájl &#x00b7; összesen {1}</translation>
    </message>
    <message>
        <source>&#x2605; Recommended</source>
        <translation>&#x2605; Ajánlott</translation>
    </message>
</context>
</TS>
