A) **Concise cluster-by-cluster interpretation**

Below I treat **attack_lift_vs_global** as enrichment, not proof of attack onset, and I weigh it together with **row_nonzero** and especially **row_signal**. In practice, the most interesting clusters are the ones that combine either high enrichment with distinctive behavior, or low enrichment but extremely atypical intensity that may reflect rare but important system activity.

**Cluster 16**
Single-row **post-phase micro-cluster**, extremely attack-enriched (**lift 7.19**) but with only **moderately high row_nonzero (40)** and **very low row_signal lift (0.15)**. Features are entropy spikes, temp/spool, and policy change.
**Likely mode:** a very localized post-compromise configuration or staging event rather than broad filesystem churn.
**Interpretation:** because the signal magnitude is not high, this looks less like mass activity and more like a **specific control/policy or transient workspace action**. The combination of `is_in_temp_or_spool` and `is_policy_change` makes it notable despite being just one row.

**Cluster 4**
Tiny cluster (**n=5**) with very strong enrichment (**lift 5.75**) and **high row_nonzero (57.2)** plus **elevated row_signal (lift 1.19, p95 6216.8)**. Features are strongly file-centric: `is_file_entry`, `has_sha256`, `is_file`, `is_ntfs`, `mask_File_stat`.
**Likely mode:** **artifact-heavy file object processing**, probably a small set of windows dominated by concentrated file creation/modification/hashable file presence.
**Interpretation:** suspicious because it is both enriched and semantically coherent around concrete file entities. This looks like a **compact file-operation micro-pattern** that could align with payload drops, archive expansion, staging, or selective file manipulation.

**Cluster 7**
Small cluster (**n=9**) with moderate enrichment (**lift 2.40**), very high structural complexity (**row_nonzero lift 3.84**) and clearly high signal (**row_signal lift 3.20**). Features mix `WinEVTX`, user-dir activity, NTFS stats, AppData, and MACB accessed.
**Likely mode:** **user-profile/AppData event-log correlated activity**.
**Interpretation:** this is a strong candidate for **user-context execution or persistence-related behavior** because AppData + user directory + event log traces often appear around launched tooling, installers, user-space malware, or post-execution logging.

**Cluster 8**
Very small (**n=3**), same enrichment as cluster 7 (**lift 2.40**), high row_nonzero (**57.3**) and **very high row_signal lift (6.86)**. Features are NTFS standard info in users/AppData.
**Likely mode:** **intense AppData NTFS metadata bursts** in a few isolated windows.
**Interpretation:** stronger than cluster 7 in raw intensity, but with fewer rows and less semantic diversity. This feels like a **sharp metadata-heavy spike in user-space files**, consistent with bursty install/extract/execute behavior in AppData.

**Cluster 1**
Moderate-sized small cluster (**n=15**) with enrichment (**lift 1.92**) and **extremely high row_signal lift (12.51)**. Features mix NTFS file stat, MACB accessed/modified, standard info, and registry key traces.
**Likely mode:** **heavy mixed filesystem + registry churn**.
**Interpretation:** one of the clearest “rare but meaningful” behaviors. This is not just many active features; it is **very intense activity across file metadata and registry artifacts**, which often aligns with software installation, persistence changes, execution side effects, or cleanup.

**Cluster 13**
Small cluster (**n=16**) with mild enrichment (**lift 1.35**) but **very high row_signal lift (8.96)** and high row_nonzero (**3.31 lift**). Features are user-dir, AppData, NTFS, file stat.
**Likely mode:** **sustained user-space file-system churn**.
**Interpretation:** less attack-enriched than clusters 1/4/7/8, but behaviorally very distinct. This could be either **benign application activity in AppData** or attacker tooling living in user-space. Needs timeline context.

**Cluster 12**
Tiny cluster (**n=6**) with slight enrichment (**lift 1.20**) but **very high row_signal lift (10.93)** and elevated row_nonzero. Features are NTFS/file/stat/file-entry/standard-info.
**Likely mode:** **rare, intense file metadata bursts**.
**Interpretation:** not strongly attack-enriched, but behaviorally unusual enough to deserve attention. Likely a small number of windows where many file objects changed quickly.

**Cluster 14**
Large minority cluster (**n=423**) with slight enrichment (**lift 1.17**) but **very low row_nonzero (0.69 lift)** and almost no signal lift (**0.016**). Features are dominated by entropy spike/diff measures.
**Likely mode:** **low-content entropy-shift background windows**.
**Interpretation:** probably a broad class of relatively sparse windows that got grouped because of entropy-derived dynamics rather than rich artifact presence. Slight enrichment may simply reflect that some compromised-state windows are quiet or transitional. Usually lower priority.

**Cluster 10**
The dominant baseline cluster (**n=3041**, 64.1% of data), essentially global average attack rate (**lift 1.00**), low row_nonzero and extremely low row_signal. Features include `accessed_sensitive_docs`, `account_creation`, `account_deletion`, `accessed_sensitive_file`, `HasAandBNoMC`, which is likely due to prevalence rather than distinctiveness.
**Likely mode:** **background/common operating state**.
**Interpretation:** this is your main benign/default cluster unless source-row review shows hidden subclasses. It is too broad and behaviorally weak to prioritize.

