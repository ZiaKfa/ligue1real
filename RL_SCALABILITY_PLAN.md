# Rencana Skalabilitas AI (RL) — Futsal Sim

Dokumen ini adalah hasil review arsitektur `main.py` saat ini terhadap kebutuhan pengembangan AI lanjutan (RL atau metode lain), plus rencana bertahap untuk sampai ke sana. Tidak ada kode yang diubah oleh dokumen ini — ini murni planning.

---

## 1. Ringkasan Kondisi Saat Ini

**File**: `main.py`, 645 baris, satu class `FutsalMatch` (12 method) + `draw_frame()` + `main()`.

### Yang sudah menguntungkan (fondasi kuat, tidak perlu dirombak)

| Aspek | Status | Bukti |
|---|---|---|
| Physics loop decoupled dari rendering | ✅ Sudah | `FutsalMatch.step(dt)` ([main.py:309](main.py#L309)) tidak memanggil pygame sama sekali — sudah terbukti bisa dipanggil headless ratusan kali berturut-turut selama development sesi ini. |
| Seed deterministik | ✅ Sudah | `FutsalMatch(seed=...)` di [main.py:89-91](main.py#L89-L91). |
| Titik ganti AI sudah diantisipasi | ✅ Sudah | `choose_action(self, player)` ([main.py:205](main.py#L205)) terisolasi per-pemain, docstring-nya secara eksplisit bilang "swap this out for RL policy." |
| State match self-contained | ✅ Sudah | Semua state ada di instance `FutsalMatch` (`self.score`, `self.possessor`, dll) — tidak ada state global tersembunyi selain `random` module-level. |

### Yang jadi hambatan

| # | Masalah | Lokasi | Dampak ke RL |
|---|---|---|---|
| 1 | Semua concern (physics, AI scripted, render, main loop) ada di satu file | `main.py` seluruhnya | Env RL akan butuh `import` `FutsalMatch` tanpa ikut narik dependency pygame window — bisa tapi kotor kalau tetap 1 file. |
| 2 | `main()` dipaksa real-time | [main.py:574](main.py#L574) — `clock.tick(FPS)`, window preview selalu dibuat | Training butuh run jauh lebih cepat dari 30fps; belum ada jalur headless-only. |
| 3 | `choose_action` tidak punya slot action eksternal | [main.py:205](main.py#L205) | Semua pemain (GK/BACK/FWD) selalu jalanin heuristic yang sama; belum ada cara bilang "pemain ini dikontrol model." |
| 4 | Belum ada observation/reward/Gym interface | — | Ini memang kerjaan baru yang belum pernah dibutuhkan sebelumnya, wajar belum ada. |
| 5 | `random` module-level global dipakai luas | Banyak tempat (tackle, shot spread, fumble, dll) | Aman untuk 1 proses per env (SubprocVecEnv), tapi jadi masalah kalau nanti threading dalam 1 proses. |
| 6 | Reward signal alami (skor) sudah ada tapi belum diekspos sebagai reward per-step | `self.score` di [main.py:96](main.py#L96) | Perlu dihitung delta antar step, bukan langsung dipakai. |

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

### Fase 0 — Refactor Pemisahan Concern
**Tujuan**: memecah `main.py` tanpa mengubah perilaku sama sekali, supaya siap dijadikan dependency oleh env RL.

**Struktur file yang diusulkan**:
```
futsal_sim/
├── sim/
│   ├── __init__.py
│   ├── config.py          # semua CONFIG constants (baris 28-83 sekarang)
│   ├── match.py           # class FutsalMatch (physics + game logic, tanpa AI heuristic)
│   └── scripted_ai.py     # choose_action() sekarang, jadi fungsi/strategy yang di-inject ke FutsalMatch
├── render/
│   ├── __init__.py
│   ├── draw.py            # draw_frame()
│   └── preview.py         # loop main() sekarang (window + ffmpeg pipe)
├── main.py                # entrypoint tipis: bikin FutsalMatch + scripted_ai, panggil render/preview
└── requirements.txt
```

**Tugas konkret**:
1. Pindahkan block `CONFIG` ke `sim/config.py`, import di tempat lain.
2. Pindahkan `choose_action` keluar dari `FutsalMatch` jadi fungsi berdiri sendiri `scripted_policy(match, player) -> (dx, dy)`, lalu `FutsalMatch.step()` menerima parameter `policy_fn` (default `scripted_policy`) — ini titik seam paling penting untuk Fase 2.
3. Pindahkan `draw_frame` + loop pygame dari `main()` ke `render/preview.py`.
4. Tambah entrypoint `main.py --headless` (atau file terpisah `run_headless.py`) yang cuma manggil `FutsalMatch` + loop `step()` tanpa pygame sama sekali — berguna untuk smoke-test kecepatan simulasi murni.
5. **Acceptance criteria**: semua behavior/test manual yang sudah divalidasi sepanjang sesi ini (gol, tackle, stun, selebrasi, kickoff) harus identik setelah refactor — jalankan ulang skrip-skrip test headless yang sudah dipakai sesi ini sebagai regression check.

**Estimasi**: pekerjaan mekanis, risiko rendah, tidak butuh keputusan desain baru.

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
