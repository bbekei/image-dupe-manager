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
        <source>View</source>
        <translation>Nézet</translation>
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
        <source>KEEP</source>
        <translation>MEGTARTÁS</translation>
    </message>
    <message>
        <source>DEL</source>
        <translation>TÖRLÉS</translation>
    </message>
    <message>
        <source>Rename</source>
        <translation>Átnevezés</translation>
    </message>
    <message>
        <source>New filename…</source>
        <translation>Új fájlnév…</translation>
    </message>
    <message>
        <source>({0}&apos;s copy)</source>
        <translation>({0} másolata)</translation>
    </message>
    <message>
        <source>(read only)</source>
        <translation>(csak olvasható)</translation>
    </message>
    <message>
        <source>Invalid filename</source>
        <translation>Érvénytelen fájlnév</translation>
    </message>
    <message>
        <source>The filename is invalid. Use a simple name without path separators.</source>
        <translation>A fájlnév érvénytelen. Használjon egyszerű nevet elérési út nélkül.</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     _BatchRulesDialog (ui/compare_view.py — batch rules modal)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>_BatchRulesDialog</name>
    <message>
        <source>Batch Rules</source>
        <translation>Kötegelt szabályok</translation>
    </message>
    <message>
        <source>Apply an automatic rule to this group:</source>
        <translation>Automatikus szabály alkalmazása a csoportra:</translation>
    </message>
    <message>
        <source>Keep oldest, delete rest</source>
        <translation>Legrégebbi megtartása, többi törlése</translation>
    </message>
    <message>
        <source>Keep largest, delete rest</source>
        <translation>Legnagyobb megtartása, többi törlése</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>Mégse</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     _ConfirmDialog (ui/compare_view.py — confirmation modal)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>_ConfirmDialog</name>
    <message>
        <source>Confirm Actions</source>
        <translation>Műveletek megerősítése</translation>
    </message>
    <message>
        <source>The following actions will be performed:</source>
        <translation>A következő műveletek lesznek végrehajtva:</translation>
    </message>
    <message>
        <source>DELETE: {0}</source>
        <translation>TÖRLÉS: {0}</translation>
    </message>
    <message>
        <source>RENAME: {0} → {1}</source>
        <translation>ÁTNEVEZÉS: {0} → {1}</translation>
    </message>
    <message>
        <source>KEEP: {0}</source>
        <translation>MEGTARTÁS: {0}</translation>
    </message>
</context>

<!-- ═══════════════════════════════════════════════════════════════════════════
     CompareView (ui/compare_view.py — main comparison widget)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>CompareView</name>
    <message>
        <source>Apply to all in group</source>
        <translation>Alkalmazás a csoport minden elemére</translation>
    </message>
    <message>
        <source>Batch rules…</source>
        <translation>Kötegelt szabályok…</translation>
    </message>
    <message>
        <source>Review &amp;&amp; Confirm…</source>
        <translation>Áttekintés és megerősítés…</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Bezárás</translation>
    </message>
    <message>
        <source>DUPLICATE GROUP ({0} files · SHA: {1}…)</source>
        <translation>DUPLIKÁTUM CSOPORT ({0} fájl · SHA: {1}…)</translation>
    </message>
    <message>
        <source>No actions</source>
        <translation>Nincs művelet</translation>
    </message>
    <message>
        <source>No actions have been staged yet.</source>
        <translation>Még nincsenek előkészített műveletek.</translation>
    </message>
    <message>
        <source>Path outside scan scope: {0}</source>
        <translation>Az elérési út a vizsgálati hatókörön kívül esik: {0}</translation>
    </message>
    <message>
        <source>Invalid rename target: {0}</source>
        <translation>Érvénytelen átnevezési cél: {0}</translation>
    </message>
    <message>
        <source>Some actions failed</source>
        <translation>Egyes műveletek sikertelenek</translation>
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
</TS>
