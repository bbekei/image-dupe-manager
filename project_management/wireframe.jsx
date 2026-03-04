import { useState, useEffect, useRef, useCallback } from "react";

// ─── Mock Data ───────────────────────────────────────────────────────────
const generateMockGroups = (count) => {
  const locations = ["Beach Vacation", "Birthday Party", "Christmas 2024", "Hiking Trip", "Wedding", "Graduation", "Concert", "City Walk", "Sunset", "Family Dinner", "Park Day", "Road Trip"];
  const folders = ["Camera Roll", "Downloads", "WhatsApp Images", "Screenshots", "Google Photos Backup", "iCloud Sync"];
  return Array.from({ length: count }, (_, i) => ({
    id: `group-${i}`,
    label: locations[i % locations.length] + ` #${Math.floor(i / locations.length) + 1}`,
    photos: Array.from({ length: 2 + Math.floor(Math.random() * 3) }, (_, j) => ({
      id: `photo-${i}-${j}`,
      thumbnail: `https://picsum.photos/seed/${i * 10 + j}/400/400`,
      filename: `IMG_${2000 + i * 10 + j}.jpg`,
      folder: folders[Math.floor(Math.random() * folders.length)],
      resolution: j === 0 ? "4032 × 3024" : j === 1 ? "3024 × 3024" : "2048 × 1536",
      fileSize: j === 0 ? "4.2 MB" : j === 1 ? "3.8 MB" : "1.9 MB",
      date: `2024-${String(1 + (i % 12)).padStart(2, "0")}-${String(1 + ((i + j * 3) % 28)).padStart(2, "0")}`,
      isRecommended: j === 0,
    })),
    resolved: false,
    keptPhotoId: null,
  }));
};

const mockFamilyMembers = [
  { id: "me", name: "You", avatar: "Y", color: "#6366f1" },
  { id: "sarah", name: "Sarah", avatar: "S", color: "#ec4899" },
  { id: "mike", name: "Mike", avatar: "M", color: "#14b8a6" },
];

const generateFamilyDuplicates = () => [
  {
    id: "fam-1",
    label: "Beach Sunset, July 2024",
    mine: { filename: "IMG_4021.jpg", resolution: "4032 × 3024", fileSize: "3.2 MB", note: "Edited", thumbnail: `https://picsum.photos/seed/f1a/400/400` },
    theirs: { owner: mockFamilyMembers[1], filename: "IMG_8844.jpg", resolution: "4032 × 3024", fileSize: "4.1 MB", note: "Original", thumbnail: `https://picsum.photos/seed/f1b/400/400` },
  },
  {
    id: "fam-2",
    label: "Christmas Morning",
    mine: { filename: "IMG_5102.jpg", resolution: "3024 × 3024", fileSize: "2.8 MB", note: "Cropped", thumbnail: `https://picsum.photos/seed/f2a/400/400` },
    theirs: { owner: mockFamilyMembers[1], filename: "IMG_9001.jpg", resolution: "4032 × 3024", fileSize: "5.1 MB", note: "Original", thumbnail: `https://picsum.photos/seed/f2b/400/400` },
  },
  {
    id: "fam-3",
    label: "Graduation Ceremony",
    mine: { filename: "IMG_6200.jpg", resolution: "4032 × 3024", fileSize: "4.8 MB", note: "Original", thumbnail: `https://picsum.photos/seed/f3a/400/400` },
    theirs: { owner: mockFamilyMembers[2], filename: "DCIM_0442.jpg", resolution: "2048 × 1536", fileSize: "1.9 MB", note: "Compressed", thumbnail: `https://picsum.photos/seed/f3b/400/400` },
  },
];

const generateIncomingRequests = () => [
  { id: "req-1", from: mockFamilyMembers[1], type: "request_copy", photo: { filename: "IMG_6200.jpg", label: "Graduation Ceremony", thumbnail: `https://picsum.photos/seed/f3a/400/400` }, message: "Your version is much better quality — can I have a copy?", date: "2 hours ago" },
  { id: "req-2", from: mockFamilyMembers[2], type: "offer_copy", photo: { filename: "DCIM_1100.jpg", label: "Road Trip Panorama", thumbnail: `https://picsum.photos/seed/offer1/400/400` }, message: "I have a higher-res version of this one. Want it?", date: "Yesterday" },
  { id: "req-3", from: mockFamilyMembers[1], type: "suggest_consolidate", photo: { filename: "IMG_4021.jpg", label: "Beach Sunset", thumbnail: `https://picsum.photos/seed/f1a/400/400` }, message: "We both have this — want to keep just one copy in your library?", date: "3 days ago" },
];