**Cluster 2**
Mid-sized (**n=147**) with slightly below-average enrichment (**lift 0.93**) but **high row_nonzero lift (2.51)** and **very high row_signal lift (8.82)**. Features are classic NTFS/file/stat/file-entry/standard-info.
**Likely mode:** **intense filesystem metadata activity spanning many windows**.
**Interpretation:** despite below-average attack enrichment, this is behaviorally one of the most important clusters. It may represent **large-scale benign file processing**, but it could also capture attacker-adjacent activity that the compromised-state label misses. Worth reviewing because the label is imperfect.

**Cluster 6**
Large cluster (**n=1018**) with slightly below-average enrichment (**lift 0.90**), moderate row_nonzero (**1.66 lift**), low row_signal (**0.08 lift**), and entropy spikes plus `event_powershell` and NTFS event.
**Likely mode:** **broad low-intensity script/event-related background activity**.
**Interpretation:** the presence of PowerShell is notable, but the cluster is too large and too low-intensity to read as inherently malicious. More likely this is a **mixed background scripting/administrative/event telemetry class**. Only escalate if timeline proximity or command content supports it.

**Cluster 0**
Smallish (**n=34**) with below-average enrichment (**lift 0.85**) but **high row_nonzero (3.52 lift)** and **very high row_signal (8.59 lift)**. Features are NTFS/file/file-entry.
**Likely mode:** **dense file-entry bursts**, similar family to clusters 2/12.
**Interpretation:** behaviorally unusual, label-wise not enriched. This is a good example of why the compromised-state label should not dominate interpretation. Could be benign bulk file operations, but also could hide staging or packaging activity outside labeled windows.

**Cluster 3**
Small (**n=21**) with low enrichment (**lift 0.68**) but **extreme row_signal mean 186,818** and **signal lift 120.69**, by far the most intense cluster. Features are NTFS/file stat/MACB accessed/standard info.
**Likely mode:** **extreme filesystem surge / bulk-touch event**.
**Interpretation:** this is the most behaviorally abnormal cluster in the whole table. Even though attack enrichment is low, this could reflect **backup, indexing, extraction, copy, AV scan, or mass file access/modification**. It absolutely needs validation because intensity this high can mask both benign heavy maintenance and attacker mass operations.

**Cluster 5**
Tiny (**n=3**) with zero attack rows, but high row_nonzero (**3.93 lift**) and high row_signal (**6.93 lift**). Features include NTFS, WinEVTX, MACB accessed.
**Likely mode:** **rare event-log + filesystem crossover burst**.
**Interpretation:** probably a benign but uncommon system action, though still worth a quick check because tiny zero-attack clusters can be unlabeled precursors or aftermaths.

**Cluster 9**
Single-row post-phase micro-cluster, zero attack rows, very high row_nonzero (**75**) and high row_signal (**7.48 lift**). Features: registry key, system hive, WinEVTX, NTFS.
**Likely mode:** **isolated system-hive / registry-heavy system event**.
**Interpretation:** could be a one-off administrative or boot/shutdown/configuration action. Not attack-enriched, but because it is a singleton with system-hive focus, it deserves contextual review.

**Cluster 11**
Single-row pre-phase micro-cluster, zero attack rows, high row_nonzero (**63**) and very high row_signal (**29.77 lift**). Features: NTFS, registry key, System32, accessed, standard info.
**Likely mode:** **isolated high-intensity system-level maintenance/configuration window**.
**Interpretation:** probably benign but extremely distinctive. Could align with service start, installer activity, updates, or a system configuration change.

**Cluster 15**
Single-row pre-phase micro-cluster, zero attack rows, high row_nonzero (**69**) and high row_signal (**7.65 lift**). Features: NTFS, users dir, file stat, standard info.
**Likely mode:** **isolated user-space metadata burst**.
**Interpretation:** could be a precursor action, but with zero attack rows it looks more like a rare benign user-side bulk file operation unless correlated with a known incident milestone.

---

B) **Top 3 suspicious clusters with reason**

**1) Cluster 4**
Best balance of **strong attack enrichment** and **coherent file-centric semantics**. It is tiny, concentrated, mostly post-phase, and centered on actual file-entry/file/stat indicators with hashing presence. That combination is very compatible with **payload staging, dropped files, extracted contents, or selective file manipulation**.

**2) Cluster 1**
Not the highest enrichment, but it has **very high row_signal lift (12.51)** plus a telling mix of **filesystem metadata and registry key activity**. That cross-artifact combination is often more operationally meaningful than raw attack-rate alone because it suggests **state change**, not just passive access.

**3) Cluster 8**
Very small, moderately attack-enriched, and **extremely intense** for AppData/user-dir NTFS metadata activity. AppData is often where both legitimate apps and attacker tooling operate, but in forensic prioritization, **small high-intensity AppData bursts** are exactly the kind of windows that often reveal execution, unpacking, persistence, or dropped user-space components.

