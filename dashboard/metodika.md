Tu máš krátky, kompaktný report, ktorý môžeš poslať kolegom:

---

## **Interpretácia dôležitosti atribútov**

### **1. Predpoklady**

* **Dáta:**

  * Vstupom sú **raw feature** (sum agregácie v časových oknách).
  * Tieto raw features majú:

    * rôzne škály (0–1 vs. 0–1000+),
    * sparsity,

* **Transformácia pre clustering:**

  * Pred clusteringom sa aplikuje transformácia `log1p + z-score`.
  * Použijeme `np.log1p(x)` a následne StandardScaler. V prípade že máme záporné hodnoty, tak `sign(x) * log1p(abs(x))`.
  * Clustering následne prebieha:

    * nad **model_matrix** (transformovaný priestor),

* **Interpretácia clusterov:**

  * Feature interpretácia sa robí späť v **raw feature priestore**:

    * `cluster_value` = mean feature v clustri
    * `global_value` = mean feature v celom datasete
    * `delta = cluster - global`

---

### **2. Prečo je transformácia dobrá**

Transformácia pred clusteringom je kľúčová, pretože:

* **Zjednocuje škály feature**

  * bez transformácie by dominovali high-range feature (napr. counts vs. binary)

* **Znižuje vplyv extrémnych hodnôt**

  * `log1p` stabilizuje heavy-tail distribúcie (typické pre sum/count dáta)

* **Zlepšuje geometriu priestoru**

  * clustering (napr. Ward linkage) predpokladá približne „rozumné“ vzdialenosti

* **Zvyšuje kvalitu clusterov**

  * clustre viac reprezentujú **vzory správania**, nie artefakty škály

👉 Z pohľadu modelovania je teda transformácia **metodicky správna a potrebná**.

---

### **3. Problém: transformácia vs. interpretácia**

Vzniká nesúlad:

* **Clustre vznikajú v transformovanom priestore**
* **Interpretácia sa robí v raw priestore**

To vedie k týmto problémom:

#### a) Nezhoda priestoru

* vysvetľujeme clustre v inom priestore, než v akom vznikli
  → potenciálne metodicky napadnuteľné

#### b) Neštandardizovaný význam feature

* `delta = mean difference`:

  * zvýhodňuje feature s veľkým rozsahom
  * nie je porovnateľný naprieč feature

#### c) Citlivosť na outliery

* mean je nestabilný pri sum/count dátach

#### d) Ignorovanie negatívnych odchýlok

* súčasný ranking berie len „vyššie než priemer“
* ale **potlačené feature môžu byť rovnako informatívne**

👉 Výsledok:
aktuálna metodika je **interpretovateľná**, ale nie úplne **robustná ani silná z pohľadu feature importance**.

---

### **4. Možnosti riešenia**

Existujú tri hlavné smery, ktoré zachovávajú interpretovateľnosť a zároveň zlepšujú metodiku:

---

#### **Variant A: Standardized deviation (odporúčaný baseline)**

* Namiesto raw delta použiť:

[
score = \frac{cluster_mean - global_mean}{global_std}
]

* Význam:

  * „koľko štandardných odchýlok je cluster nad/pod baseline“

**Výhody:**

* porovnateľné naprieč feature
* jednoduché na implementáciu aj vysvetlenie
* zachováva raw hodnoty pre interpretáciu

---

#### **Variant B: Robust (median-based) prístup**

* Použiť median a MAD:

[
score = \frac{median_{cluster} - median_{global}}{MAD}
]

**Výhody:**

* odolné voči outlierom
* vhodné pre sum/count dáta

**Nevýhoda:**

* menej intuitívne než mean

---

#### **Variant C: Dual-view (najlepšie riešenie)**

Kombinovať:

* **Raw interpretácia:**

  * `cluster_value`, `global_value`, `delta`

* **Štandardizovaný score pre ranking:**

  * `score_std`
  * kde `score_std = (cluster_value - global_value) / (global_std + 1e-8)`
  * `global_std` sa ráta ako populačná smerodajná odchýlka v raw priestore, teda `std(ddof=0)`

* **Obojsmerná interpretácia:**

  * ranking podľa `abs(score_std)`
  * rozlíšiť:

    * **elevated features**
    * **suppressed features**

**Výhody:**

* zachováva interpretovateľnosť (raw hodnoty)
* zároveň zabezpečuje metodickú robustnosť (standardization)
* umožňuje zachytiť aj „chýbajúce“ alebo potlačené správanie

---

## **Zhrnutie**

* Transformácia je **nevyhnutná pre kvalitný clustering**
* Interpretácia v raw priestore je **správna pre vysvetliteľnosť**
* Aktuálny prístup (`mean difference`) je:

  * dobrý baseline,
  * ale slabší ako feature importance metrika

👉 Najlepší kompromis:

> ponechať raw hodnoty pre interpretáciu, ale feature ranking robiť pomocou štandardizovanej (a ideálne aj robustnej) odchýlky a brať do úvahy aj pozitívne aj negatívne odchýlky.

---

Ak chceš, viem ti z toho spraviť aj:

* verziu do diplomovky (formálnejšiu),
* alebo priamo implementačný návrh do tvojho pipeline.