// ─── Wireframe Styles ────────────────────────────────────────────────────
const colors = {
  bg: "#f5f5f0",
  surface: "#ffffff",
  surfaceAlt: "#fafaf7",
  border: "#e2e0db",
  borderLight: "#eeede8",
  text: "#1a1a18",
  textMuted: "#6b6963",
  textLight: "#9b9790",
  accent: "#2563eb",
  accentLight: "#dbeafe",
  accentSubtle: "#eff6ff",
  green: "#16a34a",
  greenLight: "#dcfce7",
  red: "#dc2626",
  redLight: "#fee2e2",
  orange: "#ea580c",
  orangeLight: "#fff7ed",
  purple: "#7c3aed",
  purpleLight: "#ede9fe",
};

// ─── Shared Components ───────────────────────────────────────────────────
const WireframeLabel = ({ children }) => (
  <div style={{ position: "absolute", top: -10, left: 12, background: colors.accent, color: "#fff", fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 3, letterSpacing: "0.05em", textTransform: "uppercase", zIndex: 10 }}>
    {children}
  </div>
);

const Badge = ({ children, color = colors.textMuted, bg = colors.surfaceAlt }) => (
  <span style={{ display: "inline-block", fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 10, background: bg, color, letterSpacing: "0.01em" }}>{children}</span>
);

const Button = ({ children, variant = "default", size = "md", onClick, style = {}, disabled = false }) => {
  const base = { border: "none", cursor: disabled ? "default" : "pointer", fontFamily: "inherit", fontWeight: 500, borderRadius: 6, transition: "all 0.15s", opacity: disabled ? 0.4 : 1, display: "inline-flex", alignItems: "center", gap: 6 };
  const sizes = { sm: { fontSize: 12, padding: "5px 12px" }, md: { fontSize: 13, padding: "7px 16px" }, lg: { fontSize: 14, padding: "10px 24px" } };
  const variants = {
    default: { background: colors.surface, color: colors.text, border: `1px solid ${colors.border}` },
    primary: { background: colors.accent, color: "#fff" },
    danger: { background: colors.red, color: "#fff" },
    success: { background: colors.green, color: "#fff" },
    ghost: { background: "transparent", color: colors.textMuted, padding: sizes[size].padding },
  };
  return <button onClick={disabled ? undefined : onClick} style={{ ...base, ...sizes[size], ...variants[variant], ...style }}>{children}</button>;
};

