# Dokumentácia Aktuálnej Agglomerative Clustering Pipeline

Tento text opisuje aktuálne používanú agglomerative clustering vetvu v repozitári ADFIR. Zameriava sa na praktický workflow pre `60s` časové okná a na downstream export pre Streamlit dashboard.

## 1. Vstupné dáta

Pipeline pracuje s už agregovanými datasetmi vo formáte:

`agg_(max|sum)_<artifact>_<window>s.parquet`

## 2. Výber feature priestoru

Filtrujeme technické meta stĺpce ako `artifact`, `aggregation`, `window_s`, `source_path`, `row_idx`
- label stĺpec

Aktuálny label stĺpec je `is_attack_related`

Potom sa aplikuje ďalšia filtrácia:

1. **Entropy feature filtering**

   Filtrujeme v3etky st=lpce s=uvisiace s entropiou (work-in-progress)

2. **Agregácia `max`**

   Pri `max` sa ponechávajú len binary-like feature, teda stĺpce s hodnotami zodpovedajúcimi `0/1`.

3. **Agregácia `sum`**

   Pri `sum` sa ponechávajú všetky numerické feature s podporovanými numerickými dtypmi.

5. **Dead-feature filter**

   Ak je zapnutý `enable_dead_filter`, načíta sa deadness report a vyradia sa feature, ktoré prekročia konfigurovaný prah `dead_records_pct_threshold`.

Výsledkom tejto fázy sú:

- `feature_cols`: finálny zoznam feature stĺpcov
- `raw_features`: dataframe s týmito stĺpcami v pôvodnom priestore

## 3. Príprava modelového priestoru

Po výbere feature sa vytvoria dve samostatné reprezentácie:

- `raw_features`: priestor používaný na interpretáciu clusterov
- `model_matrix`: priestor používaný na samotné clustering výpočty

### 3.1 Agregácia `sum`

Pre `sum` sa používa transformácia `log1p_zscore`, ktorá je aj aktuálny default.

Postup:

1. `raw_features` sa prevedú na `float`
2. ak sa v dátach nachádzajú záporné hodnoty, použije sa:

   `sign(x) * log1p(abs(x))`

3. inak sa použije:

   `log1p(x)`

4. následne sa aplikuje:

   `StandardScaler(with_mean=True, with_std=True)`

5. všetky `NaN`, `+inf`, `-inf` sa nahradia nulou

Táto transformácia:

- komprimuje heavy-tail count/sum rozdelenia
- zjednocuje mierku feature
- stabilizuje euklidovské vzdialenosti pred clusteringom

### 3.2 Agregácia `max`

Pre `max` sa nepoužíva `log1p`.

Postup:

- binary/binary-like feature sa len prevedú na `float`
- `model_matrix` zostáva v raw binárnom priestore

## 4. Clustering space a PCA embedding

Clustering prebieha priamo nad plným `model_matrix`.

Funkcia `build_cluster_spaces(...)` vytvorí:

1. **cluster space**

   `cluster_space = model_matrix`

   Tento priestor sa používa na reálne clustering výpočty.

2. **PCA-2 embedding**

   `PCA(n_components=2, random_state=42)`

   Tento embedding slúži len na vizualizáciu a export.

Zmysel rozdelenia:

- `model_matrix` = transformovaný feature priestor
- `cluster_space` = plný priestor, v ktorom sa reálne klastruje
- `emb2` / `pc1`, `pc2` = 2D projekcia na scatter a dashboard

Ak nie je možné zostaviť validný `model_matrix`, clustering sa preskočí. Samotný `PCA-2` embedding je pomocná vizualizačná vrstva a jeho nedostupnosť sama osebe neznamená, že clustering nemožno vykonať.

## 5. Samotný agglomerative clustering

Agglomerative vetva používa:

- `AgglomerativeClustering`
- `metric="euclidean"`
- zvolený `linkage` (Ward)
- `compute_distances=True`

### 5.1 Rez podľa počtu clusterov (`k`)

Použije sa:

- `fit_agglomerative_with_k(cluster_space, n_clusters=k, linkage=...)`

Toto je režim používaný aj v dashboard exporte, kde sa generujú všetky `k` v intervale, typicky:

- `10..30`

## 6. Validácie a skip/failure režimy

Clustering sa nevykoná alebo sa označí ako neúspešný v týchto situáciách:

- po filtrácii nezostane žiadny feature stĺpec
- dataset má menej než 3 riadky
- nie je možné zostaviť validný clustering priestor
- `k` je neplatné pre daný počet riadkov
- model vytvorí menej než 2 clustre
- model vytvorí toľko clusterov ako je riadkov alebo viac

