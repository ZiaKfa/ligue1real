# Rencana Skalabilitas AI (RL) — Futsal Sim

Dokumen ini adalah hasil review arsitektur kode saat ini terhadap kebutuhan pengembangan AI lanjutan (RL atau metode lain), plus rencana bertahap untuk sampai ke sana.

---

## 0. Riwayat Versi

| Versi | Konteks | Perubahan |
|---|---|---|
| v1.0 | Draft awal (sebelum ada kode dieksekusi dari plan ini) | Review kondisi single-file `main.py` (645 baris), rekomendasi pendekatan (single-agent → shared-policy self-play, PPO/SB3), 6 fase (Fase 0-5), guardrail YAGNI. Semua isi §1-6 di bawah adalah versi awal ini. |
| v1.1 | Setelah **Fase 0 dieksekusi & diverifikasi** | `main.py` sudah dipecah jadi `sim/` + `render/` + entrypoint tipis sesuai rencana Fase 0. Tabel "hambatan" di §1 dan blok Fase 0 di §3 diperbarui dengan status & lokasi kode terbaru (bukan lagi proposal, tapi hasil nyata + hasil regression test). Detail lengkap ada di §3 → "Fase 0 — Hasil Eksekusi". |
| v1.2 | Estimasi waktu training (tebakan awal) | Tambah tabel estimasi waktu training kasar (timestep & wall-clock) di §3 Fase 3, sebagai perkiraan awal sebelum ada benchmark nyata. |
| v1.3 (saat ini) | **Benchmark throughput nyata dijalankan** | Ukur langsung `FutsalMatch.step()` headless pakai `multiprocessing` (1/4/8/12 proses paralel) di hardware ini (12 logical CPU, Windows) — hasil: 3.934 env-frame/detik single-core, naik ke 14.829/detik di 12 proses (scaling tidak linear). Tabel estimasi waktu training di §3 Fase 3 diperbarui pakai angka nyata ini (jauh lebih cepat dari tebakan v1.2), dengan catatan jelas belum termasuk overhead PPO. |
| v1.4 (sekarang) | **Klarifikasi kontrak RL dan batas benchmark** | Status fase diperbarui: Fase 0 selesai, Fase 1 menjadi langkah aktif. Episode baseline ditetapkan satu half, kontrak observation/action/reward diperjelas, evaluasi diperketat, dan benchmark physics tidak lagi dipakai sebagai estimasi waktu training final. |

---

## 1. Ringkasan Kondisi Saat Ini

**File** *(kondisi v1.0, sebelum Fase 0)*: `main.py`, 645 baris, satu class `FutsalMatch` (12 method) + `draw_frame()` + `main()`.

**File** *(kondisi v1.1, setelah Fase 0 — lihat §3 untuk detail)*: dipecah jadi `sim/config.py`, `sim/match.py`, `sim/scripted_ai.py`, `render/draw.py`, `render/preview.py`, dan `main.py` (24 baris, entrypoint tipis).

### Yang sudah menguntungkan (fondasi kuat, tidak perlu dirombak)

| Aspek | Status | Bukti |
|---|---|---|
| Physics loop decoupled dari rendering | ✅ Sudah (v1.0) | `FutsalMatch.step(dt)` tidak memanggil pygame sama sekali — sudah terbukti bisa dipanggil headless ratusan kali berturut-turut selama development. |
| Seed deterministik | ✅ Sudah (v1.0) | `FutsalMatch(seed=...)`. |
| Titik ganti AI sudah diantisipasi | ✅ Sudah (v1.0), **dieksekusi di v1.1** | Dulu: `choose_action(self, player)` terisolasi per-pemain dengan docstring "swap this out for RL policy." Sekarang: benar-benar sudah dipisah jadi `scripted_policy(match, player)` di [sim/scripted_ai.py](sim/scripted_ai.py), dan `FutsalMatch(policy_fn=...)` di [sim/match.py](sim/match.py) menerima fungsi pengganti — sudah diverifikasi bisa nyuntik action eksternal ke 1 pemain spesifik tanpa ubah `match.py`. |
| State match self-contained | ✅ Sudah (v1.0) | Semua state ada di instance `FutsalMatch` (`self.score`, `self.possessor`, dll) — tidak ada state global tersembunyi selain `random` module-level. |