const PhotoThumb = ({ src, size = 120, selected = false, recommended = false, onClick, style = {} }) => (
  <div onClick={onClick} style={{ width: size, height: size, borderRadius: 8, overflow: "hidden", border: selected ? `3px solid ${colors.accent}` : `1px solid ${colors.border}`, cursor: onClick ? "pointer" : "default", position: "relative", flexShrink: 0, transition: "border 0.15s", ...style }}>
    <img src={src} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
    {recommended && (
      <div style={{ position: "absolute", top: 6, left: 6, background: colors.green, color: "#fff", fontSize: 9, fontWeight: 600, padding: "2px 6px", borderRadius: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>Best</div>
    )}
    {selected && (
      <div style={{ position: "absolute", inset: 0, background: "rgba(37,99,235,0.12)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 28, height: 28, borderRadius: 14, background: colors.accent, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 700 }}>✓</div>
      </div>
    )}
  </div>
);

const MetaRow = ({ label, value }) => (
  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0" }}>
    <span style={{ color: colors.textLight }}>{label}</span>
    <span style={{ color: colors.text, fontWeight: 500 }}>{value}</span>
  </div>
);

const SectionHeader = ({ title, subtitle, right }) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: colors.text, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>{title}</h2>
      {subtitle && <p style={{ fontSize: 13, color: colors.textMuted, margin: "4px 0 0" }}>{subtitle}</p>}
    </div>
    {right && <div>{right}</div>}
  </div>
);

// ─── Screen: Scan Results Dashboard ──────────────────────────────────────
const DashboardScreen = ({ groups, onStartReview, onAutoResolve, onGoToFamily }) => {
  const totalPhotos = groups.reduce((a, g) => a + g.photos.length, 0);
  const totalSize = (totalPhotos * 3.1).toFixed(1);
  const stats = [
    { label: "Duplicate Groups", value: groups.length, icon: "◫" },
    { label: "Total Duplicates", value: totalPhotos, icon: "⊞" },
    { label: "Recoverable Space", value: `${totalSize} GB`, icon: "◉" },
  ];

  return (
    <div>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <div style={{ fontSize: 48, marginBottom: 8 }}>✓</div>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: colors.text, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>Scan Complete</h1>
        <p style={{ fontSize: 14, color: colors.textMuted, marginTop: 6 }}>Your photo library has been analyzed</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 32 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ background: colors.surface, border: `1px solid ${colors.border}`, borderRadius: 10, padding: 20, textAlign: "center" }}>
            <div style={{ fontSize: 28, marginBottom: 4 }}>{s.icon}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: colors.text, fontFamily: "'DM Sans', sans-serif" }}>{s.value}</div>
            <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div onClick={onStartReview} style={{ background: colors.accent, color: "#fff", borderRadius: 10, padding: "16px 20px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Review All Groups</div>
            <div style={{ fontSize: 12, opacity: 0.8, marginTop: 2 }}>Go through each group and choose what to keep</div>
          </div>
          <div style={{ fontSize: 22 }}>→</div>
        </div>

        <div onClick={onAutoResolve} style={{ background: colors.surface, border: `1px solid ${colors.border}`, borderRadius: 10, padding: "16px 20px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: colors.text }}>Auto-Resolve Exact Matches</div>
            <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>Keep highest quality version automatically for all groups</div>
          </div>
          <div style={{ fontSize: 22, color: colors.textMuted }}>→</div>
        </div>

        <div onClick={onGoToFamily} style={{ background: colors.purpleLight, border: `1px solid ${colors.purple}22`, borderRadius: 10, padding: "16px 20px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: colors.purple }}>Cross-Family Scan</div>
            <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>Check for duplicates across family members' libraries</div>
          </div>
          <div style={{ fontSize: 22, color: colors.purple }}>→</div>
        </div>
      </div>
    </div>
  );
};

// ─── Screen: Group Review ────────────────────────────────────────────────
const GroupReviewScreen = ({ groups, onBack, onFinish }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedPhotos, setSelectedPhotos] = useState({});
  const [resolvedGroups, setResolvedGroups] = useState(new Set());

  const group = groups[currentIndex];
  const selected = selectedPhotos[group.id] || group.photos[0].id;
  const progress = resolvedGroups.size;

  const handleKeep = () => {
    setResolvedGroups((prev) => new Set(prev).add(group.id));
    if (currentIndex < groups.length - 1) setCurrentIndex(currentIndex + 1);
  };
  const handleKeepAll = () => {
    setResolvedGroups((prev) => new Set(prev).add(group.id));
    if (currentIndex < groups.length - 1) setCurrentIndex(currentIndex + 1);
  };
  const handleSelect = (photoId) => setSelectedPhotos((prev) => ({ ...prev, [group.id]: photoId }));

  return (
    <div>
      {/* Progress bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <div style={{ flex: 1, height: 4, background: colors.borderLight, borderRadius: 2, overflow: "hidden" }}>
          <div style={{ width: `${(progress / groups.length) * 100}%`, height: "100%", background: colors.accent, borderRadius: 2, transition: "width 0.3s" }} />
        </div>
        <span style={{ fontSize: 12, color: colors.textMuted, fontWeight: 600, whiteSpace: "nowrap" }}>{progress} / {groups.length}</span>
      </div>

      {/* Group nav */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: colors.text, fontFamily: "'DM Sans', sans-serif" }}>{group.label}</h2>
          <p style={{ fontSize: 12, color: colors.textMuted, margin: "2px 0 0" }}>{group.photos.length} copies found</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Button size="sm" disabled={currentIndex === 0} onClick={() => setCurrentIndex(currentIndex - 1)}>←</Button>
          <Button size="sm" disabled={currentIndex === groups.length - 1} onClick={() => setCurrentIndex(currentIndex + 1)}>→</Button>
        </div>
      </div>

      {/* Photo comparison */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, overflowX: "auto", paddingBottom: 8 }}>
        {group.photos.map((photo) => (
          <div key={photo.id} style={{ minWidth: 180 }}>
            <PhotoThumb
              src={photo.thumbnail}
              size={180}
              selected={selected === photo.id}
              recommended={photo.isRecommended}
              onClick={() => handleSelect(photo.id)}
            />
            <div style={{ marginTop: 10, padding: "0 2px" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: colors.text, marginBottom: 6 }}>{photo.filename}</div>
              <MetaRow label="Folder" value={photo.folder} />
              <MetaRow label="Resolution" value={photo.resolution} />
              <MetaRow label="Size" value={photo.fileSize} />
              <MetaRow label="Date" value={photo.date} />
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 10, padding: "16px 0", borderTop: `1px solid ${colors.borderLight}` }}>
        <Button variant="primary" size="lg" onClick={handleKeep} style={{ flex: 1 }}>
          Keep Selected — Delete {group.photos.length - 1} Other{group.photos.length > 2 ? "s" : ""}
        </Button>
        <Button variant="default" size="lg" onClick={handleKeepAll}>Keep All</Button>
      </div>

      {progress === groups.length && (
        <div style={{ marginTop: 20, padding: 16, background: colors.greenLight, borderRadius: 8, textAlign: "center" }}>
          <div style={{ fontWeight: 700, color: colors.green, marginBottom: 6 }}>All groups reviewed!</div>
          <Button variant="success" size="lg" onClick={onFinish}>Apply Changes</Button>
        </div>
      )}
    </div>
  );
};

// ─── Screen: Duplicates Bin ──────────────────────────────────────────────
const DuplicatesBinScreen = ({ onBack }) => {
  const [items, setItems] = useState([
    { id: 1, filename: "IMG_2010.jpg", deletedFrom: "Camera Roll", date: "Mar 1, 2026", size: "3.8 MB", thumbnail: `https://picsum.photos/seed/bin1/400/400` },
    { id: 2, filename: "IMG_2011.jpg", deletedFrom: "Downloads", date: "Mar 1, 2026", size: "1.9 MB", thumbnail: `https://picsum.photos/seed/bin2/400/400` },
    { id: 3, filename: "IMG_2050.jpg", deletedFrom: "WhatsApp Images", date: "Feb 28, 2026", size: "4.2 MB", thumbnail: `https://picsum.photos/seed/bin3/400/400` },
    { id: 4, filename: "IMG_2055.jpg", deletedFrom: "Google Photos Backup", date: "Feb 28, 2026", size: "2.1 MB", thumbnail: `https://picsum.photos/seed/bin4/400/400` },
  ]);

  const handleRestore = (id) => setItems(items.filter((i) => i.id !== id));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>Duplicates Bin</h2>
      </div>

      <div style={{ background: colors.orangeLight, border: `1px solid ${colors.orange}22`, borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontSize: 13, color: colors.orange, display: "flex", gap: 10, alignItems: "center" }}>
        <span style={{ fontSize: 18 }}>⏱</span>
        <span>Items are permanently deleted after <strong>30 days</strong>. Restore any photo to return it to its original location.</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((item) => (
          <div key={item.id} style={{ display: "flex", gap: 14, alignItems: "center", background: colors.surface, border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12 }}>
            <PhotoThumb src={item.thumbnail} size={56} style={{ borderRadius: 6 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{item.filename}</div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>From: {item.deletedFrom} · {item.size} · Deleted {item.date}</div>
            </div>
            <Button size="sm" onClick={() => handleRestore(item.id)}>Restore</Button>
          </div>
        ))}
      </div>

      {items.length > 0 && (
        <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end" }}>
          <Button variant="danger" size="sm" onClick={() => setItems([])}>Permanently Delete All</Button>
        </div>
      )}
      {items.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: colors.textLight, fontSize: 14 }}>Bin is empty</div>
      )}
    </div>
  );
};

