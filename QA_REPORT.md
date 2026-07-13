# QA Report — Futsal Sim (Ligue1Real)

**Proyek**: Simulasi pertandingan futsal 5v5 otomatis → video (Python, pymunk untuk physics, pygame untuk rendering)
**Peran**: Solo developer + QA selama proses pengembangan
**Metodologi testing**: automated headless simulation, statistical/Monte Carlo testing lintas random seed, regression testing tiap fix, playtest feedback loop, visual review via rendered screenshot

---

## Ringkasan Metodologi

Karena game ini tidak punya UI interaktif tradisional (output-nya video), sebagian besar bug ditemukan lewat **automated headless testing** — menjalankan simulasi ratusan/ribuan frame tanpa render, lalu memeriksa state (posisi pemain, skor, event log) secara terprogram. Beberapa bug (khususnya bug balance/fairness) **tidak akan pernah ketemu dari 1-2 kali playtest manual** — baru kelihatan setelah menjalankan simulasi across banyak random seed dan membandingkan distribusi hasil (statistical/Monte Carlo testing). Ini pola yang saya pakai berulang di laporan bawah:

1. **Reproduce** — isolasi kondisi yang memicu bug secara konsisten (seed spesifik, atau agregat statistik banyak seed)
2. **Root cause** — trace ke baris kode spesifik lewat instrumentasi (print posisi/state tiap frame)
3. **Fix** — perubahan minimal, spesifik ke root cause (bukan tambal gejala)
4. **Verify** — regression test ulang (headless, biasanya 10-25 match/seed) untuk konfirmasi fix bekerja DAN tidak merusak hal lain

---

## Ringkasan Temuan