**Honorable mention: Cluster 16**
I would not rank it top 3 purely on one row, but it is a **high-priority micro-cluster** because the combination of **policy change + temp/spool + high enrichment** is very interpretable and potentially very important.

**Behaviorally most abnormal regardless of label: Cluster 3**
This is the cluster to inspect if you want the single strongest anomaly by intensity. It may be benign, but it is too extreme to ignore.

---

C) **Recommended validation steps on source rows/time windows**

For each priority cluster, validate at the **source-row/window level**, not just aggregate metrics.

**For Cluster 4**

* Pull all 5 source windows between **2022-02-06 07:56:00** and **2022-02-12 00:04:00**.
* Enumerate the exact files behind `is_file_entry`, `has_sha256`, `mask_File_stat`, `is_ntfs`.
* Check whether the same paths recur across the 4 attack-labeled rows.
* Look for:

  * newly created executables, DLLs, archives, scripts
  * files in suspicious user-writable locations
  * short-lived files or staged bundles
  * clustered SHA256-bearing objects that were created/accessed together

**For Cluster 1**

* Review all 15 windows from **2022-02-04 07:06:00** to **2022-02-12 19:23:00**.
* Correlate **registry key artifacts** with **file MACB changes** in the same windows.
* Specifically test for:

  * Run / RunOnce / Services / Scheduled Tasks / policy-related keys
  * shell extensions, startup persistence, autoruns
  * file modifications in directories referenced by those registry keys
* Build a per-window mini timeline: registry write → file create/modify → subsequent access.

**For Cluster 8**

* Inspect the 3 windows from **2022-02-04 07:08:00** to **2022-02-12 01:47:00**.
* Resolve exact **AppData paths** and determine whether they belong to:

  * legitimate app updates/installers
  * browser/cache/updater noise
  * suspicious executables/scripts/unpacked resources
* Compare filenames, parent directories, extensions, and temporal adjacency to known suspicious events.

**For Cluster 16**

* Inspect the single window at **2022-02-11 22:54:00** in full context: at least 30–60 minutes before and after.
* Determine what generated `is_policy_change` and whether the temp/spool artifacts are tied to:

  * Group Policy changes
  * print spooler activity
  * temporary script/dropper execution
  * installer or admin tool activity
* Because this is a singleton, neighboring windows matter more than the row itself.

**For Cluster 3**

* Pull all 21 windows from **2022-02-05 01:22:00** to **2022-02-12 21:47:00**.
* Sort underlying rows by contribution to `row_signal_mean` and inspect the top contributors first.
* Test whether the extreme signal comes from:

  * many objects touched once
  * a small set of objects touched heavily
  * one artifact family exploding in count
* Distinguish between benign bulk processes and malicious mass activity by checking path locality, file types, and known maintenance windows.

**For filesystem-heavy clusters as a family: 0, 2, 3, 4, 8, 12, 13**

* Create a comparison sheet with:

  * top directories
  * file extensions
  * create/modify/access ratios
  * count of unique paths
  * repeat-path concentration
* This helps separate:

  * benign broad scans/indexing/backups
  * focused attacker staging/execution
  * application installer/update behavior
  * persistence-related user-space changes

**For PowerShell-related Cluster 6**

* Even though it is low priority as a cluster, sample windows near known incident milestones.
* Validate whether `event_powershell` corresponds to:

  * interactive admin usage
  * automation scripts
  * encoded commands / unusual parents / suspicious script blocks
* If command content is available, pivot immediately on rare or encoded usage.

**For singleton zero-attack micro-clusters: 9, 11, 15**

* Do a fast manual review, not a deep dive first.
* Ask:

  * Is this near an incident boundary?
  * Is it a system start/stop/update point?
  * Does it correspond to one rare but benign maintenance action?
* If yes, deprioritize; if no, promote for deeper inspection.

---

### Priority for manual investigation

**Highest priority**

1. **Cluster 4** — strongest suspicious small file-operation cluster
2. **Cluster 1** — heavy registry + filesystem churn
3. **Cluster 8** — intense AppData/user-space burst
4. **Cluster 16** — singleton but highly interpretable policy/temp-spool event

**High anomaly review**
5. **Cluster 3** — extreme intensity, even if not attack-enriched
6. **Cluster 13** — AppData/user-dir sustained churn
7. **Cluster 12** — rare intense file-metadata bursts

**Lower priority / likely baseline or mixed**
8. **Cluster 10** — dominant background class
9. **Cluster 14** — sparse entropy-driven background/transitional class
10. **Cluster 6** — broad mixed PowerShell/event background unless supported by command evidence

The main forensic takeaway is that this cut produced two important families:

* **attack-enriched micro-clusters** that look like **focused file/policy/user-space activity**: 4, 8, 16, 1
* **behaviorally extreme but weakly labeled clusters** that may still be crucial because the label is imperfect: 3, 2, 0, 12, 13

That second family should not be ignored just because attack enrichment is low.
