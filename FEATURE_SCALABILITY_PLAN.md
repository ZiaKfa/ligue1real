# Rencana Skalabilitas Fitur — Futsal Sim

Dokumen ini fokus ke 6 fitur yang diminta: nama tim custom, aset gambar custom (bola/bendera/sprite pemain), adu penalti, atribut statistik pemain yang mempengaruhi simulasi, statistik gol & assist pemain di akhir pertandingan, dan fitur power-up (sengaja ditaruh di fase terakhir) — plus beberapa saran tambahan di §5. Ini dokumen terpisah dari [RL_SCALABILITY_PLAN.md](RL_SCALABILITY_PLAN.md) karena concern-nya beda (fitur gameplay/visual, bukan infrastruktur training AI).

---

## 0. Riwayat Versi

| Versi | Konteks | Perubahan |
|---|---|---|
| v1.0 | Draft awal | Review kondisi kode saat ini terhadap 4 fitur yang diminta, rencana per-fitur, saran tambahan. |
| v1.1 | Riset sumber data eksternal | Tambah tabel sumber data (SoFIFA/Kaggle, football-data.org, API-Football, TheSportsDB) di §4.D untuk ngisi roster/atribut pemain, dengan rekomendasi konkret mana yang dipakai untuk apa. |
| v1.2 (saat ini) | 2 fitur baru ditambahkan | Tambah §4.E (statistik gol & assist pemain di akhir pertandingan — promosi dari saran §5.4 jadi fitur formal) dan §4.F (power-up, sengaja ditaruh di fase paling akhir sesuai permintaan). Urutan prioritas §3 dan §7 diperbarui. |

---

## 1. Ringkasan Kondisi Saat Ini

Hasil audit langsung ke `sim/match.py`, `sim/scripted_ai.py`, dan `render/draw.py`:

### Identitas tim ("red"/"blue") — tercampur antara ID opaque dan hard-coded logic