### Yang jadi hambatan

| # | Masalah | Status v1.1 | Dampak ke RL |
|---|---|---|---|
| 1 | Semua concern (physics, AI scripted, render, main loop) ada di satu file | ✅ **Selesai (Fase 0)** — sekarang `sim/` (physics+AI) terpisah total dari `render/` (pygame). `import sim` tidak lagi ikut narik pygame window. | Env RL sekarang bisa `from sim import FutsalMatch` bersih tanpa dependency render. |
| 2 | `main()` dipaksa real-time, belum ada jalur headless | ⚠️ **Sebagian** — `sim/match.py` sudah 100% headless-callable (sudah dipakai lewat script test langsung tanpa pygame), tapi belum ada entrypoint/flag `--headless` khusus yang jadi convenience wrapper. Item ini sengaja ditunda karena Fase 2 (env wrapper) akan butuh pola importnya sendiri — bikin `run_headless.py` sekarang kemungkinan akan ditulis ulang lagi nanti. | Training tetap bisa mulai (langsung `import sim`), cuma belum ada script siap-pakai untuk smoke-test kecepatan simulasi murni. |
| 3 | `choose_action` tidak punya slot action eksternal | ✅ **Selesai (Fase 0)** — `FutsalMatch.__init__(..., policy_fn=None)` di [sim/match.py](sim/match.py), default `scripted_policy`. Diverifikasi: policy custom bisa override 1 pemain spesifik, sisanya tetap scripted. | Titik seam Fase 2 sudah siap pakai, tidak perlu kerjaan tambahan di sini. |
| 4 | Belum ada observation/reward/Gym interface | ⏳ Belum (rencana Fase 1-2) | Kerjaan baru yang memang belum pernah dibutuhkan sebelumnya. |
| 5 | `random` module-level global dipakai luas | ⏳ Belum disentuh | Sekarang tersebar di [sim/match.py](sim/match.py) (tackle, shot spread, fumble, dll). Aman untuk 1 proses per env (SubprocVecEnv), tapi jadi perhatian kalau nanti threading dalam 1 proses. |
| 6 | Reward signal alami (skor) sudah ada tapi belum diekspos sebagai reward per-step | ⏳ Belum (rencana Fase 1-2) | `self.score` di [sim/match.py](sim/match.py) — perlu dihitung delta antar step, bukan langsung dipakai. |

---

## 2. Rekomendasi Pendekatan

**Jangan langsung lompat ke multi-agent self-play penuh** meskipun README menyebutnya sebagai rencana akhir. Urutan yang direkomendasikan, dari yang paling murah dibuktikan:

1. **Single-agent dulu** — latih 1 pemain (misal 1 FWD) lawan sisanya yang tetap scripted AI (kode `choose_action` yang sudah ada, tidak dibuang). Ini membuktikan seluruh pipeline (env wrapper, observation, reward, training loop) bekerja dengan permukaan risiko paling kecil.
2. **Baru naik ke shared-policy self-play** — 1 policy mengontrol semua pemain outfield di satu tim (persis rencana original README), setelah baseline single-agent terbukti menang lawan scripted AI.
3. **Multi-policy per role / komunikasi antar-agent** — hanya kalau shared-policy self-play mentok. Jangan dibangun di awal (YAGNI).

**Algoritma**: PPO via **Stable-Baselines3**. Alasan: standar, robust terhadap reward yang belum sempurna, dokumentasi/komunitas besar, dan ini juga yang sudah disebut README sebelumnya — tidak perlu eksplorasi algoritma eksotis di tahap awal.

**Action space**: pertahankan bentuk `(dx, dy)` continuous, identik dengan return value `choose_action` sekarang. Ini bikin translation layer dari action model → physics jadi hampir 1:1, minim kerja tambahan.

**Observation space (usulan awal, kecil dan cukup)**:
- Posisi & velocity pemain sendiri (relatif terhadap tengah lapangan)
- Posisi & velocity bola
- Posisi relatif teman & lawan terdekat (bukan semua pemain — biar observation tidak membengkak)
- Jarak & arah ke gawang lawan
- Flag: apakah sedang possess bola