Pri takýchto stavoch pipeline zapisuje failure outputs a manifest so statusom zlyhania alebo skipu.

## 7. Hodnotenie clustering behov

Po úspešnom clusteringu sa nad `cluster_space` a výslednými labelmi rátajú run-level metriky:

- `silhouette_score`
- `davies_bouldin_score`
- `calinski_harabasz_score`

Tieto metriky slúžia ako globálne hodnotenie kvality rozdelenia pre konkrétny cut.

## 8. Cluster summary

Funkcia `build_cluster_summary(...)` vytvára run-level aj cluster-level prehľad.

### 8.1 Run-level riadok

Obsahuje napríklad:

- `rows`
- `features_total`
- `selected_k`
- `silhouette_score`
- `davies_bouldin_score`
- `calinski_harabasz_score`
- `largest_cluster_size`
- `largest_cluster_frac`
- `attack_rate_global`
- `best_cluster_attack_rate`
- `best_cluster_attack_lift`

### 8.2 Cluster-level riadky

Obsahujú napríklad:

- `cluster_id`
- `cluster_size`
- `cluster_frac`
- `attack_count`
- `attack_rate`
- `attack_lift_vs_global`
- `time_cluster_min`
- `time_cluster_max`

Interpretácia attack metrík:

- `attack_count` = počet riadkov v clustri, kde `is_attack_related = 1`
- `attack_rate` = podiel attack riadkov v clustri
- `attack_lift_vs_global` = pomer `attack_rate / attack_rate_global`

## 9. Feature interpretácia clusterov

Feature interpretácia sa robí nad `raw_features`, nie nad `cluster_space`.

To znamená:

- clustering vzniká v transformovanom `model_matrix`
- interpretácia sa robí späť v pôvodnom raw feature priestore
- ranking používa štandardizovaný score odvodený z raw priestoru

Pre každý cluster sa počíta dual-view summary:

- `cluster_value` = priemer feature v danom clustri
- `global_value` = priemer tej istej feature v celom datasete
- `delta_vs_global = cluster_value - global_value`
- `global_std` = populačná smerodajná odchýlka feature v celom datasete, teda `raw_features.std(axis=0, ddof=0)`
- `score_std = (cluster_value - global_value) / (global_std + 1e-8)`
- `direction`:
  - `elevated`, ak `score_std > 0`
  - `suppressed`, inak

Ranking:

1. vyradia sa feature, ktoré sú zároveň nulové:

   - v clustri
   - globálne
   - aj v delte

2. ponechajú sa feature s nenulovým `abs(score_std)`

3. zoradia sa podľa:

   - `abs(score_std)` zostupne
   - potom podľa signed `score_std`
   - potom podľa názvu feature

Tým sa zachytia:

- elevated feature
- suppressed feature

Raw hodnoty zostávajú interpretačným pohľadom. `score_std` slúži iba na ranking a porovnateľnosť feature naprieč rôznymi škálami.


## 10. Dôležité metodické rozlíšenia

Pri interpretácii výsledkov treba striktne rozlišovať:

1. **Feature selection**

   ktoré stĺpce vôbec vstupujú do pipeline

2. **Modelový priestor**

   teda transformovaný `model_matrix`

3. **Clustering priestor**

   teda plný `cluster_space`, ktorý je rovný `model_matrix`

4. **Interpretačný priestor**

   teda `raw_features`, z ktorých sa rátajú `cluster_value`, `global_value`, `delta_vs_global` a `global_std`

5. **Rankingový priestor**

   teda štandardizovaný pohľad nad raw priestorom reprezentovaný cez `score_std` a `direction`

Toto rozlíšenie je dôležité, pretože clustre vznikajú v inom priestore, než v akom sa následne opisujú.

## 11. Stručné zhrnutie pipeline

Aktuálny agglomerative clustering workflow je teda:

1. načítať `agg_(max|sum)_..._60s.parquet`
2. doplniť technické meta stĺpce
3. vybrať feature stĺpce a odfiltrovať neželané stĺpce
4. pripraviť `raw_features`
5. vytvoriť `model_matrix`
6. použiť `model_matrix` ako `cluster_space` a vytvoriť PCA-2 embedding
7. vykonať agglomerative clustering podľa `k` alebo `distance_threshold`
8. spočítať run metrics
9. vytvoriť cluster summary
10. vytvoriť feature interpretáciu z raw priestoru
11. vytvoriť cluster characteristics
12. zapísať výstupné CSV/parquet/JSON súbory
13. voliteľne z toho pripraviť long-form dashboard export

Toto je aktuálna implementovaná logika, s ktorou dnes pracuje clustering aj dashboard vetva v repozitári.
