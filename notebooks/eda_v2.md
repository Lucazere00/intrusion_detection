## 1. Setup


### Project configuration


### DuckDB connection


## 2. Dataset structure


#### Osservazioni
- Ci sono 75.987.976 flussi e 47 colonne, tutte quelle attese. Mancano le colonne con timestamp e IAT della v3.
- Il peso dei sub-dataset è molto sbilanciato: BoT-IoT 49,7%, CSE-CIC-IDS2018 24,9%, ToN-IoT 22,3%, UNSW-NB15 3,1% (circa 16 a 1 tra il primo e l'ultimo).
- `row_id` è unico solo dentro ogni `Dataset`, perché riparte da 0 per ogni file. Non rispetta l'ordine di cattura dei flussi.

#### Note per la pulizia
- Identificare ogni riga con la coppia `(Dataset, row_id)` e non usare `row_id` e `Dataset` come feature.

#### Note per l'addestramento
- BoT-IoT pesa quasi metà dei dati: servono pesi o campionamento, e le metriche vanno riportate per fonte.
- Non costruire sequenze usando l'ordine di `row_id`.


## 3. Data integrity


#### Osservazioni
- Non ci sono NULL, NaN/Inf, valori fuori dominio né violazioni delle 9 regole di consistenza (sono controlli semplici: limiti minimi e ordinamenti).
- Ci sono 120.210 duplicati esatti (0,16% del totale, 0,32% di BoT-IoT), tutti in BoT-IoT. Non sappiamo se sono flussi ripetuti davvero o copie.
- 5.384 gruppi di righe (20.410 righe, 0,03%) hanno feature identiche ma `Attack` diverso. `Label` è sempre 1, quindi non c'è mai un conflitto tra benigno e attacco. Succede solo in CSE-CIC (2.934 gruppi) e UNSW-NB15 (2.450 gruppi).
- In CSE-CIC il conflitto è quasi sempre `DDOS attack-HOIC` contro `Brute Force -Web` (1.746 gruppi), `Brute Force -XSS` (738) e `SQL Injection` (338). Almeno l'81%, l'80% e il 78% delle righe di queste tre classi ha una riga HOIC identica. Sono limiti inferiori, perché ogni variante compare una sola volta per gruppo.
- In UNSW-NB15 `Exploits` va in conflitto con `Generic`, `DoS`, `Reconnaissance` e `Fuzzers`. Alcuni gruppi hanno fino a 5 classi (`Analysis`, `Backdoor`, `DoS`, `Exploits`, `Fuzzers`).
- In CSE-CIC e UNSW-NB15 non ci sono duplicati esatti con la stessa etichetta, ma ci sono righe identiche con etichette diverse. `[ipotesi]` il dataset originale potrebbe essere stato deduplicato per classe, oppure le finestre di attacco si sovrappongono.
- Con uno split casuale 75/25, circa 2.251 righe in conflitto di CSE-CIC (38%) e 11.957 di UNSW-NB15 (82,5%) finirebbero con la riga gemella nell'altro split.

#### Note per la pulizia
- Duplicati: non toglierli alla cieca. Prima si raggruppano e si deduplica, poi si fa lo split.
- Conflitti: non eliminare i gruppi. Nel binario non serve fare nulla. Nel multiclasse queste classi non si distinguono con le feature attuali: decidere se tenerle separate nei risultati o raggrupparle in una famiglia (es. attacchi web).

#### Note per l'addestramento
- Fare lo split per gruppi di feature identiche, così nessuna copia finisce sia in train sia in test.
- Nel multiclasse, per le classi in conflitto la recall massima è limitata dai dati stessi: riportare le metriche sia per classe sia per famiglia.


## 4. Class distribution


#### Osservazioni
- Gli attacchi sono il 66,9% del totale, ma dipende dalla fonte: 99,6% in BoT-IoT, 64,0% in ToN-IoT, 12,0% in CSE-CIC-IDS2018, 4,0% in UNSW-NB15. In BoT-IoT i benigni sono solo 135.037 (0,36%).
- `Attack` ha 35 valori. `DDoS` (24,1%) e `DoS` (21,9%) dominano: `DDoS` ha 18.331.847 righe, `Worms` solo 164. Dieci classi stanno sotto lo 0,01%.
- Ci sono varianti di maiuscole (`DoS`/`dos`, `DDoS`/`ddos`, `Backdoor`/`backdoor`) e un refuso (`Infilteration`). Classi con lo stesso nome o simile in fonti diverse non sono per forza la stessa cosa: ad esempio `xss` di ToN-IoT ha 2.455.020 righe, `Brute Force -XSS` di CSE-CIC solo 927.

#### Note per la pulizia
- Normalizzare i nomi (`casefold` e `strip`) in una colonna separata dall'accorpamento per significato (`Attack_raw`, `Attack_norm`, eventuale famiglia). Ogni accorpamento va motivato.

#### Note per l'addestramento
- Usare macro-F1, recall e PR-AUC per classe e per fonte, con split stratificato per `Dataset` e classe.
- Accorpare o togliere le classi rare è una scelta da valutare, non un automatismo.


## 5. Feature distributions


#### Zeri, costanti e valori sentinella

Non avere NULL non significa non avere valori mancanti: un mancante può essere scritto come 0. Le analisi seguenti guardano la quota di zeri per feature, fonte, classe e protocollo. Le soglie nel codice sono criteri esplorativi.


#### Zeri strutturali o sospetti

Uno zero può essere un valore valido, un campo che non si applica o una sentinella. `ICMP_TYPE=0`, ad esempio, non è per forza un mancante. Il controllo sui valori fuori protocollo assume TCP=6 e ICMP=1.


#### Osservazioni
- La quota di zeri cambia molto da fonte a fonte. `FLOW_DURATION_MILLISECONDS` è zero nel 6,9% di BoT-IoT, 86,6% di CSE-CIC, 81,5% di ToN-IoT e 94,0% di UNSW-NB15. `DST_TO_SRC_SECOND_BYTES` è zero nell'87,9% di BoT-IoT, 6,3% di CSE-CIC, 37,0% di ToN-IoT e 2,2% di UNSW-NB15.
- Anche tra benigni e attacchi ci sono differenze nette (soglia esplorativa: 20 punti). `FLOW_DURATION_MILLISECONDS` in CSE-CIC è zero nel 96,0% dei benigni e nel 17,3% degli attacchi; `OUT_BYTES` in BoT-IoT nel 16,7% dei benigni e nell'88,2% degli attacchi. Possibili scorciatoie per il modello.
- `FTP_COMMAND_RET_CODE` è sempre zero solo in CSE-CIC. Nelle altre fonti è quasi sempre zero (ToN-IoT 99,7%, UNSW-NB15 81,9%) ma non costante.
- Nei flussi DNS su UDP, `DNS_QUERY_ID/TYPE` vale zero nell'1,4% dei casi in CSE-CIC, 3,8% in ToN-IoT, 32,0% in UNSW-NB15 e circa il 100% in BoT-IoT. Su TCP e ICMP è quasi sempre zero. Anche `L7_PROTO` varia tra fonti: il suo significato va verificato.
- I campi TCP (flag, finestre, ritrasmissioni) sono sempre zero fuori da TCP, come ci si aspetta.
- `ICMP_TYPE` e `ICMP_IPV4_TYPE` invece sono diversi da zero anche sui flussi TCP: BoT-IoT 4.930.580 righe (25,4% dei flussi TCP), CSE-CIC 1.444.651 (13,1%), ToN-IoT 263.930 (1,8%), UNSW-NB15 1.691.895 (92,4%). Sui flussi UDP sono sempre zero. `[ipotesi]` nei flussi TCP non sono un vero tipo ICMP ma un'altra codifica; non è verificato.
- Nei flussi ICMP, `ICMP_TYPE=0` può essere un valore valido: è zero nel 36,2% dei casi in CSE-CIC e in circa l'1,5% in ToN-IoT e UNSW-NB15.

#### Note per la pulizia
- Non trasformare tutti gli zeri in mancanti: si controlla feature per feature, per protocollo e per fonte. Non imputare i campi DNS/FTP senza aver verificato `PROTOCOL`, `L7_PROTO` e le convenzioni di ogni fonte.
- Una feature costante in una fonte può servire in un'altra. Le soglie di sparsità e di differenza sono esplorative.
- `ICMP_TYPE` e `ICMP_IPV4_TYPE`: non trattarli come veri tipi ICMP nei flussi TCP. Decidere se tenerli, separarli per protocollo o escluderli.

#### Note per l'addestramento
- Fare un'ablation sugli indicatori di applicabilità e su `ICMP_TYPE`/`ICMP_IPV4_TYPE`: possono far riconoscere fonte o protocollo (in UNSW-NB15 il 92,4% dei flussi TCP ha `ICMP_TYPE` diverso da zero).
- Selezione delle feature e imputazione si stimano solo sul train.


#### Durata

La durata ha molti zeri (dal 6,9% di BoT-IoT al 94,0% di UNSW) e una coda a parte. Il massimo osservato è 4.294.967 (= ⌊2³²/1000⌋). La soglia 4.000.000 è esplorativa e non prova che ci sia saturazione.


#### Osservazioni
- La quota di righe con `FLOW_DURATION_MILLISECONDS > 4.000.000` è 98,3% per `DDoS` e 95,7% per `DoS` in BoT-IoT; 100% per `DDOS attack-HOIC`, `FTP-BruteForce` e `DoS attacks-SlowHTTPTest` in CSE-CIC; 72,8% per `ddos` in ToN-IoT. Anche i benigni di BoT-IoT sono al 62,9%.
- In CSE-CIC la durata separa bene benigni e attacchi: sopra soglia ci sono il 4,0% dei benigni contro il 100% di tre classi di attacco, e (cap. precedente) gli zeri sono 96,0% contro 17,3%. Rischio di scorciatoia.
- Il massimo 4.294.967 (= ⌊2³²/1000⌋) fa pensare a un valore troncato o saturato, ma l'origine tecnica non è confermata. Mediana: 4.293.811 in BoT-IoT, 0 in CSE-CIC e ToN-IoT.

#### Note per la pulizia
- Non eliminare righe e non confondere la durata zero con la coda estrema. Alternative da confrontare: valore originale, flag sul massimo, flag sopra soglia, mancante se la saturazione viene confermata, feature rimossa.
- Per `DURATION_IN` e `DURATION_OUT` non abbiamo fatto lo stesso controllo.

#### Note per l'addestramento
- Confrontare le alternative con gli stessi split, riportando metriche per fonte e per classe. Le trasformazioni si stimano sul train.


## 6. Correlation


#### Osservazioni
- Pearson calcolato su un campione di 100.000 righe, dominato dalle fonti più grandi. Coppie con |r| ≥ 0,90: `LONGEST_FLOW_PKT`–`MAX_IP_PKT_LEN` 1,000; `MIN_TTL`–`MAX_TTL` 0,999; `OUT_BYTES`–`OUT_PKTS` 0,997; `OUT_BYTES` e `OUT_PKTS` con `NUM_PKTS_1024_TO_1514_BYTES` 0,996 e 0,993; `RETRANSMITTED_OUT_BYTES`–`RETRANSMITTED_OUT_PKTS` 0,981.
- La correlazione cambia tra benigni e attacchi: `IN_BYTES`–`NUM_PKTS_UP_TO_128_BYTES` è 0,002 nei benigni e 0,994 negli attacchi. Dato indicativo: campione piccolo e code pesanti.
- Una correlazione calcolata su tutti i dati insieme non prova che due feature siano uguali o ridondanti dentro ogni fonte.

#### Note per la pulizia
- Togliere `MAX_IP_PKT_LEN` solo dopo aver controllato che sia uguale a `LONGEST_FLOW_PKT` riga per riga. Per le altre coppie, valutare fonte per fonte.

#### Note per l'addestramento
- Confrontare il modello con feature ridotte o rapporti contro quello con tutte le feature: costi e benefici dipendono dal modello.


## 7. Network entities


#### Osservazioni
- Ci sono 247.700 IP sorgente e 40.529 IP destinazione. Solo 6 IP sorgente compaiono in più fonti: le reti sono quasi separate, quindi un grafo unico equivale a quattro componenti.
- `18.219.193.20` ha 432.648 flussi, una sola label e una sola destinazione. È esattamente il numero di righe di `DoS attacks-Hulk`, quindi questo IP identifica la classe.
- In CSE-CIC il 99,75% degli IP sorgente ha una sola etichetta (223.920 solo benigni, 97 solo attacco). BoT-IoT ha 20 IP sorgente (12 solo benigni, 8 con entrambe). Porte destinazione: BoT-IoT 16.235 solo attacco e nessuna solo benigna, ToN-IoT 27.375 solo attacco, UNSW-NB15 61.645 solo benigne. Sono conteggi di valori distinti, non pesati per numero di flussi.
- `L7_PROTO` = 188 compare in 18.331.497 righe di BoT-IoT (cap. 5), quasi quanto i 18.331.847 flussi `DDoS`. `[ipotesi]` è una scorciatoia quasi perfetta per quella classe, ancora da verificare.
- IP e porte possono descrivere anche un comportamento o un servizio, non solo identificare. Se il modello li memorizza si vede solo con split dedicati.

#### Note per la pulizia
- Trattare gli IP come chiavi `(Dataset, IP)`. Confrontare porte discretizzate, categoriali o escluse. Gli aggregati vanno calcolati senza far entrare informazioni del test.

#### Note per l'addestramento
- Confrontare split per IP e split casuali.
- Sequenze per host solo se l'ordine temporale è verificato. Per la GNN, decidere come trattare gli hub.


Sono alternative da confrontare, nessuna è già scelta. Pro e contro vengono dai risultati dell'EDA.

| ID | Cap. | Decisione | Opzione | Pro | Contro |
|---|---|---|---|---|---|
| P1-a | 3 | Duplicati esatti | Deduplicare prima dello split | Nessuna copia tra train e test | Cambia le frequenze (120.210 righe di BoT-IoT) |
| P1-b | 3 | Duplicati esatti | Tenerli e fare split per gruppi | Frequenze originali, senza contaminazione | Split più complesso; meno varietà reale |
| P2-a | 3 | `Attack` discordante | Tenere nel binario | `Label` è coerente | Nel multiclasse resta ambiguo |
| P2-b | 3 | `Attack` discordante | Escludere o analizzare a parte nel multiclasse | Metriche meno ambigue | Test meno rappresentativo |
| P2-c | 3 | `Attack` discordante | Mappare le classi con evidenza di significato | Si tengono i dati | Si perde granularità; non sono tutti errori |
| P3-a | 5 | Zeri strutturali | Tenerli e aggiungere un indicatore di applicabilità | Si conservano valori validi | L'indicatore può diventare una scorciatoia |
| P3-b | 5 | Zero sentinella confermato | Trasformare in mancante e imputare | Rappresenta l'assenza | Serve conferma; rischio di bias |
| P3-c | 5 | Zeri ambigui | Ablation con e senza indicatori | Misura quanto pesa la presenza del campo | Più feature; possibile proxy di fonte o protocollo |
| P4-a | 4 | Nomi delle classi | Normalizzare le varianti confermate | Etichette uniformi | Non prova che il significato sia lo stesso |
| P4-b | 4 | Tassonomia | Tenere le classi originali | Nessun accorpamento assunto | Classi rare e fonti poco confrontabili |
| P4-c | 4 | Tassonomia | Mappare in famiglie | Più interpretabile | Si perde dettaglio; il mapping va motivato |
| P5-a | 4 | Classi rare | Accorpare in "other" | Più esempi per classe | Classe eterogenea |
| P5-b | 4 | Classi rare | Tenerle e riportare il supporto | Massima granularità | Metriche instabili |
| P5-c | 4 | Classi rare | Escludere solo dal multiclasse | Test più stabile | Copertura minore |
| P6-a | 5 | Durata | Valore originale o flag su massimo/soglia | Si tiene l'informazione e si separano zeri e coda | Il flag può codificare la fonte; la soglia non prova la saturazione |
| P6-b | 5 | Durata | Trattare come censurata/mancante se confermato | Modella il limite | Serve conferma tecnica |
| P6-c | 5 | Durata | Rimuovere la feature (baseline) | Toglie una possibile scorciatoia | Si perde segnale utile |
| P6-d | 5 | Durata | Escludere le righe estreme | Elimina la coda | Perdita grande in alcune fonti e classi |
| P7-a | 6 | Correlazione 1,00 | Rimuovere solo dopo il controllo riga per riga | Meno dimensioni se è davvero ridondante | Pearson sui dati uniti non prova l'uguaglianza |
| P8-a | 6 | Altre correlazioni | Ridurre le coppie | Meno costo | Possibile perdita di informazione |
| P8-b | 6 | Altre correlazioni | Usare rapporti o range | Feature più compatte | Da validare; attenzione a zeri e code |
| P8-c | 6 | Altre correlazioni | Tenere tutto | Nessuna perdita | Costo e collinearità |
| P9-a | 6.1 | Dataset e proxy | Escludere e valutare i proxy | Test migliore di generalizzazione | Può restare shift residuo |
| P9-b | 6.1 | Dataset e proxy | Includere (in-distribution) | Sfrutta il contesto noto | Non vale per fonti nuove |
| P10-a | 7 | IP | Usarli come chiavi, non come feature | Meno memorizzazione | Si perde identità e reputazione dell'host |
| P10-b | 7 | IP | Includerli solo come ablation | Misura il vantaggio in-distribution | Alta cardinalità; overfitting |
| P10-c | 7 | IP | Aggregati di comportamento | Tiene i pattern degli host | Rischio di leakage; più costo |
| P11-a | 7 | Porte | Discretizzare per servizio o intervallo | Tiene il contesto senza usare l'ID esatto | Si perde dettaglio; mapping da motivare |
| P11-b | 7 | Porte | Numeri grezzi | Semplice | L'ordine numerico non ha senso; scorciatoia |
| P11-c | 7 | Porte | Categoriali o embedding | Modella il servizio | Alta cardinalità; overfitting |
| P11-d | 7 | Porte | Escludere (baseline) | Misura quanto dipende dal servizio | Si perde segnale (`L4_DST_PORT` ha AUC 0,926) |
| P12-a | 7 | Nodi GNN | `(Dataset, IP)` | Non unisce host di fonti diverse | Nessun legame tra dataset |
| P12-b | 7 | Nodi GNN | Solo IP | Più semplice | Unisce host diversi |
| P13-a | 5 | Feature costante in una fonte | Rimuoverla nel train di quella fonte/fold | Toglie una feature senza variabilità | Pipeline meno uniforme |
| P13-b | 5 | Feature costante in una fonte | Tenere lo schema comune e fare ablation | Si riusa tra fonti | Feature inutile o proxy in alcune fonti |
| P14-a | 7 | Sequenze | Usarle solo con ordine temporale verificato | Modella la dinamica | Senza ordine verificato la sequenza è fuorviante |
| P15-a | 5 | `ICMP_TYPE`/`ICMP_IPV4_TYPE` diversi da zero nei flussi TCP | Tenere come feature separata e fare ablation | Si conserva l'informazione, presente in tutte le fonti | Nei flussi TCP non è un tipo ICMP; in UNSW-NB15 è diverso da zero nel 92,4% dei TCP: proxy di fonte |
| P15-b | 5 | `ICMP_TYPE`/`ICMP_IPV4_TYPE` diversi da zero nei flussi TCP | Escludere | Toglie un possibile proxy di fonte o protocollo | Si perde l'eventuale segnale |
| P16-a | 3 | Split train/test | Per gruppi di feature identiche | Nessuna riga gemella tra train e test | Più complesso; gruppi di dimensioni diverse |
| P16-b | 3 | Split train/test | Casuale per riga | Semplice | Il 38% (CSE-CIC) e l'82,5% (UNSW-NB15) delle righe in conflitto ha la gemella nell'altro split |