**Reward (usulan awal)**: sparse dulu (`+1` gol tim, `-1` kebobolan), baru tambah shaping (dekat bola, tembakan on-target, dll) **kalau** training terbukti stuck dengan sparse reward. Jangan desain reward shaping rumit di depan sebelum ada bukti butuh.

---

## 3. Rencana Bertahap

### Fase 0 — Refactor Pemisahan Concern ✅ SELESAI (v1.1)
**Tujuan**: memecah `main.py` tanpa mengubah perilaku sama sekali, supaya siap dijadikan dependency oleh env RL.

**Struktur file final** (sedikit beda dari proposal awal — tanpa folder pembungkus `futsal_sim/`, karena `sim/`/`render/` memang sudah cukup diletakkan langsung di root project yang sudah ada):
```
sim/
├── __init__.py         # re-export FutsalMatch, scripted_policy
├── config.py           # semua CONFIG constants
├── match.py            # class FutsalMatch (physics + game logic), terima policy_fn
└── scripted_ai.py       # scripted_policy(match, player) -> (dx, dy)
render/
├── __init__.py
├── draw.py             # draw_frame()
└── preview.py          # run_preview(match) - loop pygame + placeholder ffmpeg
main.py                  # entrypoint tipis (24 baris)
```

**Tugas yang selesai**:
1. ✅ Block `CONFIG` dipindah ke `sim/config.py`.
2. ✅ `choose_action` dipindah keluar dari `FutsalMatch` jadi `scripted_policy(match, player)` di `sim/scripted_ai.py`. `FutsalMatch.__init__` menerima `policy_fn=None` (default `scripted_policy`), `step()` memanggil `self.policy_fn(self, p)`.
3. ✅ `draw_frame` + loop pygame dipindah ke `render/draw.py` + `render/preview.py::run_preview(match)`.
4. ❌ **Belum dikerjakan**: entrypoint/flag `--headless` khusus. Sengaja ditunda — lihat catatan hambatan #2 di §1 (kemungkinan akan ditulis ulang begitu Fase 2/3 punya kebutuhan konkret, jadi belum dibuat sekarang biar tidak dobel kerja).
5. ✅ **Acceptance criteria terpenuhi** — regression test headless (10 match penuh lewat `from sim import FutsalMatch`) menghasilkan pola skor & rate gol yang konsisten dengan sebelum refactor; fitur detail (tackle, stun, keeper slip, pass, shoot, goal, selebrasi berkumpul, kickoff ke tim yang kebobolan) semua dikonfirmasi masih berfungsi identik lewat trace event log.
6. ✅ **Bonus — titik seam Fase 2 sudah diverifikasi**: `policy_fn` custom yang meng-override 1 pemain spesifik (return velocity tetap/fixed, meniru `model.predict(obs)`) berhasil dijalankan berdampingan dengan 9 pemain lain yang tetap pakai `scripted_policy`, tanpa perlu ubah `sim/match.py` sama sekali.

**Hasil**: risiko rendah seperti diperkirakan, tidak ada keputusan desain baru yang dibutuhkan di luar rencana awal.

---

### Fase 1 — Desain Interface RL (dokumen, bukan kode)
**Tujuan**: menetapkan kontrak observation/action/reward sebelum menulis wrapper env, supaya Fase 2 tidak bolak-balik redesign.

**Tugas konkret**:
1. Tulis spesifikasi observation vector per pemain (urutan field, normalisasi — misal posisi dinormalisasi ke [-1,1] relatif ukuran lapangan).
2. Tulis spesifikasi action space: `Box(low=-1, high=1, shape=(2,))` untuk `(dx, dy)` yang di-scale ke speed pemain di dalam env.
3. Tulis rumus reward: `reward = (score_delta_tim_dikontrol - score_delta_tim_lawan)` per step, plus catatan kapan boleh nambah shaping.
4. Tentukan `episode length` / kondisi `terminated` vs `truncated` (mis. `truncated` di `match_clock >= MATCH_SECONDS`, `terminated` tidak pernah true kecuali mau ada "game over" eksplisit).