// ─── Screen: Family Cross-Library ────────────────────────────────────────
const FamilyCrossLibraryScreen = ({ onBack, onGoToRequests }) => {
  const familyDups = generateFamilyDuplicates();
  const [actions, setActions] = useState({});

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>Cross-Family Duplicates</h2>
          <p style={{ fontSize: 12, color: colors.textMuted, margin: "2px 0 0" }}>{familyDups.length} matches found across family libraries</p>
        </div>
        <Button size="sm" onClick={onGoToRequests} style={{ background: colors.purpleLight, color: colors.purple, border: "none" }}>
          Requests Inbox (3)
        </Button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {familyDups.map((dup) => (
          <div key={dup.id} style={{ background: colors.surface, border: `1px solid ${colors.border}`, borderRadius: 10, padding: 20, position: "relative" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: colors.text, marginBottom: 14 }}>{dup.label}</div>

            <div style={{ display: "flex", gap: 20, marginBottom: 16 }}>
              {/* My version */}
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 24, height: 24, borderRadius: 12, background: mockFamilyMembers[0].color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>Y</div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: colors.text }}>Your Copy</span>
                  {dup.mine.note && <Badge>{dup.mine.note}</Badge>}
                </div>
                <PhotoThumb src={dup.mine.thumbnail} size={140} />
                <div style={{ marginTop: 8 }}>
                  <MetaRow label="Resolution" value={dup.mine.resolution} />
                  <MetaRow label="Size" value={dup.mine.fileSize} />
                </div>
              </div>

              {/* Divider */}
              <div style={{ width: 1, background: colors.borderLight, alignSelf: "stretch" }} />

              {/* Their version */}
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 24, height: 24, borderRadius: 12, background: dup.theirs.owner.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>{dup.theirs.owner.avatar}</div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: colors.text }}>{dup.theirs.owner.name}'s Copy</span>
                  {dup.theirs.note && <Badge>{dup.theirs.note}</Badge>}
                </div>
                <PhotoThumb src={dup.theirs.thumbnail} size={140} />
                <div style={{ marginTop: 8 }}>
                  <MetaRow label="Resolution" value={dup.theirs.resolution} />
                  <MetaRow label="Size" value={dup.theirs.fileSize} />
                </div>
              </div>
            </div>

            {/* Actions */}
            {actions[dup.id] ? (
              <div style={{ padding: "10px 14px", background: colors.greenLight, borderRadius: 6, fontSize: 13, color: colors.green, fontWeight: 500 }}>
                ✓ {actions[dup.id]}
              </div>
            ) : (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Button size="sm" variant="primary" onClick={() => setActions((p) => ({ ...p, [dup.id]: "Requested their copy" }))}>Request Their Copy</Button>
                <Button size="sm" onClick={() => setActions((p) => ({ ...p, [dup.id]: "Offered your copy" }))}>Offer Your Copy</Button>
                <Button size="sm" onClick={() => setActions((p) => ({ ...p, [dup.id]: "Suggested consolidation" }))}>Suggest Consolidation</Button>
                <Button size="sm" variant="ghost" onClick={() => setActions((p) => ({ ...p, [dup.id]: "Dismissed" }))}>Dismiss</Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Screen: Family Requests Inbox ───────────────────────────────────────
const FamilyRequestsScreen = ({ onBack }) => {
  const requests = generateIncomingRequests();
  const [handled, setHandled] = useState({});

  const typeLabels = {
    request_copy: { label: "Wants your photo", color: colors.accent, bg: colors.accentLight },
    offer_copy: { label: "Offering a photo", color: colors.green, bg: colors.greenLight },
    suggest_consolidate: { label: "Suggests consolidation", color: colors.purple, bg: colors.purpleLight },
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>Family Requests</h2>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {requests.map((req) => {
          const t = typeLabels[req.type];
          const done = handled[req.id];
          return (
            <div key={req.id} style={{ background: colors.surface, border: `1px solid ${colors.border}`, borderRadius: 10, padding: 16, opacity: done ? 0.5 : 1, transition: "opacity 0.3s" }}>
              <div style={{ display: "flex", gap: 14 }}>
                <PhotoThumb src={req.photo.thumbnail} size={72} />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 6 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <div style={{ width: 22, height: 22, borderRadius: 11, background: req.from.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>{req.from.avatar}</div>
                        <span style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{req.from.name}</span>
                        <Badge color={t.color} bg={t.bg}>{t.label}</Badge>
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{req.photo.label}</div>
                    </div>
                    <span style={{ fontSize: 11, color: colors.textLight }}>{req.date}</span>
                  </div>
                  <p style={{ fontSize: 12, color: colors.textMuted, margin: "4px 0 10px", lineHeight: 1.4 }}>"{req.message}"</p>

                  {done ? (
                    <div style={{ fontSize: 12, color: colors.green, fontWeight: 500 }}>✓ {done}</div>
                  ) : (
                    <div style={{ display: "flex", gap: 8 }}>
                      {req.type === "request_copy" && (
                        <>
                          <Button size="sm" variant="success" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Approved — photo shared" }))}>Approve & Share</Button>
                          <Button size="sm" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Declined" }))}>Decline</Button>
                        </>
                      )}
                      {req.type === "offer_copy" && (
                        <>
                          <Button size="sm" variant="primary" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Accepted — photo received" }))}>Accept</Button>
                          <Button size="sm" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Declined" }))}>No Thanks</Button>
                        </>
                      )}
                      {req.type === "suggest_consolidate" && (
                        <>
                          <Button size="sm" variant="primary" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Agreed — keeping in your library" }))}>Keep in My Library</Button>
                          <Button size="sm" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Agreed — keeping in their library" }))}>Keep in Theirs</Button>
                          <Button size="sm" variant="ghost" onClick={() => setHandled((p) => ({ ...p, [req.id]: "Dismissed" }))}>Dismiss</Button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── Screen: Auto-Resolve Confirmation ───────────────────────────────────
const AutoResolveScreen = ({ groups, onBack, onConfirm }) => {
  const totalRemoved = groups.reduce((a, g) => a + g.photos.length - 1, 0);
  const savedSpace = (totalRemoved * 3.1).toFixed(1);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, fontFamily: "'DM Sans', sans-serif" }}>Auto-Resolve Preview</h2>
      </div>

      <div style={{ background: colors.accentSubtle, border: `1px solid ${colors.accent}22`, borderRadius: 10, padding: 20, marginBottom: 24 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: colors.text, marginBottom: 8 }}>What will happen:</div>
        <div style={{ fontSize: 13, color: colors.textMuted, lineHeight: 1.6 }}>
          For each duplicate group, the <strong>highest resolution, largest file size</strong> version will be kept.
          All other copies will be moved to the Duplicates Bin (recoverable for 30 days).
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
          <div style={{ background: colors.surface, borderRadius: 8, padding: 14, textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: colors.text }}>{totalRemoved}</div>
            <div style={{ fontSize: 11, color: colors.textMuted }}>Photos to Bin</div>
          </div>
          <div style={{ background: colors.surface, borderRadius: 8, padding: 14, textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: colors.green }}>{savedSpace} GB</div>
            <div style={{ fontSize: 11, color: colors.textMuted }}>Space Recovered</div>
          </div>
        </div>
      </div>

      {/* Preview of first few groups */}
      <div style={{ fontSize: 13, fontWeight: 600, color: colors.text, marginBottom: 12 }}>Preview (first 3 groups):</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
        {groups.slice(0, 3).map((group) => (
          <div key={group.id} style={{ display: "flex", gap: 12, alignItems: "center", background: colors.surface, border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 10 }}>
            <PhotoThumb src={group.photos[0].thumbnail} size={48} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: colors.text }}>{group.label}</div>
              <div style={{ fontSize: 11, color: colors.textMuted }}>Keeping: {group.photos[0].filename} ({group.photos[0].resolution})</div>
            </div>
            <Badge color={colors.green} bg={colors.greenLight}>Keep 1 of {group.photos.length}</Badge>
          </div>
        ))}
        {groups.length > 3 && (
          <div style={{ textAlign: "center", fontSize: 12, color: colors.textLight, padding: 8 }}>
            + {groups.length - 3} more groups
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <Button variant="primary" size="lg" onClick={onConfirm} style={{ flex: 1 }}>Confirm Auto-Resolve</Button>
        <Button variant="default" size="lg" onClick={onBack}>Cancel</Button>
      </div>
    </div>
  );
};

// ─── Main App Shell ──────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: "◫" },
  { id: "review", label: "Review", icon: "⊞" },
  { id: "bin", label: "Bin", icon: "◌" },
  { id: "family", label: "Family", icon: "◈" },
  { id: "requests", label: "Requests", icon: "✉" },
];

export default function App() {
  const [screen, setScreen] = useState("dashboard");
  const [groups] = useState(() => generateMockGroups(24));

  const fonts = `@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');`;

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif", background: colors.bg, minHeight: "100vh", display: "flex" }}>
      <style>{fonts}</style>

      {/* Sidebar */}
      <div style={{ width: 220, background: colors.surface, borderRight: `1px solid ${colors.border}`, padding: "20px 0", display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "0 20px 20px", borderBottom: `1px solid ${colors.borderLight}` }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: colors.text, letterSpacing: "-0.02em" }}>PhotoDupe</div>
          <div style={{ fontSize: 11, color: colors.textLight, marginTop: 2 }}>Duplicate Manager</div>
        </div>

        <nav style={{ padding: "12px 10px", flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV_ITEMS.map((item) => (
            <div
              key={item.id}
              onClick={() => setScreen(item.id)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "9px 12px", borderRadius: 6, cursor: "pointer",
                background: screen === item.id ? colors.accentSubtle : "transparent",
                color: screen === item.id ? colors.accent : colors.textMuted,
                fontWeight: screen === item.id ? 600 : 400, fontSize: 13,
                transition: "all 0.15s",
              }}
            >
              <span style={{ fontSize: 16, width: 20, textAlign: "center" }}>{item.icon}</span>
              {item.label}
              {item.id === "requests" && (
                <span style={{ marginLeft: "auto", background: colors.red, color: "#fff", fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 8 }}>3</span>
              )}
            </div>
          ))}
        </nav>

        {/* Family members */}
        <div style={{ padding: "12px 20px", borderTop: `1px solid ${colors.borderLight}` }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: colors.textLight, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>Family Group</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {mockFamilyMembers.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 24, height: 24, borderRadius: 12, background: m.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>{m.avatar}</div>
                <span style={{ fontSize: 12, color: colors.text }}>{m.name}</span>
                <span style={{ width: 6, height: 6, borderRadius: 3, background: colors.green, marginLeft: "auto" }} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, padding: 32, maxWidth: 720, margin: "0 auto" }}>
        {/* Wireframe annotation */}
        <div style={{ position: "relative", marginBottom: 24, padding: "10px 14px 10px 14px", background: "#fffbe6", border: "1px dashed #d4a800", borderRadius: 6, fontSize: 11, color: "#8a7000" }}>
          <strong>WIREFRAME</strong> — {screen.charAt(0).toUpperCase() + screen.slice(1)} Screen · Click through to explore the user journey. All interactions are functional.
        </div>

        {screen === "dashboard" && (
          <DashboardScreen
            groups={groups}
            onStartReview={() => setScreen("review")}
            onAutoResolve={() => setScreen("auto-resolve")}
            onGoToFamily={() => setScreen("family")}
          />
        )}
        {screen === "review" && (
          <GroupReviewScreen groups={groups} onBack={() => setScreen("dashboard")} onFinish={() => setScreen("bin")} />
        )}
        {screen === "bin" && (
          <DuplicatesBinScreen onBack={() => setScreen("dashboard")} />
        )}
        {screen === "family" && (
          <FamilyCrossLibraryScreen onBack={() => setScreen("dashboard")} onGoToRequests={() => setScreen("requests")} />
        )}
        {screen === "requests" && (
          <FamilyRequestsScreen onBack={() => setScreen("family")} />
        )}
        {screen === "auto-resolve" && (
          <AutoResolveScreen groups={groups} onBack={() => setScreen("dashboard")} onConfirm={() => setScreen("bin")} />
        )}
      </div>
    </div>
  );
}