| ID | Judul | Severity | Metode Temuan | Status |
|---|---|---|---|---|
| [BUG-001](#bug-001) | AI pemain diam total, bola tidak pernah tersentuh | Critical | Headless simulation | Fixed & Verified |
| [BUG-002](#bug-002) | Self-repossession loop — spam event tak terkendali | High | Event log review | Fixed & Verified |
| [BUG-003](#bug-003) | Kick-off tidak adil — tim merah selalu menang rebutan bola | Medium | Statistical testing (multi-seed) | Fixed & Verified |
| [BUG-004](#bug-004) | Kiper diroyok, gol mudah tercipta dari tekel jarak dekat | High | Event log trace | Fixed & Verified |
| [BUG-005](#bug-005) | Rasio konversi tembakan tidak realistis (0% atau ~100%) | Medium | Statistical testing (multi-seed) | Fixed & Verified |
| [BUG-006](#bug-006) | Tendangan sudut tajam bisa "lolos" masuk gawang tanpa halangan fisik | Medium | User playtest report | Fixed & Verified |
| [BUG-007](#bug-007) | Permainan terlalu terpusat di tengah, tidak ada wing play | Low-Medium | User playtest report | Fixed & Verified |
| [BUG-008](#bug-008) | Regresi: wing play terlalu ekstrem (dua sayap sekaligus) | Low | User playtest report | Fixed & Verified |
| [BUG-009](#bug-009) | Window preview terpotong taskbar Windows | Low | User environment report | Fixed |
| [BUG-010](#bug-010) | Layar FULL TIME — teks numpuk di atas sprite pemain | Low | Visual/screenshot review | Fixed & Verified |

---

## Detail Temuan

### BUG-001
**Judul**: AI pemain diam total setelah beberapa frame, bola tidak pernah tersentuh
**Severity**: Critical — game-breaking, loop gameplay inti tidak berfungsi
**Environment**: Python 3.12.2, pymunk 7.3.0

**Steps to Reproduce**:
1. Buat `FutsalMatch(players_per_team=3, seed=1)`
2. Jalankan `match.step()` selama 30 frame
3. Amati `body.velocity` tiap pemain

**Expected**: Pemain terus bergerak, minimal ada yang mendekati bola.
**Actual**: Semua pemain velocity konvergen ke `(0,0)` persis setelah mencapai posisi formasi masing-masing. Bola diam di tengah lapangan selamanya.

**Root Cause**: Formula target posisi bertahan (`target_y`) di `choose_action` statis persis di `home_y` (garis spawn), tidak pernah tertarik ke posisi bola secara vertikal — cuma `target_x` yang punya bobot tarikan ke bola. Akibatnya radius kejar bola (260px) tidak pernah terpenuhi karena pemain berhenti tepat di garis spawn horizontal sejajar bola tapi terlalu jauh secara diagonal.

**Suggested Fix**: `target_y = by * 0.35 + home_y * 0.65` (sebelumnya `target_y = home_y` statis) — cermin dari formula `target_x` yang sudah benar.
**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Simulasi headless 300 frame ulang — bola bergerak, gol tercipta (0-2 dalam 10 detik simulasi pertama).

---

### BUG-002
**Judul**: Self-repossession loop menyebabkan spam event "shoots!" tak terkendali
**Severity**: High — merusak log/statistik pertandingan, indikasi bug fisika/logic

**Steps to Reproduce**:
1. Jalankan match headless sampai terjadi tembakan pertama
2. Print `event_log` penuh

**Expected**: Satu entri "X shoots!" per tembakan.
**Actual**: 60+ entri "X shoots!" dari pemain yang SAMA dalam rentang <0.02 detik berturut-turut.

**Root Cause**: Setelah `_release_ball()` melepas bola dengan velocity baru, substep fisika berikutnya (1/120 detik) bola baru bergerak ~3-4px — masih dalam `CONTROL_RADIUS` (46px) pemain yang sama. Pemain itu langsung memungut ulang bolanya sendiri dan mengulang keputusan tembak, berulang-ulang sampai bola akhirnya cukup jauh.

**Suggested Fix**: Tambah cooldown pemungutan — pemain yang baru melepas bola (shooter atau bek yang baru "dilewati") tidak bisa memungutnya lagi selama jendela waktu singkat (0.35 detik).
**Fix Applied**: Ya — `self.pickup_exempt` / `self.pickup_cooldown_until` di `sim/match.py`
**Verification**: Event log ulang — tidak ada lagi entri berulang dari pemain sama dalam rentang waktu <0.1s.

---

### BUG-003
**Judul**: Kick-off tidak adil — satu tim (merah) menang rebutan bola bebas jauh lebih sering
**Severity**: Medium — bug fairness/balance, bukan crash, tapi merusak inti kompetitif game

**Steps to Reproduce**:
1. Jalankan 6+ match penuh dengan seed berbeda (posisi kick-off simetris tiap kali)
2. Bandingkan skor akhir tim merah vs biru

**Expected**: Distribusi skor kurang lebih seimbang antar tim (posisi kick-off simetris).
**Actual**: Salah satu match berakhir 8-0. Pola konsisten: tim merah unggul jauh lebih sering di rebutan bola bebas pasca-kickoff.

**Root Cause**: Logika pemungutan bola bebas mengambil pemain **pertama di `self.players` yang masuk radius**, bukan yang benar-benar terdekat (`for p in self.players: if dist<RADIUS: possessor=p; break`). Karena list pemain selalu diisi tim merah duluan, dan posisi kick-off simetris membuat kedua tim sering masuk radius di physics-step yang sama, tie selalu dimenangkan tim merah akibat urutan list — bukan jarak sebenarnya.

**Suggested Fix**: Ganti jadi iterasi cari jarak minimum sungguhan di antara semua kandidat, baru assign possessor setelah loop selesai (bukan `break` di kandidat pertama yang memenuhi syarat).
**Fix Applied**: Ya — `sim/match.py::_update_possession`
**Verification**: Regression test 6 seed — skor jadi seimbang (3-4, 4-3, 3-4, 6-4, 2-5, 2-6), tidak ada lagi dominasi satu tim.

---

### BUG-004
**Judul**: Kiper diroyok penyerang lawan; gol mudah tercipta dari tekel jarak sangat dekat
**Severity**: High — merusak keseimbangan pertahanan, membuat pertandingan tidak realistis

**Steps to Reproduce**:
1. Jalankan match headless, trace event log
2. Cari pola "TACKLE! X wins the ball" yang diikuti langsung "GOAL!" dalam <1 detik

**Expected**: Peluang mencetak gol proporsional terhadap kualitas peluang (jarak, tekanan bek).
**Actual**: Sebagian besar gol terjadi tepat setelah tekel menang **di depan kiper**, karena penyerang sudah dibiarkan berlari sampai ke kotak penalti tanpa dijaga.

**Root Cause**: Dua masalah bertumpuk:
1. Semua bek mengejar **posisi persis** pembawa bola (bukan menjaga ruang/cover), sehingga tidak ada yang menutup ruang di belakang saat lawan melakukan operan/lari ke depan.
2. Begitu kiper memegang bola, penyerang lawan tetap menekan sampai jarak sangat dekat — begitu menang tekel, jarak ke gawang sudah dalam `SHOT_RANGE`, hampir pasti gol.

**Suggested Fix**:
1. Bek terdekat menekan ketat, bek lainnya mengambil posisi cover antara bola dan gawang sendiri (bukan collapsing ke titik yang sama).
2. Kalau yang pegang bola adalah kiper, lawan mundur ke posisi formasi (tidak ikut menekan).

**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Trace event log ulang — tidak lagi ada pola tekel-menang-langsung-gol beruntun di depan kiper.

---

### BUG-005
**Judul**: Rasio konversi tembakan tidak realistis — berayun antara 0% dan ~100%
**Severity**: Medium — realism/balance, ditemukan bertahap lewat 3 root cause berbeda

**Steps to Reproduce**:
1. Jalankan 10-20 match headless dengan seed berbeda
2. Hitung `total_goals / total_shots`

**Expected**: Rasio konversi realistis untuk olahraga (~10-30%).
**Actual** (progresif, 3 iterasi):
- Iterasi 1: 0 gol dalam 20 match meski ada 100+ tembakan (0% konversi)
- Iterasi 2 (setelah fix parsial): kembali ke hampir 100% (setiap tembakan = gol otomatis)
- Iterasi 3: tembakan diblok bek sebelum sempat sampai ke gawang

**Root Cause** (3 sub-penyebab, ditemukan berurutan lewat instrumentasi posisi bola vs kiper tiap frame):
1. Kiper melacak posisi bola **secara terus-menerus** (bukan cuma bereaksi saat ditembak), jadi selalu sudah di posisi ideal sebelum tembakan lepas — hampir mustahil dikalahkan.
2. Bek yang seharusnya "cover" malah berdiri **persis di jalur lurus** antara bola dan gawang sendiri — jadi tembakan diblok bek sebelum sempat diuji lawan kiper sama sekali.
3. Bek yang baru gagal tekel bisa langsung mencegat ulang tembakan yang baru lepas (varian dari BUG-002, tapi untuk shot bukan possession).

**Suggested Fix**:
1. Tambah randomisasi sudut & jarak tembak (`SHOT_ANGLE_SPREAD`, `SHOT_DIST_MIN/MAX`) — tembakan sekarang bisa melebar keluar gawang, tidak selalu presisi ke tengah.
2. Turunkan kecepatan reaksi kiper (dari 200 ke 100 px/s) supaya tidak selalu bisa menutup semua sudut.
3. Lepaskan posisi cover bek dari collapsing ke jalur bola — tetap di zona lateral sendiri.
4. Tambah exemption pemungutan sementara untuk bek yang baru "dilewati" tembakan (sama mekanisme dengan BUG-002).

**Fix Applied**: Ya — kombinasi `sim/config.py` (konstanta baru) dan `sim/match.py`/`sim/scripted_ai.py`
**Verification**: Regression test 20 match — konversi tembakan naik jadi ~11% (22 gol / 198 tembakan), 15/20 match punya minimal 1 gol.

---

### BUG-006
**Judul**: Tendangan dari sudut sangat tajam di luar mulut gawang bisa "lolos" masuk tanpa halangan fisik
**Severity**: Medium — realism bug, dilaporkan langsung oleh user saat playtest video

**Steps to Reproduce**:
1. Playtest visual — perhatikan gol yang tercipta dari tendangan sudut lebar/dari samping
2. Reproduksi terkontrol: tembak bola dari luar `goal_top_x_range` dengan velocity nyaris sejajar garis gawang

**Expected**: Tembakan dari sudut tajam di luar lebar gawang seharusnya membentur tiang/dinding, bukan masuk.
**Actual**: Bola bisa "menyusur" masuk ke mulut gawang dari sudut yang secara geometris mustahil di sepak bola nyata.

**Root Cause**: Tiang gawang cuma direpresentasikan sebagai ujung garis dinding tipis (10px) yang persis berada di garis gawang — tidak ada objek fisik nyata (post) yang menonjol untuk menghalangi bola dari sudut landai.

**Suggested Fix**: Tambah 4 objek fisik statis (`pymunk.Circle`, radius 9px) di tiap sudut mulut gawang dengan elastisitas tinggi (0.9) supaya bola memantul realistis kalau kena tiang.
**Fix Applied**: Ya — `sim/match.py::_build_walls` + render visual tiang di `render/draw.py`
**Verification**: Physics test terkontrol — bola yang ditembak landai dari luar mulut gawang terdeteksi kena deflect tepat di posisi tiang (`vx` berubah drastis dari +500 ke -76.6px/s), bukan lolos masuk. Regression test 20 match tetap sehat (13/20 ada gol, tidak ada bola/pemain macet di luar batas lapangan).

---

### BUG-007
**Judul**: Permainan terlalu terpusat di tengah lapangan, tidak ada wing play
**Severity**: Low-Medium — gameplay variety/realism, dilaporkan user

**Steps to Reproduce**: Playtest visual — perhatikan hampir semua build-up serangan terjadi di jalur tengah sempit.

**Expected**: Variasi serangan termasuk lewat sisi lapangan (wing play), sesuai futsal/sepak bola nyata.
**Actual**: FWD (penyerang) jarang menjauh lebih dari ±80px dari titik tengah lapangan (lebar lapangan total 820px).

**Root Cause**: Formasi FWD terlalu sempit (`formation_x_offset` maksimal ±80px), dan formula target dribble (`target_x = mid_x + offset * 0.6`) menarik terlalu kuat ke tengah bahkan saat pemain sudah di posisi lebar.

**Suggested Fix**: Perlebar spacing formasi FWD, naikkan bobot posisi lateral asli saat dribble (dari 0.6 ke 0.8).
**Fix Applied**: Ya — `sim/config.py` (spacing constants) + `sim/scripted_ai.py`
**Verification**: Ukur standar deviasi posisi-x FWD sepanjang match — naik dari implisit sempit jadi 250.5px, mengonfirmasi penyebaran lateral yang jauh lebih luas.

---

### BUG-008
**Judul**: Regresi dari BUG-007 — wing play jadi terlalu ekstrem, kedua FWD sama-sama bermain di sayap
**Severity**: Low — balance tuning, ditemukan user sendiri lewat playtest video setelah fix BUG-007 di-deploy

**Steps to Reproduce**: Playtest visual pasca-fix BUG-007 — perhatikan kedua penyerang selalu di dekat garis sisi kiri/kanan secara bersamaan, tidak ada yang jadi target sentral.

**Expected**: Satu penyerang sebagai winger (sayap), satu sebagai striker sentral — bukan dua-duanya di sayap sekaligus.
**Actual**: Formasi simetris membuat kedua FWD selalu lebar di sisi berlawanan, tidak ada opsi umpan silang ke tengah.

**Root Cause**: Fix BUG-007 melebarkan **kedua** slot FWD secara simetris tanpa diferensiasi peran.

**Suggested Fix**: Ganti jadi pairing dinamis realtime — FWD yang posisinya lebih dekat ke sisi bola saat itu otomatis jadi winger (melebar), yang satunya otomatis jadi striker tengah. Keputusan berdasarkan jarak-ke-bola (bukan identitas tetap/saling cek satu sama lain) untuk menghindari risiko osilasi (keduanya gantian wide↔center tiap frame kalau kondisinya simetris).
**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Sampling 90 titik sepanjang 1 match — 28 kali terjadi perpindahan peran wide antar kedua FWD, mengonfirmasi perilaku dinamis (bukan identitas statis) tanpa oscillation runaway.

---

### BUG-009
**Judul**: Window preview terpotong taskbar Windows
**Severity**: Low — environment-specific display issue

**Steps to Reproduce**: Jalankan `python main.py` di Windows dengan resolusi layar yang lebih kecil, amati window preview.

**Expected**: Window preview sepenuhnya terlihat.
**Actual**: Bagian bawah window tertutup taskbar Windows.

**Root Cause**: `preview_scale = 0.5` menghasilkan tinggi window 960px — terlalu tinggi untuk resolusi layar tertentu setelah dikurangi tinggi taskbar+titlebar.

**Suggested Fix**: Turunkan `preview_scale` ke 0.42 (~806px tinggi window).
**Fix Applied**: Ya — `render/preview.py`
**Verification**: Perhitungan piksel dikonfirmasi (806px vs 960px sebelumnya); tidak ada environment display di sesi development untuk verifikasi visual langsung, jadi diverifikasi user secara langsung.

---

### BUG-010
**Judul**: Layar FULL TIME — teks skor akhir numpuk langsung di atas sprite pemain
**Severity**: Low — visual polish, ditemukan lewat self-review screenshot sebelum diserahkan ke user

**Steps to Reproduce**: Render `draw_final_score()` ke gambar, amati komposisi visual.

**Expected**: Teks "FULL TIME" dan skor terbaca jelas.
**Actual**: Teks floating langsung di atas overlay transparan gelap, tumpang tindih visual dengan titik-titik pemain di baliknya — sulit dibaca.

**Root Cause**: Implementasi awal cuma overlay semi-transparan + teks langsung di-blit tanpa background solid.

**Suggested Fix**: Ganti jadi panel solid bulat sudut dengan border, teks diletakkan di dalam panel (bukan floating di atas gameplay).
**Fix Applied**: Ya — `render/draw.py::draw_final_score`
**Verification**: Render ulang ke screenshot offscreen (SDL dummy driver) — dikonfirmasi visual, teks terbaca jelas tanpa tumpang tindih dengan elemen di belakangnya.

---

## Refleksi Proses QA

Beberapa pola yang saya pakai konsisten sepanjang proses ini, relevan untuk peran QA:

- **Automated regression testing tiap fix** — setiap perbaikan diverifikasi ulang lewat simulasi headless (biasanya 10-25 match/seed berbeda), bukan cuma "kelihatannya sudah benar."
- **Statistical/Monte Carlo testing untuk bug balance** — BUG-003 dan BUG-005 tidak akan pernah ketemu dari 1-2 kali playtest manual; baru kelihatan setelah agregasi hasil across banyak seed acak dan membandingkan distribusi (skor, rasio konversi).
- **Instrumentasi terarah untuk root cause** — daripada menebak, saya print state (posisi, velocity, jarak) tiap frame di sekitar momen bug terjadi untuk melacak titik persis penyebabnya (contoh: BUG-005 butuh 3 putaran instrumentasi berbeda sebelum ketemu semua sub-penyebab).
- **Verifikasi terkontrol, bukan cuma observasional** — BUG-006 diverifikasi lewat physics test yang sengaja menembakkan bola pada sudut spesifik, bukan cuma menunggu kejadian serupa muncul lagi secara kebetulan.