**Acceptance criteria**: dokumen spesifikasi (bisa nambahan di file ini) yang disetujui sebelum lanjut Fase 2.

---

### Fase 2 — Gymnasium Environment Wrapper
**Tujuan**: satu-satunya kerja kode yang benar-benar baru; semua yang lain reuse.

**Tugas konkret**:
1. Tambah `sim/env.py`:
   ```python
   class FutsalEnv(gymnasium.Env):
       def reset(self, seed=None, options=None):
           self.match = FutsalMatch(players_per_team=5, seed=seed)
           self.controlled_player = self.match.players[<index yang dipilih>]
           return self._get_obs(), {}

       def step(self, action):
           self.match.external_action = action  # slot baru yang dibaca scripted_policy/wrapper policy
           for _ in range(STEPS_PER_FRAME):
               self.match.step(dt / STEPS_PER_FRAME)
           obs = self._get_obs()
           reward = self._compute_reward()
           truncated = self.match.match_clock >= MATCH_SECONDS
           return obs, reward, False, truncated, {}
   ```
2. Modifikasi titik seam di `scripted_ai.py` / `FutsalMatch.step()`: kalau `player is self.controlled_player`, pakai `self.external_action` alih-alih heuristic; pemain lain tetap `scripted_policy`.
3. Tulis `_get_obs()` dan `_compute_reward()` sesuai spesifikasi Fase 1.
4. Test manual: `env.reset()` → beberapa `env.step(random_action)` → pastikan tidak crash, obs shape konsisten, reward masuk akal (mis. reward naik pas gol beneran kejadian).

**Acceptance criteria**: `stable_baselines3.common.env_checker.check_env(FutsalEnv())` lolos tanpa warning fatal.

---

### Fase 3 — Infrastruktur Training
**Tugas konkret**:
1. `train.py`: PPO dari Stable-Baselines3, `SubprocVecEnv` dengan N environment paralel (N = jumlah core CPU yang tersedia, karena pymunk single-threaded per proses).
2. Logging TensorBoard bawaan SB3 (`tensorboard_log=...`), track: episode reward, gol dicetak, gol kebobolan, win-rate.
3. Callback checkpoint periodik (`CheckpointCallback` dari SB3) supaya training bisa di-resume.
4. `eval.py`: jalankan N episode policy terlatih lawan `scripted_policy` baseline, laporkan win-rate — ini jadi "regression test" resmi untuk validasi tiap iterasi model baru.

**Acceptance criteria**: training berjalan tanpa crash minimal 1 juta timestep, win-rate eval > 50% lawan scripted AI baseline (baseline paling rendah untuk bilang "policy belajar sesuatu").

**Benchmark throughput nyata** (dijalankan langsung di hardware ini, 12 logical CPU, Windows — bukan tebakan lagi): mengukur `FutsalMatch.step()` murni headless (tanpa pygame, tanpa PPO) pakai `multiprocessing`, meniru cara kerja `SubprocVecEnv`:

| Jumlah proses paralel | Throughput agregat | Per-proses |
|---|---|---|
| 1 | 3.934 env-frame/detik | 3.934/detik |
| 4 | 10.227 env-frame/detik | 2.557/detik |
| 8 | 13.152 env-frame/detik | 1.644/detik |
| 12 | 14.829 env-frame/detik | 1.236/detik |

Scaling tidak linear (diminishing return lewat 4 proses — indikasi core fisik lebih sedikit dari 12, sisanya hyperthread/contention memori). **Penting**: ini throughput fisika+AI murni, BELUM termasuk overhead PPO (forward/backward pass jaringan, hitung observation/reward, GAE, dsb.) yang baru ada begitu Fase 2 selesai — jadi ini batas atas (best case), bukan angka final training.

**Estimasi waktu training** (pakai throughput 12-proses di atas sebagai basis, dengan diskon 30-70% untuk overhead PPO yang belum terukur):

