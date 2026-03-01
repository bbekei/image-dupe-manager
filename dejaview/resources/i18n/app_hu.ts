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
        <source>Google sign-in failed.</source>
        <translation>A Google bejelentkezés sikertelen.</translation>
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
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     FolderPanel (ui/folder_panel.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>FolderPanel</name>
    <message>
        <source>Scan Folders</source>
        <translation>Vizsgálandó mappák</translation>
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
        <source>{0} / {1}</source>
        <translation>{0} / {1}</translation>
    </message>
    <message>
        <source>{0} / {1} — {2}</source>
        <translation>{0} / {1} — {2}</translation>
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
        <source>Name</source>
        <translation>Név</translation>
    </message>
    <message>
        <source>Status</source>
        <translation>Állapot</translation>
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
        <source>Pass 1: Discovering files…</source>
        <translation>1. lépés: Fájlok keresése…</translation>
    </message>
    <message>
        <source>Pass 1: Discovering files…  ({0} found)</source>
        <translation>1. lépés: Fájlok keresése…  ({0} találat)</translation>
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
        <source>{0} / {1} files — {2}</source>
        <translation>{0} / {1} fájl — {2}</translation>
    </message>
    <message>
        <source>{0} / {1} files</source>
        <translation>{0} / {1} fájl</translation>
    </message>
    <message>
        <source>Pass 1: Discovery ✓</source>
        <translation>1. lépés: Keresés ✓</translation>
    </message>
    <message>
        <source>Pass 1: Discovery ✓  ({0} files)</source>
        <translation>1. lépés: Keresés ✓  ({0} fájl)</translation>
    </message>
    <message>
        <source>Pass 2: Hashing…  ({0} / {1})</source>
        <translation>2. lépés: Hashelés…  ({0} / {1})</translation>
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
</TS>
