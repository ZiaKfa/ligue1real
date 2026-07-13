# QA Report — Futsal Sim (Ligue1Real)

**Proyek**: Simulasi pertandingan futsal 5v5 otomatis → video (Python, pymunk untuk physics, pygame untuk rendering)
**Peran**: Solo developer + QA selama proses pengembangan
**Metodologi testing**: playtest manual (menjalankan `python main.py`, mengamati preview render + event log konsol), lintas beberapa run/seed berbeda untuk bug bertipe pola/fairness; regression test via headless simulation untuk verifikasi tiap fix

---

## Ringkasan Metodologi

Semua bug di bawah **ditemukan lewat playtest manual** — menjalankan `python main.py` (preview window aktif), mengamati gameplay secara visual, dan membaca event log yang tercetak di konsol. Untuk bug yang sifatnya pola/fairness (bukan crash sekali kejadian), polanya baru kelihatan setelah menjalankan beberapa match secara manual dengan seed berbeda dan membandingkan hasil (skor akhir, jumlah tembakan vs gol) — tetap lewat run biasa dengan render, bukan batch otomatis.

**Headless simulation** (memanggil `FutsalMatch` langsung tanpa pygame) dipakai di proyek ini **khusus untuk tahap verifikasi**: setelah fix diterapkan, dijalankan puluhan match headless (cepat, tanpa render) untuk memastikan gejalanya hilang dan tidak ada regresi lain. Headless bukan alat untuk menemukan bug pertama kali di proyek ini.

Pola yang saya pakai berulang di laporan bawah:

1. **Temukan** — lewat playtest manual (visual + event log konsol), kadang lintas beberapa run/seed untuk melihat pola
2. **Root cause** — trace ke baris kode spesifik lewat pembacaan kode dan log dari playtest yang sama
3. **Fix** — perubahan minimal, spesifik ke root cause (bukan tambal gejala)
4. **Verify** — regression test headless (biasanya 10-30 match/seed) untuk konfirmasi fix bekerja DAN tidak merusak hal lain

---

## Ringkasan Temuan

