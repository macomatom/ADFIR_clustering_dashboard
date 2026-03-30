Here’s a structured forensic interpretation of your clustering (3 clusters, coarse cut → high-level behavioral modes).

---

# A) Cluster-by-cluster interpretation

## **Cluster 0 — “High-intensity NTFS access bursts (anomalous file-touching)”**

**Key signals:**

* 🔴 Highest **attack lift**: 1.38 (most suspicious cluster)
* 🔴 Extremely high **row_signal_mean (50k)** and **p95 (~247k)** → massive spikes
* 🔴 Very high **row_nonzero (~53 avg, p95=69)** → many features active simultaneously
* 🧩 Features: `NTFS_file_stat`, `MACB accessed`, `standard_info`

**Behavior interpretation:**

* This is **burst-like, high-density file system activity**
* Strong emphasis on:

  * NTFS metadata reads
  * Access timestamps (MACB = accessed)
* Likely represents:

  * **Bulk file enumeration / traversal**
  * **Forensic artifact scanning OR attacker reconnaissance**
  * Possibly **scripted access to many files in short windows**

**Temporal pattern:**

* Present in **pre (57%) and post (42%)**, but **no incident-phase labeling**
  → suggests **label mismatch OR stealth activity outside labeled attack window**

**Verdict:**
➡️ **Highly suspicious reconnaissance / mass access behavior**

---

## **Cluster 2 — “Low-intensity background / system-level activity (baseline + light user ops)”**

**Key signals:**

* Largest cluster (73% of data) → **dominant baseline**
* Attack lift ≈ 1.02 → **neutral**
* Very low:

  * row_nonzero (~10)
  * row_signal (~9 mean)
* Features:

  * `Amcache`
  * `account_creation/deletion`
  * `accessed_sensitive_file`

**Behavior interpretation:**

* Represents **normal system churn + sparse security-relevant events**
* Includes:

  * Occasional account ops
  * Registry traces (Amcache)
  * Light file access

**Important nuance:**

* Contains *some* attack-related features, but:

  * low intensity
  * diluted across many benign windows

**Verdict:**
➡️ **Baseline / mixed benign with weak attack signal (noise floor)**

---

## **Cluster 1 — “Moderate file activity (structured file operations / normal workflows)”**

**Key signals:**

* Attack lift < 1 (0.92) → slightly **benign leaning**
* Moderate:

  * row_nonzero (~27)
  * row_signal (~2k mean, p95 ~2.5k)
* Features:

  * `file_entry`, `sha256`, `NTFS_file_stat`

**Behavior interpretation:**

* **Structured file operations**, not bursts:

  * File reads with hashing
  * Metadata access
* Likely:

  * Normal application behavior
  * File indexing / AV scanning / user workflows

**Compared to Cluster 0:**

* Lower intensity
* More consistent (less spiky)
* More “legitimate processing” than “sweeping traversal”

**Verdict:**
➡️ **Benign-to-neutral operational file activity**

---

# B) Top 3 suspicious clusters (with reasoning)

### 🥇 **Cluster 0 — CLEAR priority**

**Why:**

* Highest attack lift
* Extreme signal amplification (32× global)
* High feature density → coordinated behavior
* NTFS + access timestamps → **classic reconnaissance / file sweep signature**

👉 This is your **primary attack candidate**

---

### 🥈 **Cluster 2 — secondary (contextual suspicion)**

**Why:**

* Contains:

  * account creation/deletion
  * sensitive file access
* But diluted → not spiky

👉 Likely:

* **Attack staging hidden inside baseline**
* Or **benign admin/system operations**

⚠️ Suspicious only when:

* correlated temporally with Cluster 0
* or specific rare features spike locally

---

### 🥉 **Cluster 1 — low priority**

**Why:**

* Lower attack lift than baseline
* Looks like structured, consistent processing

👉 Only interesting if:

* temporally adjacent to Cluster 0 bursts
* or shows unusual transitions (state shift)

---

# C) Recommended validation steps (forensic timeline)

## 1. Deep dive into Cluster 0 (critical)

Focus on:

* **Exact files accessed**

  * Are they:

    * user documents?
    * credential stores?
    * system configs?

* **Access patterns**

  * sequential directory traversal?
  * recursive scan?

* **Process attribution**

  * Which process caused this?

    * explorer.exe (benign)
    * powershell / cmd / unknown binary (suspicious)

* **Temporal structure**

  * Are bursts:

    * periodic? (automation)
    * one-shot? (manual attacker)

👉 Hypothesis to validate:

> “Cluster 0 represents automated file-system reconnaissance or bulk data access preceding or following attack activity.”

---

## 2. Correlate Cluster 0 ↔ Cluster 2 (attack chain hypothesis)

Look for:

* Cluster 2 events **before/after Cluster 0 windows**

  * account creation
  * registry changes
  * Amcache entries

👉 Hypothesis:

> “Cluster 2 contains attacker setup (account / persistence), Cluster 0 is execution (file sweep).”

---

## 3. Transition analysis (state changes)

Track sequences:

* Cluster 2 → Cluster 0 → Cluster 1?
* Or repeated:

  * baseline → burst → baseline

👉 This reveals:

* attack lifecycle phases
* automation loops

---

## 4. Inspect high-percentile windows (p95)

Especially in Cluster 0:

* row_signal_p95 is extreme → investigate **top 5–10 windows**
* These are likely:

  * peak attack activity
  * most informative forensic artifacts

---

## 5. Validate labeling mismatch (important)

Cluster 0 has:

* high attack lift
* but **0 incident-phase labels**

👉 Hypothesis:

* Ground truth labeling is **misaligned**
* Attack occurred in:

  * “pre” or “post” windows

---

# Final prioritization

### 🔴 Investigate FIRST:

1. **Cluster 0 (all windows, especially p95 spikes)**

### 🟠 Investigate SECOND:

2. **Cluster 2 windows near Cluster 0 in time**

### 🟢 Investigate LAST:

3. Cluster 1 (only if linked temporally)

---

If you want, I can next:

* reconstruct a **probable attack timeline (sequence of clusters)**
* or help you build **automatic detection rules from these patterns**