String `"red"`/`"blue"` dipakai dengan 2 cara berbeda yang saat ini nyampur:
- **Sebagai key opaque** (aman digeneralisasi) — `self.score = {"red":0,"blue":0}`, `player["team"]`, `id: f"{team}_{i}"`. Semua akses lewat `dict[key]`/`.get()` berdasar nama, bukan asumsi urutan/isi tetap — jadi ini sebenarnya sudah siap diganti nama apa saja.
- **Sebagai hard comparison** (perlu diperbaiki) — ada di **5 titik terpisah**:
  - [sim/match.py:212](sim/match.py#L212) & [sim/match.py:260](sim/match.py#L260) & [sim/scripted_ai.py:31](sim/scripted_ai.py#L31) — `attack_dir = 1 if team == "red" else -1` (diduplikasi 3x)
  - [sim/match.py:317-319](sim/match.py#L317-L319) — gawang atas selalu di-hardcode "blue scores", gawang bawah selalu "red scores"
  - [sim/match.py:355](sim/match.py#L355) — `conceding_team = "blue" if ... == "red" else "red"`

  **Kabar baik**: setiap tempat ini punya pengganti langsung dari data yang SUDAH ada (`home_side`, bernilai -1/+1 per pemain) — `attack_dir` sebenarnya persis `-home_side` selalu, tidak perlu bandingkan string sama sekali. Perbaikannya murni substitusi, bukan desain ulang.

- **Render** — ✅ **sudah selesai** (di luar rencana ini, dikerjakan lebih dulu): warna tim tidak lagi hardcode `TEAM_RED`/`TEAM_BLUE`. `sim/config.py` punya `random_team_colors()` yang menghasilkan `match.team_colors[team]` (RGB) + `match.team_labels[team]` (nama warna, dari palet `(nama, hue)` yang sudah dipasangkan supaya label selalu cocok dengan warna sebenarnya) acak tiap match. `render/draw.py`, papan skor, dan event log commentary semua baca dari `match.team_colors`/`match.team_labels`, bukan konstanta tetap.

### Aset gambar — nol infrastruktur, semua prosedural

Grep menyeluruh ke `sim/` dan `render/` untuk `pygame.image.load`, `.png`, `.jpg`, `asset` — **tidak ada satupun**. Semua visual (pemain, bola, tiang, garis) digambar pakai `pygame.draw.circle`/`draw.line`/`draw.rect` dengan warna RGB dari `sim/config.py`. Menambah aset gambar berarti bikin infrastruktur loading dari nol, bukan modifikasi yang sudah ada.

### Adu penalti — belum ada konsep "match berakhir seri"

[render/preview.py:53](render/preview.py#L53) — satu-satunya syarat match berakhir adalah `while match.match_clock < MATCH_SECONDS:`, murni waktu, tidak ada pengecekan skor imbang sama sekali. Titik sambung yang tepat: persis setelah loop ini berakhir ([render/preview.py:82-84](render/preview.py#L82-L84)), sebelum `draw_final_score` dipanggil.

### Atribut pemain — semua pemain per role 100% identik

Semua konstanta perilaku (`CONTROL_CHANCE`, `STUN_CHANCE`, `KEEPER_SLIP_CHANCE`, `SHOT_POWER_MIN/MAX`, `SHOT_ANGLE_SPREAD`, `TACKLE_RADIUS`, speed) di-import sekali di level module dari `sim/config.py` dan dipakai sama rata untuk SEMUA pemain — tidak pernah dibaca dari dict per-pemain. Bahkan ada beberapa angka yang **belum jadi named constant sama sekali**:
- [sim/match.py:226](sim/match.py#L226) — peluang menang tackle `0.5` hardcoded literal
- [sim/match.py:282](sim/match.py#L282) — kekuatan passing `380` hardcoded literal
- [sim/scripted_ai.py:123](sim/scripted_ai.py#L123) — jarak lari FWD `220` hardcoded literal

**Kabar baik**: struktur dict pemain di [sim/match.py:152-159](sim/match.py#L152-L159) dibangun sekali per pemain dan semua konsumennya akses lewat nama key (bukan urutan/tuple) — nambah key baru (misal `"stats": {...}`) itu **additive**, tidak akan merusak kode yang sudah ada.

---

## 2. Fondasi Bersama: Konsep "Team Config" / "Roster"

Tiga dari empat fitur (nama tim, aset custom, atribut pemain) sama-sama butuh cara untuk **mendefinisikan sebuah tim dari luar** (nama, warna/aset, daftar pemain+stat) alih-alih hardcoded di kode. Daripada membangun ini 3x terpisah, saya sarankan satu fondasi bersama duluan:

```python
# konsep, bukan kode final
TeamConfig = {
    "name": "FC Merah",
    "color": (230, 70, 70),
    "flag_image": "assets/flags/merah.png",   # opsional
    "roster": [                                # opsional - kalau kosong, pakai stat default netral
        {"role": "GK", "name": "Andi", "stats": {"pace": 60, "shooting": 40, "tackling": 55, "reflex": 75}},
        ...
    ],
}
FutsalMatch(players_per_team=5, teams=(team_config_a, team_config_b))
```

Ini murni penyatuan interface — tidak menambah kompleksitas baru, malah mengurangi (satu param `teams=` menggantikan potensi 3 param terpisah untuk nama/aset/roster).

---

## 3. Prioritas & Urutan yang Disarankan

1. **Nama tim custom dulu** — fondasional, kecil, dan membuka jalan untuk fitur lain (aset & atribut butuh "team config" yang sama).
2. **Atribut statistik pemain** — independen, nilai tinggi (bikin tiap match terasa beda tergantung roster), effort sedang.
3. **Statistik gol & assist pemain** — independen dari 1-2, effort kecil-sedang, sinergis kalau atribut pemain (langkah 2) sudah ada (nama pemain buat ditampilkan di papan top scorer).
4. **Aset gambar custom** — dibangun di atas team config dari langkah 1, effort bertahap (bendera dulu, baru sprite pemain).
5. **Adu penalti** — paling kompleks (state machine baru), effort besar, tapi paling independen — bisa dikerjakan kapan saja tanpa nunggu yang lain kalau prioritas berubah.
6. **Power-up — sengaja paling akhir** (permintaan eksplisit). Alasan teknis yang mendukung urutan ini juga: butuh pipeline aset (langkah 4) buat ikon, dan ini fitur yang paling mengubah karakter game (dari "simulasi realistis" ke arah "arcade") — masuk akal baru disentuh setelah fondasi lain stabil.

---

## 4. Rencana Detail per Fitur

### A. Custom Nama Tim

**Tugas konkret**:
1. Ganti 5 titik hard comparison (§1) dari `team == "red"` jadi `home_side == -1` (atau turunan langsung darinya) — substitusi murni, tanpa redesain.
2. `FutsalMatch(..., teams=(name_a, name_b))` — default `("red", "blue")` supaya perilaku lama tidak berubah kalau tidak diisi.
3. `render/draw.py` scoreboard: ganti string hardcode `"RED {..} - {..} BLUE"` jadi baca dari `match.score` langsung (key sudah otomatis jadi nama custom).
4. ✅ **Sudah ada**: `match.team_colors[team]` (dan `match.team_labels[team]` untuk nama warnanya) — tapi key-nya masih `team` internal (`"red"`/`"blue"`), belum terhubung ke nama tim custom dari poin 2. Begitu nama tim custom ada, tinggal sambungkan: `team_colors[custom_name]` alih-alih `team_colors["red"]`.

**Acceptance criteria**: ganti nama tim jadi apa saja (termasuk nama dengan spasi/karakter unik) tidak mengubah hasil gameplay sama sekali (regression test seperti biasa — skor & event log identik untuk seed yang sama).

---

### B. Aset Gambar Custom

**Tugas konkret** (bertahap, dari yang murah ke yang mahal):
1. **Nomor punggung** (paling murah, mulai dari sini) — render angka pakai font yang sudah ada di tengah lingkaran pemain, tanpa aset gambar sama sekali. Langsung bikin match terasa lebih "sungguhan" tanpa infrastruktur baru.
2. `render/assets.py` — `load_image(path, size=None)` dengan cache + fallback graceful (`FileNotFoundError` → `None`, render tetap jalan pakai circle polos kalau path tidak diisi/tidak ketemu). Ini prasyarat teknis buat item 3-4.
3. **Bendera/logo tim** — icon kecil di sebelah nama tim di scoreboard. Murah, dampak visual tinggi, tidak perlu sentuh rendering pemain/bola.
4. **Tekstur bola** — ganti `pygame.draw.circle` bola jadi `surface.blit(scaled_image, ...)` kalau `ball_image` diisi.
5. **Sprite pemain sungguhan** (paling mahal, terakhir) — perlu rotasi berdasar arah gerak (`body.velocity`) supaya tidak terlihat aneh (gambar statis di atas lingkaran yang bergerak cepat terlihat lebih jelek daripada lingkaran polos kalau tidak dirotasi). Sarankan tunda sampai 1-4 selesai dan terbukti dibutuhkan.

**Acceptance criteria**: match tetap bisa dijalankan (dan terlihat sama seperti sekarang) tanpa aset apapun diisi — semua aset bersifat opsional dengan fallback.

---

### C. Adu Penalti

**Tugas konkret**:
1. Titik sambung persis di [render/preview.py](render/preview.py) setelah loop `while match.match_clock < MATCH_SECONDS`: kalau `match.score[team_a] == match.score[team_b]`, jalankan `run_penalty_shootout(match)` sebelum `draw_final_score`.
2. **Jangan** reuse physics 10 pemain penuh untuk ini (overkill) — buat `sim/penalty.py` dengan simulasi ringan: gantian penendang tiap tim (5x, lalu sudden death), tiap tendangan dihitung sebagai probabilitas (pakai stat `shooting` penendang vs stat kiper kalau §D sudah ada, atau fallback 75% base rate kalau belum), baru divisualisasikan lewat animasi sederhana (posisi bola di titik penalti → tendang → kiper reaksi berdasar hasil yang sudah ditentukan).
3. Render: bisa reuse `draw_frame` dengan mode "zoom ke satu gawang" (opsional, polish tahap 2 — bagus untuk video vertikal karena lebih dramatis, tapi tidak wajib untuk fungsi dasar).

**Acceptance criteria**: match yang berakhir seri selalu lanjut ke adu penalti dan menghasilkan pemenang tunggal; match yang tidak seri langsung ke layar FULL TIME seperti sekarang.

---

### D. Atribut Statistik Pemain

**Tugas konkret**:
1. **Prasyarat**: nama-in dulu literal yang belum jadi constant (§1) — peluang tackle `0.5` di [sim/match.py:226](sim/match.py#L226), kekuatan pass `380`, jarak lari FWD `220` — supaya ada "titik pengait" yang jelas untuk discale oleh stat.
2. Tambah key `"stats"` opsional ke player dict di `_spawn_team` — default semua stat = nilai netral yang **menghasilkan perilaku identik dengan sekarang** kalau tidak diisi (wajib demi backward compatibility).
3. Formula scaling (linear, sederhana dulu — jangan kompleks di awal):
   - `speed = BASE_SPEED * (0.7 + 0.6 * pace/100)` — pace 50 (default) = speed sama seperti sekarang persis.
   - Peluang menang tackle: `0.5 + (tackler.tackling - carrier.tackling) / 200`, di-clamp `[0.2, 0.8]` (jangan pernah 100% pasti menang/kalah).
   - `SHOT_POWER`/`SHOT_ANGLE_SPREAD` diskalakan oleh stat `shooting` milik penembak.
   - `KEEPER_SLIP_CHANCE` diskalakan terbalik oleh stat kiper (kiper bagus jarang slip).
4. `FutsalMatch(..., teams=(team_config_a, team_config_b))` — roster opsional per §2; kalau kosong, generate stat default netral seperti sekarang (tidak ada perubahan perilaku).

**Acceptance criteria**: tanpa roster custom, hasil regression test (skor/event log) identik dengan sebelum perubahan. Dengan roster custom (misal 1 pemain pace=95 vs default=50), pemain itu harus terukur lebih cepat mencapai bola dalam test headless.

**Sumber data eksternal buat ngisi roster** (hasil riset, dicek 2026-07):

| Sumber | Tipe | Cocok untuk | Catatan |
|---|---|---|---|
| **[SoFIFA](https://sofifa.com/document) → dataset [Kaggle](https://www.kaggle.com/datasets/luisfucros/fifa-players) / [FC 26](https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data)** | Dataset statis (CSV), bukan API real-time | **Paling cocok** — atribut 0-100 (pace, shooting, dribbling, defending, physical) formatnya hampir 1:1 sama `player["stats"]` yang direncanakan di §D.2-3, tinggal mapping field. | Halaman `sofifa.com/document` sendiri mengembalikan 403 saat dicoba diakses langsung — belum terkonfirmasi apakah ada API live publik beneran, yang pasti tersedia & gampang dipakai adalah dataset hasil scrape di Kaggle. |
| **[football-data.org](https://www.football-data.org/)** | API live | Nama tim/pemain asli (§4.A), bukan atribut skill | Gratis selamanya (komitmen founder), 10 request/menit, 12 kompetisi besar. Tidak ada data pace/shooting dll — cuma fixtures/standings/nama pemain. |
| **[API-Football](https://freeapihub.com/apis/api-football)** | API live | Nama tim/pemain asli + statistik pertandingan (gol, assist) | Tier gratis 100 request/hari, 1.236 liga. Statistik pertandingan, bukan rating atribut gaya FIFA. |
| **[TheSportsDB](https://github.com/topics/football-api)** | API live, crowd-sourced | Prototyping cepat | Gratis tapi kualitas data "hobby-grade", jangan diandalkan untuk akurasi. |

**Rekomendasi konkret**: pakai dataset Kaggle SoFIFA/FC buat **seed roster default** (§D.4, `teams=` param) karena formatnya paling siap pakai dan tidak perlu urus rate limit/auth sama sekali (cuma download CSV sekali, commit ke repo atau load lokal). Kalau nanti mau nama tim/pemain yang benar-benar real & up to date (bukan cuma rating), baru pertimbangkan football-data.org untuk melengkapi nama di §4.A.

---

### E. Statistik Gol & Assist Pemain (akhir pertandingan)

**Kondisi saat ini**: `event_log` sudah mencatat teks `"{p['id']} shoots!"` dan `"GOAL! {team} scores!"` sebagai entri terpisah, tapi **tidak ada link terstruktur** antara satu gol dan pemain spesifik yang mencetaknya, dan **belum ada konsep assist sama sekali**. Ini fitur baru, bukan sekadar baca ulang data yang sudah ada (beda dari saran §5.4 versi lama, yang sudah dilebur ke sini).

**Tugas konkret**:
1. Tambah counter per-pemain: `player["goals"] = 0`, `player["assists"] = 0` di `_spawn_team` (additive, aman — pola sama seperti field `stunned_until` yang sudah ada).
2. Track `self.last_shooter` — di-set di `_release_ball(shoot=True)` ke id penembak; di-clear begitu bola dipungut pemain LAIN (baik lawan yang menggagalkan, atau bahkan rekan setim yang berarti itu sudah jadi possession baru, bukan lanjutan tembakan yang sama).
3. Track `self.pending_assist` — di-set ke id pengoper setiap kali ada operan sukses (`_release_ball(shoot=False)`) yang diarahkan ke pemain tertentu; **hanya tetap valid** kalau penerima operan itu sendiri yang jadi `last_shooter` berikutnya tanpa ada pemain lain menyentuh bola di antaranya. Kalau ada sentuhan lain (dribble lama, direbut, dst), `pending_assist` di-clear.
4. Di `_check_goal`, saat `scored` terdeteksi: `+1 goals` ke `last_shooter` (kalau valid & satu tim dengan `scored`), `+1 assists` ke `pending_assist` (kalau masih valid).
5. **Scope sengaja dibatasi** (biar gak over-engineer): gol bunuh diri, gol dari rebound/defleksi berantai tidak dilacak assist-nya secara detail di v1 — dikreditkan ke penembak terakhir yang sah, tanpa assist, kalau rantainya ambigu. Bisa diperhalus nanti kalau ternyata dibutuhkan.
6. Render: panel tambahan setelah/di `draw_final_score` — daftar pemain diurutkan gol lalu assist ("Top Scorer: red_3 — 2 gol, 1 assist"). Sinergis dengan §D (kalau roster punya nama asli, tampilkan nama, bukan cuma id internal seperti `red_3`).

**Acceptance criteria**: total `sum(goals per player)` untuk satu tim harus selalu sama persis dengan `match.score[team]` di akhir match (invariant sederhana buat regression test) — kalau tidak sama, berarti ada gol yang gak ke-attribute dengan benar.

---

### F. Fitur Power-up *(sengaja di fase terakhir)*

**Kenapa terakhir**: ini fitur yang paling mengubah karakter game — dari "simulasi futsal yang realistis" ke arah nuansa arcade. Juga secara teknis paling diuntungkan kalau pipeline aset (§4.B) sudah ada duluan buat ikon power-up, dan paling independen dari 5 fitur lain sehingga aman ditunda tanpa memblokir apapun.

**Tugas konkret**:
1. Spawn objek power-up di posisi acak lapangan tiap interval waktu tertentu (misal tiap 15-20 detik, atau tiap habis gol), hilang otomatis kalau tidak diambil dalam waktu tertentu.
2. Pickup: reuse pola proximity-check yang sudah ada buat bola (`CONTROL_RADIUS`) — pemain pertama yang masuk radius power-up otomatis mengambil & efeknya langsung aktif.
3. Mulai dari **2-3 tipe efek sederhana** dulu, jangan langsung banyak:
   - **Speed boost** — kalikan speed efektif pemain untuk beberapa detik (kalau §D/atribut pemain sudah ada, ini literally re-use mekanisme scaling speed yang sama).
   - **Freeze lawan terdekat** — **sudah nyaris gratis dibangun**, karena mekanisme `stunned_until` buat freeze pemain **sudah ada** dari fitur tackle/stun yang sudah jalan sekarang. Tinggal panggil fungsi yang sama ke lawan terdekat dari pemain yang ambil power-up.
   - **Power shot** — tembakan berikutnya dari pemain itu dapat `SHOT_POWER` lebih besar & `SHOT_ANGLE_SPREAD` lebih presisi untuk satu kesempatan.
4. Visual: ikon per tipe power-up di lapangan (pakai pipeline aset dari §4.B — alasan lain kenapa fitur ini nunggu di belakang).
5. **Sarankan power-up bisa di-toggle on/off** (`FutsalMatch(..., powerups_enabled=False)` default) — supaya mode "simulasi realistis" yang sudah ada tetap bisa dipilih apa adanya, power-up murni opsional/tambahan, bukan menggantikan mode default.

**Acceptance criteria**: dengan `powerups_enabled=False` (default), hasil regression test (skor/event log) identik dengan sebelum fitur ini ada — power-up 100% opt-in, tidak mengubah perilaku default sama sekali.

---

## 5. Saran Tambahan (di luar yang diminta)

Beberapa hal yang menurut saya sinergis banget dengan fitur-fitur di atas dan murah untuk ditambahkan sekalian:

1. **File konfigurasi eksternal (JSON)** untuk team config — begitu fitur A+B+D digabung, "custom" akan tetap berarti "edit Python" kalau tidak ada cara load dari file. Ini hampir jadi kebutuhan wajib begitu 2+ dari fitur ini selesai, bukan cuma nice-to-have. Sarankan masuk sebagai bagian dari Fase A (nama tim) sejak awal, format sederhana:
   ```json
   {"name": "FC Merah", "color": [230,70,70], "roster": [...]}
   ```
2. **Kit color custom** (bukan cuma nama tim) — hampir gratis ditambahkan sekalian pas mengerjakan §A, dan visualnya langsung berasa "tim beneran" tanpa perlu aset gambar sama sekali.
3. **Nomor punggung pemain** — sudah dibahas di §B item 1, saya angkat lagi di sini karena ini literally quick-win termurah dari seluruh daftar (satu `font.render()`, tidak ada aset, tidak ada infrastruktur baru) tapi dampak "terasa seperti pertandingan sungguhan"-nya besar.
4. **Stamina/fatigue** — perpanjangan alami dari §D: `pace` efektif menurun seiring `match.time_elapsed` pemain itu aktif bermain (terutama kalau nanti ada fitur substitusi pemain). Effort kecil kalau sistem atribut (§D) sudah ada, dampak realism lumayan.

*(Catatan: saran lama "ringkasan statistik akhir match" sudah dipromosikan jadi fitur formal §4.E, tidak lagi di sini.)*

Saya taruh ini sebagai saran, bukan rencana wajib — kalau ada yang menarik, bilang aja mana yang mau dimasukkan ke prioritas.

---

## 6. Guardrail YAGNI

Supaya tidak over-engineer, berikut yang **jangan** dikerjakan sampai ada bukti nyata dibutuhkan:

- Sistem substitusi pemain di tengah match (bangku cadangan) — kompleks, belum diminta
- Formasi taktik yang bisa diganti-ganti user (4-4-2 vs 3-3 dll) — role BACK/FWD/GK yang ada sudah cukup untuk saat ini
- Editor roster/tim visual (GUI) — biarkan tetap lewat kode/JSON dulu
- Animasi sprite pemain yang kompleks (running cycle, dll) — jersey number + circle sudah cukup representatif untuk kebutuhan video pendek
- Liga/turnamen multi-match dengan klasemen — di luar cakupan "1 match = 1 video"
- Power-up dengan banyak tipe efek sekaligus di v1 (§4.F) — mulai dari 2-3 tipe paling murah (reuse mekanisme yang sudah ada), baru tambah variasi kalau terbukti seru & dibutuhkan
- Assist chain/multi-level (assist dari assist, dst) di §4.E — definisi assist sengaja dibatasi 1 level (operan langsung ke penembak)

---

## 7. Urutan Eksekusi yang Disarankan

Mulai dari **§4.A (nama tim)** sekaligus fondasi §2 (team config) dan saran §5.1 (JSON config) — kecil, murah, dan membuka jalan buat fitur lain. Setelah itu **§4.D (atribut pemain)** karena nilainya tinggi dan independen, lalu **§4.E (statistik gol & assist)** yang independen tapi sinergis kalau §D sudah ada (nama pemain buat papan top scorer). **§4.B (aset)** dikerjakan bertahap sesuai urutan murah→mahal di dalamnya. **§4.C (adu penalti)** setelahnya karena besar tapi independen. **§4.F (power-up) paling akhir** — sesuai permintaan eksplisit, dan juga karena paling diuntungkan kalau §4.B (aset) sudah selesai duluan buat ikonnya.