| ID | Judul | Severity | Cara Ditemukan | Status |
|---|---|---|---|---|
| [BUG-001](#bug-001) | AI pemain diam total, bola tidak pernah tersentuh | Critical | Playtest manual (preview) | Fixed & Verified |
| [BUG-002](#bug-002) | Self-repossession loop — spam event tak terkendali | High | Playtest manual (event log konsol) | Fixed & Verified |
| [BUG-003](#bug-003) | Kick-off tidak adil — tim merah selalu menang rebutan bola | Medium | Playtest manual lintas beberapa run/seed | Fixed & Verified |
| [BUG-004](#bug-004) | Kiper dikepung, gol mudah tercipta dari tekel jarak dekat | High | Playtest manual (event log konsol) | Fixed & Verified |
| [BUG-005](#bug-005) | Rasio konversi tembakan tidak realistis (0% atau ~100%) | Medium | Playtest manual lintas beberapa run/seed | Fixed & Verified |
| [BUG-006](#bug-006) | Tendangan sudut tajam bisa "lolos" masuk gawang tanpa halangan fisik | Medium | Playtest manual (visual) | Fixed & Verified |
| [BUG-007](#bug-007) | Permainan terlalu terpusat di tengah, tidak ada wing play | Low-Medium | Playtest manual (visual) | Fixed & Verified |
| [BUG-008](#bug-008) | Regresi: wing play terlalu ekstrem (dua sayap sekaligus) | Low | Playtest manual (visual) | Fixed & Verified |
| [BUG-009](#bug-009) | Window preview terpotong taskbar Windows | Low | Laporan environment user | Fixed |
| [BUG-010](#bug-010) | Kiper dan bek saling mengoper bola berulang-ulang (backpass loop) | Medium | Playtest manual (visual + event log) | Fixed & Verified |
| [BUG-011](#bug-011) | Bola/pemain bisa snap keluar lapangan lewat mulut gawang | High | Playtest manual (visual) | Fixed & Verified |
| [BUG-012](#bug-012) | Nama warna tim kadang tidak cocok dengan warna yang sebenarnya tampil | Low | Playtest manual (visual) | Fixed & Verified |

---

## Detail Temuan

### BUG-001
**Judul**: AI pemain diam total setelah beberapa frame, bola tidak pernah tersentuh
**Severity**: Critical — game-breaking, loop gameplay inti tidak berfungsi
**Environment**: Python 3.12.2, pymunk 7.3.0

**Cara Ditemukan**: Playtest manual — jalankan `python main.py`, amati preview: semua pemain berhenti bergerak setelah beberapa detik dan bola diam di tengah lapangan selamanya.

**Expected**: Pemain terus bergerak, minimal ada yang mendekati bola.
**Actual**: Semua pemain velocity konvergen ke `(0,0)` persis setelah mencapai posisi formasi masing-masing.

**Root Cause**: Formula target posisi bertahan (`target_y`) di `choose_action` statis persis di `home_y` (garis spawn), tidak pernah tertarik ke posisi bola secara vertikal — cuma `target_x` yang punya bobot tarikan ke bola. Akibatnya radius kejar bola (260px) tidak pernah terpenuhi karena pemain berhenti tepat di garis spawn horizontal sejajar bola tapi terlalu jauh secara diagonal.

**Suggested Fix**: `target_y = by * 0.35 + home_y * 0.65` (sebelumnya `target_y = home_y` statis) — cermin dari formula `target_x` yang sudah benar.
**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Regression headless (300 frame) setelah fix, dipakai untuk memastikan fix bekerja (bukan untuk menemukan bug-nya) — bola bergerak, gol tercipta (0-2 dalam 10 detik simulasi pertama).

---

### BUG-002
**Judul**: Self-repossession loop menyebabkan spam event "shoots!" tak terkendali
**Severity**: High — merusak log/statistik pertandingan, indikasi bug fisika/logic

**Cara Ditemukan**: Playtest manual — event log konsol menampilkan 60+ entri "X shoots!" dari pemain yang SAMA berturut-turut dalam rentang <0.02 detik.

**Expected**: Satu entri "X shoots!" per tembakan.
**Actual**: Puluhan entri berulang dari shooter yang sama dalam waktu nyaris bersamaan.

**Root Cause**: Setelah `_release_ball()` melepas bola dengan velocity baru, substep fisika berikutnya (1/120 detik) bola baru bergerak ~3-4px — masih dalam `CONTROL_RADIUS` (46px) pemain yang sama. Pemain itu langsung memungut ulang bolanya sendiri dan mengulang keputusan tembak, berulang-ulang sampai bola akhirnya cukup jauh.

**Suggested Fix**: Tambah cooldown pemungutan — pemain yang baru melepas bola (shooter atau bek yang baru "dilewati") tidak bisa memungutnya lagi selama jendela waktu singkat (0.35 detik).
**Fix Applied**: Ya — `self.pickup_exempt` / `self.pickup_cooldown_until` di `sim/match.py`
**Verification**: Regression headless setelah fix — event log tidak lagi menunjukkan entri berulang dari pemain sama dalam rentang <0.1s.

---

### BUG-003
**Judul**: Kick-off tidak adil — satu tim (merah) menang rebutan bola bebas jauh lebih sering
**Severity**: Medium — bug fairness/balance, bukan crash, tapi merusak inti kompetitif game

**Cara Ditemukan**: Playtest manual — menjalankan beberapa match penuh (preview aktif) dengan seed berbeda; skor akhir yang tercetak di konsol menunjukkan pola konsisten tim merah unggul jauh lebih sering di rebutan bola bebas pasca-kickoff (salah satu match berakhir 8-0).

**Expected**: Distribusi skor kurang lebih seimbang antar tim (posisi kick-off simetris).
**Actual**: Tim merah menang rebutan bola bebas secara tidak proporsional across beberapa run.

**Root Cause**: Logika pemungutan bola bebas mengambil pemain **pertama di `self.players` yang masuk radius**, bukan yang benar-benar terdekat (`for p in self.players: if dist<RADIUS: possessor=p; break`). Karena list pemain selalu diisi tim merah duluan, dan posisi kick-off simetris membuat kedua tim sering masuk radius di physics-step yang sama, tie selalu dimenangkan tim merah akibat urutan list — bukan jarak sebenarnya.

**Suggested Fix**: Ganti jadi iterasi cari jarak minimum sungguhan di antara semua kandidat, baru assign possessor setelah loop selesai (bukan `break` di kandidat pertama yang memenuhi syarat).
**Fix Applied**: Ya — `sim/match.py::_update_possession`
**Verification**: Regression headless 6 seed setelah fix — skor jadi seimbang (3-4, 4-3, 3-4, 6-4, 2-5, 2-6), tidak ada lagi dominasi satu tim.

---

### BUG-004
**Judul**: Kiper dikepung penyerang lawan; gol mudah tercipta dari tekel jarak sangat dekat
**Severity**: High — merusak keseimbangan pertahanan, membuat pertandingan tidak realistis

**Cara Ditemukan**: Playtest manual — event log konsol menunjukkan pola "TACKLE! X wins the ball" diikuti langsung "GOAL!" dalam <1 detik, berulang di beberapa match.

**Expected**: Peluang mencetak gol proporsional terhadap kualitas peluang (jarak, tekanan bek).
**Actual**: Sebagian besar gol terjadi tepat setelah tekel menang **di depan kiper**, karena penyerang sudah dibiarkan berlari sampai ke kotak penalti tanpa dijaga.

**Root Cause**: Dua masalah bertumpuk:
1. Semua bek mengejar **posisi persis** pembawa bola (bukan menjaga ruang/cover), sehingga tidak ada yang menutup ruang di belakang saat lawan melakukan operan/lari ke depan.
2. Begitu kiper memegang bola, penyerang lawan tetap menekan sampai jarak sangat dekat — begitu menang tekel, jarak ke gawang sudah dalam `SHOT_RANGE`, hampir pasti gol.

**Suggested Fix**:
1. Bek terdekat menekan ketat, bek lainnya mengambil posisi cover antara bola dan gawang sendiri (bukan collapsing ke titik yang sama).
2. Kalau yang pegang bola adalah kiper, lawan mundur ke posisi formasi (tidak ikut menekan).

**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Regression headless setelah fix — trace event log tidak lagi menunjukkan pola tekel-menang-langsung-gol beruntun di depan kiper.

---

### BUG-005
**Judul**: Rasio konversi tembakan tidak realistis — berayun antara 0% dan ~100%
**Severity**: Medium — realism/balance, ditemukan bertahap lewat 3 root cause berbeda

**Cara Ditemukan**: Playtest manual lintas 10-20 match (preview aktif) dengan seed berbeda — tally manual total gol vs total tembakan dari skor akhir dan event log yang tercetak di konsol tiap match.

**Actual** (progresif, 3 iterasi):
- Iterasi 1: 0 gol dalam 20 match meski ada 100+ tembakan (0% konversi)
- Iterasi 2 (setelah fix parsial): kembali ke hampir 100% (setiap tembakan = gol otomatis)
- Iterasi 3: tembakan diblok bek sebelum sempat sampai ke gawang

**Root Cause** (3 sub-penyebab, ditemukan berurutan lewat pembacaan kode & log dari playtest yang sama):
1. Kiper melacak posisi bola **secara terus-menerus** (bukan cuma bereaksi saat ditembak), jadi selalu sudah di posisi ideal sebelum tembakan lepas — hampir mustahil dikalahkan.
2. Bek yang seharusnya "cover" malah berdiri **persis di jalur lurus** antara bola dan gawang sendiri — jadi tembakan diblok bek sebelum sempat diuji lawan kiper sama sekali.
3. Bek yang baru gagal tekel bisa langsung mencegat ulang tembakan yang baru lepas (varian dari BUG-002, tapi untuk shot bukan possession).

**Suggested Fix**:
1. Tambah randomisasi sudut & jarak tembak (`SHOT_ANGLE_SPREAD`, `SHOT_DIST_MIN/MAX`) — tembakan sekarang bisa melebar keluar gawang, tidak selalu presisi ke tengah.
2. Turunkan kecepatan reaksi kiper (dari 200 ke 100 px/s) supaya tidak selalu bisa menutup semua sudut.
3. Lepaskan posisi cover bek dari collapsing ke jalur bola — tetap di zona lateral sendiri.
4. Tambah exemption pemungutan sementara untuk bek yang baru "dilewati" tembakan (sama mekanisme dengan BUG-002).

**Fix Applied**: Ya — kombinasi `sim/config.py` (konstanta baru) dan `sim/match.py`/`sim/scripted_ai.py`
**Verification**: Regression headless 20 match setelah fix, dipakai untuk konfirmasi (bukan untuk menemukan bug-nya) — konversi tembakan naik jadi ~11% (22 gol / 198 tembakan), 15/20 match punya minimal 1 gol.

---

### BUG-006
**Judul**: Tendangan dari sudut sangat tajam di luar mulut gawang bisa "lolos" masuk tanpa halangan fisik
**Severity**: Medium — realism bug, dilaporkan langsung oleh user saat playtest video

**Cara Ditemukan**: Playtest visual — user melaporkan gol tercipta dari tendangan sudut lebar/dari samping yang secara geometris mustahil di sepak bola nyata.

**Expected**: Tembakan dari sudut tajam di luar lebar gawang seharusnya membentur tiang/dinding, bukan masuk.
**Actual**: Bola bisa "menyusur" masuk ke mulut gawang dari sudut yang secara geometris mustahil.

**Root Cause**: Tiang gawang cuma direpresentasikan sebagai ujung garis dinding tipis (10px) yang persis berada di garis gawang — tidak ada objek fisik nyata (post) yang menonjol untuk menghalangi bola dari sudut landai.

**Suggested Fix**: Tambah 4 objek fisik statis (`pymunk.Circle`, radius 9px) di tiap sudut mulut gawang dengan elastisitas tinggi (0.9) supaya bola memantul realistis kalau kena tiang.
**Fix Applied**: Ya — `sim/match.py::_build_walls` + render visual tiang di `render/draw.py`
**Verification**: Setelah fix, dijalankan test terkontrol via headless (menembakkan bola pada sudut spesifik dari luar mulut gawang) khusus untuk memastikan tiang benar-benar menghalangi — bola yang ditembak landai terdeteksi kena deflect tepat di posisi tiang (`vx` berubah drastis dari +500 ke -76.6px/s), bukan lolos masuk. Regression headless 20 match tetap sehat (13/20 ada gol, tidak ada bola/pemain macet di luar batas lapangan).

---

### BUG-007
**Judul**: Permainan terlalu terpusat di tengah lapangan, tidak ada wing play
**Severity**: Low-Medium — gameplay variety/realism, dilaporkan user

**Cara Ditemukan**: Playtest visual — user melaporkan hampir semua build-up serangan terjadi di jalur tengah sempit.

**Expected**: Variasi serangan termasuk lewat sisi lapangan (wing play), sesuai futsal/sepak bola nyata.
**Actual**: FWD (penyerang) jarang menjauh lebih dari ±80px dari titik tengah lapangan (lebar lapangan total 820px).

**Root Cause**: Formasi FWD terlalu sempit (`formation_x_offset` maksimal ±80px), dan formula target dribble (`target_x = mid_x + offset * 0.6`) menarik terlalu kuat ke tengah bahkan saat pemain sudah di posisi lebar.

**Suggested Fix**: Perlebar spacing formasi FWD, naikkan bobot posisi lateral asli saat dribble (dari 0.6 ke 0.8).
**Fix Applied**: Ya — `sim/config.py` (spacing constants) + `sim/scripted_ai.py`
**Verification**: Setelah fix, ukur standar deviasi posisi-x FWD sepanjang match lewat headless run — naik dari implisit sempit jadi 250.5px, mengonfirmasi penyebaran lateral yang jauh lebih luas.

---

### BUG-008
**Judul**: Regresi dari BUG-007 — wing play jadi terlalu ekstrem, kedua FWD sama-sama bermain di sayap
**Severity**: Low — balance tuning, ditemukan user sendiri lewat playtest video setelah fix BUG-007 di-deploy

**Cara Ditemukan**: Playtest visual — user melaporkan pasca-fix BUG-007, kedua penyerang selalu di dekat garis sisi kiri/kanan secara bersamaan, tidak ada yang jadi target sentral.

**Expected**: Satu penyerang sebagai winger (sayap), satu sebagai striker sentral — bukan dua-duanya di sayap sekaligus.
**Actual**: Formasi simetris membuat kedua FWD selalu lebar di sisi berlawanan, tidak ada opsi umpan silang ke tengah.

**Root Cause**: Fix BUG-007 melebarkan **kedua** slot FWD secara simetris tanpa diferensiasi peran.

**Suggested Fix**: Ganti jadi pairing dinamis realtime — FWD yang posisinya lebih dekat ke sisi bola saat itu otomatis jadi winger (melebar), yang satunya otomatis jadi striker tengah. Keputusan berdasarkan jarak-ke-bola (bukan identitas tetap/saling cek satu sama lain) untuk menghindari risiko osilasi (keduanya gantian wide↔center tiap frame kalau kondisinya simetris).
**Fix Applied**: Ya — `sim/scripted_ai.py`
**Verification**: Setelah fix, sampling 90 titik sepanjang 1 match lewat headless run — 28 kali terjadi perpindahan peran wide antar kedua FWD, mengonfirmasi perilaku dinamis (bukan identitas statis) tanpa oscillation runaway.

---

### BUG-009
**Judul**: Window preview terpotong taskbar Windows
**Severity**: Low — environment-specific display issue

**Cara Ditemukan**: Laporan environment user — window preview terpotong saat menjalankan `python main.py` di resolusi layar tertentu.

**Expected**: Window preview sepenuhnya terlihat.
**Actual**: Bagian bawah window tertutup taskbar Windows.

**Root Cause**: `preview_scale = 0.5` menghasilkan tinggi window 960px — terlalu tinggi untuk resolusi layar tertentu setelah dikurangi tinggi taskbar+titlebar.

**Suggested Fix**: Turunkan `preview_scale` ke 0.42 (~806px tinggi window).
**Fix Applied**: Ya — `render/preview.py`
**Verification**: Perhitungan piksel dikonfirmasi (806px vs 960px sebelumnya); diverifikasi langsung oleh user di environment-nya.

---

### BUG-010
**Judul**: Kiper dan bek saling mengoper bola berulang-ulang tanpa progres (backpass loop)
**Severity**: Medium — merusak flow pertandingan, bola macet di area sendiri tanpa build-up

**Cara Ditemukan**: Playtest manual — user melaporkan saat tim bertahan lama di bawah tekanan, kiper dan satu bek yang sama kadang saling mengoper berkali-kali berturut-turut, macet di area sendiri.

**Expected**: Operan mengarah ke opsi yang lebih maju; back-pass ke kiper tetap boleh sesekali sebagai opsi aman, bukan siklus berulang.
**Actual**: Kiper dan bek yang sama bisa saling mengoper beberapa kali berturut-turut tanpa build-up maju.

**Root Cause**: Target operan dipilih dari "teammate paling maju" (`attack_dir * posisi_y` terbesar) di `sim/match.py::_release_ball`, dan kiper ikut jadi kandidat. Bek yang sedang cover bertahan (`sim/scripted_ai.py`) bisa menempatkan diri tepat di garis gawang sendiri (`own_goal_y`, offset 0) — lebih dalam daripada posisi kiper (`COURT_Y + PLAYER_RADIUS + 20`). Saat itu terjadi, formula "paling maju" salah menganggap kiper lebih maju daripada bek tsb: bek mengoper ke kiper, kiper tidak bisa nembak dari sana jadi mengoper lagi, dan kalau bek yang sama masih di posisi paling dalam itu, siklusnya berulang.

**Suggested Fix**: Kecualikan kiper dari kandidat target operan, **hanya untuk pemain yang baru saja menerima bola dari kiper itu sendiri** (state `self.received_from_keeper`) — supaya back-pass ke kiper tetap memungkinkan sebagai opsi normal, hanya loop langsungnya yang diblokir.
**Fix Applied**: Ya — `sim/match.py` (state `received_from_keeper` + exclude bersyarat di `_release_ball`)
**Verification**: Simulasi headless dipakai untuk memastikan fix bekerja — bukan untuk menemukan bug-nya (bug ini pertama kali dilaporkan lewat playtest manual). Dijalankan 30 seed x 45 detik simulasi, mencari pola operan bolak-balik kiper↔bek yang sama (round-trip berulang dalam jendela waktu singkat): 0 ditemukan setelah fix.

---

### BUG-011
**Judul**: Bola/pemain bisa snap keluar lapangan lewat mulut gawang
**Severity**: High — merusak visual & integritas match (bola/pemain hilang dari area bermain)

**Cara Ditemukan**: Playtest manual — user melaporkan dua gejala terkait: (1) bola pembawa bola kadang snap ke luar lapangan lewat dinding atas/bawah, dan (2) pembawa bola menabrak tembok lalu stuck di situ sementara rekan FWD-nya lari keluar lapangan lewat gawang.

**Expected**: Bola dan pemain tidak pernah keluar dari batas lapangan kecuali bola yang memang sedang mencetak gol.
**Actual**: Bola yang ditempel ke pembawa bola (dribble-glue) bisa terdorong menembus dinding samping/atas/bawah; pemain FWD yang "mendorong maju di depan pembawa bola" bisa lari lurus menembus mulut gawang (yang memang sengaja dibuat terbuka secara fisik) ke area tak terbatas di belakang gawang.

**Root Cause**: Dua sub-penyebab:
1. Posisi bola saat dribble di-assign langsung (`self.ball_body.position = ...`) berdasarkan arah hadap (`facing`) pemain tanpa dibatasi ke area lapangan — kalau pemain menghadap ke arah dinding, bola ikut terdorong menembusnya.
2. Formula "FWD dorong maju di depan pembawa bola" (`target_y = posisi_y pembawa bola + attack_dir*220`) tidak dibatasi ke area lapangan, jadi saat pembawa bola sudah dekat gawang lawan, target rekannya bisa jatuh 220px **melewati** garis gawang — dan karena mulut gawang memang gap fisik terbuka (supaya bola bisa masuk), pemain yang x-nya pas di lebar mulut gawang bisa benar-benar lari menembus keluar lapangan lewat sana.

**Suggested Fix**:
1. Clamp posisi glue bola ke dalam batas lapangan (kecuali persis di lebar mulut gawang, supaya dribble-ke-gawang tetap bisa jadi gol).
2. Clamp semua `target_x`/`target_y` hasil scripted AI (untuk role apapun) ke dalam batas lapangan sebelum dipakai, di satu tempat generik alih-alih menambal tiap formula satu-satu.

**Fix Applied**: Ya — `sim/match.py::_update_possession` (clamp glue bola) + `sim/scripted_ai.py::scripted_policy` (clamp target generik di akhir fungsi)
**Verification**: Headless dipakai untuk memastikan fix bekerja (bukan menemukan bug-nya). Sebelum fix: breach dinding saat dribble ditemukan di 20 match (140 kali di dinding samping, 2172 kali di dinding atas/bawah di luar mulut gawang), plus overshoot bola sampai ratusan px saat free-flight. Setelah fix: 0 breach dinding saat dribble maupun free-flight di sampel yang sama; pemain juga tidak lagi pernah ditemukan di luar batas lapangan (0 dari 20 match x 45 detik).

---

### BUG-012
**Judul**: Nama warna tim kadang tidak cocok dengan warna yang sebenarnya tampil
**Severity**: Low — kosmetik, tapi membingungkan (papan skor/commentary bilang satu warna, yang tampil warna lain)

**Cara Ditemukan**: Playtest manual — user melaporkan warna dan teks skor/live commentary kadang tidak sesuai.

**Expected**: Label warna tim (mis. "Yellow Player 3") selalu cocok dengan warna lingkaran yang sebenarnya ditampilkan untuk pemain itu.
**Actual**: Nama warna di-generate dari hue kontinu acak lalu ditebak namanya belakangan lewat pembagian 12 bucket; hue yang jatuh dekat perbatasan dua bucket bisa dapat nama yang tidak cocok dengan bagaimana warnanya sebenarnya terlihat.

**Root Cause**: `random_team_colors()` (versi awal) memilih hue kontinu 0-1 secara acak lalu memetakan hue itu ke nama warna terdekat via pembulatan bucket (`_hue_name`) — pemetaan hue→nama ini cuma aproksimasi, bukan sumber kebenaran yang sama dengan warna yang di-generate.

**Suggested Fix**: Ganti jadi palet diskrit berisi pasangan `(nama, hue)` yang sudah didefinisikan bareng (13 warna bernama) — warna dipilih dengan memilih pasangan dari palet ini langsung (dengan jarak hue minimal 0.25 antar tim), bukan generate hue lalu menebak nama belakangan. Nama dan warna sekarang selalu berasal dari sumber yang sama persis.

**Fix Applied**: Ya — `sim/config.py::random_team_colors` (konstanta `_NAMED_HUES` + `_hue_distance`)
**Verification**: Sampling 10 seed headless — tiap pasangan nama-warna dicek cocok (mis. `Red` persis `(216,54,54)`, `Blue` persis `(54,60,216)`), dan jarak hue antar tim dalam tiap sampel selalu ≥0.25 (tidak ada dua tim dengan warna terlalu mirip).

---

## Refleksi Proses QA

- **Playtest manual sebagai sumber temuan utama** — semua bug di atas ditemukan lewat menjalankan `python main.py` secara normal (preview render aktif) dan mengamati gameplay/log konsol, bukan lewat automated headless testing.
- **Pola statistik/fairness butuh beberapa run, bukan cuma sekali main** — BUG-003 dan BUG-005 tidak akan ketemu dari 1 kali playtest; baru kelihatan setelah menjalankan beberapa match manual dengan seed berbeda dan membandingkan hasil (skor akhir, rasio tembakan/gol).
- **Headless simulation dipakai murni untuk verifikasi** — begitu fix diterapkan, match dijalankan headless (tanpa render, jauh lebih cepat) untuk regression test lintas banyak seed/match, memastikan gejalanya hilang dan tidak ada yang rusak. Headless tidak dipakai untuk menemukan bug baru di proyek ini.
- **Root cause lewat pembacaan kode & log dari playtest yang sama** — bukan instrumentasi headless terpisah; misalnya BUG-010 (backpass loop) di-root-cause dengan menelusuri formula pemilihan target operan di kode setelah pola loop-nya kelihatan dari playtest.