| Target | Timestep dibutuhkan | Estimasi waktu* |
|---|---|---|
| Policy "melakukan sesuatu yang masuk akal" (bukan random) | ~500rb - 2 juta | ~1-7 menit |
| Single-agent vs scripted AI, menang konsisten (target Fase 3) | ~2-10 juta | ~4-33 menit |
| Shared-policy self-play (Fase 4, semua pemain 1 tim) | Jauh lebih banyak — self-play kurang stabil karena lawan ikut belajar (moving target) | Bisa berjam-jam sampai berhari-hari |

\* Jauh lebih cepat dari perkiraan awal (v1.2) — simulasinya ternyata sangat ringan (pymunk dengan 10 circle kecil, tanpa rendering). Yang paling menentukan angka final: overhead PPO yang sebenarnya (baru terukur begitu Fase 2 selesai), reward shaping, dan definisi "cukup baik" (menang 51% vs 90% beda jauh). **Langkah selanjutnya**: begitu Fase 2 (env wrapper) selesai, ulangi benchmark ini dengan PPO asli (bukan cuma physics step) untuk dapat angka final yang akurat.

---

### Fase 4 — Iterasi: Self-Play & Curriculum
**Tugas konkret** (hanya dikerjakan setelah Fase 3 terbukti berhasil):
1. Ubah `FutsalEnv` supaya `controlled_player` bisa berupa list (semua outfield 1 tim), 1 policy dipanggil per pemain — shared-policy self-play sesuai rencana README asli.
2. Opsional — curriculum: mulai lawan scripted AI yang dilemahkan (matiin `STUN_CHANCE`/`SHOT_ANGLE_SPREAD` acak, atau turunkan `back_count` pressing), naikkan bertahap ke full scripted AI.
3. Opsional — self-play lawan snapshot versi model sebelumnya (bukan cuma scripted AI), untuk menghindari policy overfit ke satu jenis lawan.

**Catatan**: bagian ini sengaja tidak dirinci detail dulu — keputusan konkretnya baru masuk akal setelah lihat hasil Fase 3.

---

### Fase 5 — Reuse Pipeline Video untuk Showcase
**Tugas konkret**:
1. Di `render/preview.py`, tambah opsi: untuk tim yang dikontrol, panggil `model.predict(obs)` alih-alih `scripted_policy`; tim lawan tetap scripted AI.
2. Tidak ada kerjaan render baru — pipeline pygame + (nanti) ffmpeg export yang sudah ada dipakai apa adanya, ini memang sudah dirancang untuk itu sejak awal (lihat docstring `main.py` baris 15-16).

**Acceptance criteria**: bisa hasilkan video match dengan minimal 1 tim dikontrol model terlatih, tanpa mengubah kode rendering.

---

## 4. Yang Sengaja Ditunda (Guardrail YAGNI)

Supaya tidak over-engineer di awal, berikut yang **jangan** dikerjakan sampai ada bukti nyata dibutuhkan:

- Multi-policy per role (GK/BACK/FWD punya model terpisah)
- Komunikasi eksplisit antar-agent (message passing)
- Domain randomization otomatis (randomize fisik/parameter tiap episode)
- Reward shaping kompleks (banyak komponen tertimbang)
- Algoritma RL selain PPO (SAC, TD3, dll) — PPO cukup untuk mulai
- Curriculum learning otomatis/adaptif — mulai manual dulu

---

## 5. Dependency Tambahan yang Dibutuhkan

```
gymnasium>=0.29
stable-baselines3>=2.0
tensorboard
```
(Ditambahkan ke `requirements.txt` baru pada Fase 2/3, belum sekarang — sesuai prinsip "jangan install dependency sebelum benar-benar dipakai.")

---

## 6. Urutan Eksekusi yang Disarankan

Mulai dari **Fase 0** (refactor pemisahan file) — risiko rendah, tidak butuh keputusan desain baru, dan jadi prasyarat keras untuk semua fase setelahnya. Fase 1 (spesifikasi) bisa ditulis paralel sambil Fase 0 jalan. Jangan mulai Fase 2 sebelum Fase 0 selesai dan tervalidasi (behavior gameplay tetap identik).

**Status saat ini (v1.4)**: Fase 0 ✅ selesai & tervalidasi. Fase 1 adalah langkah aktif berikutnya: tetapkan kontrak observation/action/reward dan aturan episode, baru lanjut ke Fase 2 (Gym env wrapper).
