## 1. Setup


### Project configuration


### DuckDB connection


## 2. Dataset structure


#### Osservazioni

- Lo schema ha 57 colonne: `row_id`, `Dataset` e le 55 colonne originali della v3. Non manca nulla, non c'è nulla in più e tutti i tipi coincidono con quelli attesi (`type_check`).
- Le righe sono 66.935.021 e coincidono esattamente con i conteggi ufficiali di ogni sorgente: BoT-IoT 16.933.808, CSE-CIC-IDS2018 20.115.529, ToN-IoT 27.520.260, UNSW-NB15 2.365.424. La conversione in Parquet non ha perso né aggiunto righe.
- `row_id` non ha NULL ed è unico dentro ogni `Dataset` (non a livello globale).

#### Note per la pulizia

- Niente da correggere su schema e conteggi.
- I valori di `Dataset` sono `NF-BoT-IoT`, `NF-CSE-CIC-IDS2018`, `NF-ToN-IoT` e `NF-UNSW-NB15`, senza suffisso `-v3`.

#### Note per l'addestramento

- Una riga si identifica con la coppia (`Dataset`, `row_id`). Né `row_id` né `Dataset` vanno usati come feature.
- `row_id` segue l'ordine temporale solo in alcune sorgenti (vedi capitolo 8): per le sequenze si ordina per timestamp.


## 3. Data integrity


#### Osservazioni

- Gli unici valori mancanti o non finiti sono in `SRC_TO_DST_SECOND_BYTES` e `DST_TO_SRC_SECOND_BYTES` (`missing`, `quality_detail`): 1.898.421 valori +inf (664.755 + 1.052.105 + 59.068 + 122.493) e 450.775 NULL (387.350 + 63.425), solo in BoT-IoT e UNSW-NB15. Non ci sono NaN né -inf. Le colonne IAT e i due timestamp sono pulite.
- Tutti questi casi stanno su flussi con durata 0; con durata positiva non ce n'è nessuno (`zero_rows`, `zero_status`). I NULL compaiono quando `OUT_BYTES` è 0 (0/0), i +inf quando i byte sono positivi. `DST_TO_SRC_SECOND_BYTES` non ha NULL perché `IN_BYTES` è sempre almeno 1.
- La durata 0 dipende dalla sorgente (`extra_duration_granularity`): in BoT-IoT e UNSW-NB15 il minimo è 0 ms (6,21% e 5,18% delle righe) e tutti i flussi da un pacchetto durano 0 ms. In CSE-CIC-IDS2018 e ToN-IoT il minimo è 1 ms e tutti i flussi da un pacchetto durano 1 ms.
- La quota di durata 0 cambia molto con la classe (`extra_zero_by_class`): in BoT-IoT va dal 70,3% di `Theft` e 64,9% di `Benign` al 2,8% di `DoS` e 1,3% di `DDoS`; in UNSW-NB15 dal 75,8% di `Generic` al 3,9% di `Benign` e a 0% per `Analysis`. In BoT-IoT, 664.755 dei 1.052.105 flussi a durata 0 (63%) hanno byte in entrambe le direzioni, quindi non sono solo flussi da un pacchetto.
- In BoT-IoT e UNSW-NB15 le due colonne SECOND_BYTES coincidono al 100% con byte/durata, ma con le direzioni incrociate: `SRC_TO_DST_SECOND_BYTES` ≈ `OUT_BYTES`/durata e `DST_TO_SRC_SECOND_BYTES` ≈ `IN_BYTES`/durata (byte per millisecondo). In CSE-CIC-IDS2018 e ToN-IoT nessuna combinazione supera il 18% (`extra_rate_checks`): la definizione della colonna cambia da una sorgente all'altra.

#### Note per la pulizia

- Escludere SECOND_BYTES dalle feature: derivano da colonne già presenti, hanno definizioni diverse tra le sorgenti e i valori anomali seguono la durata (e la classe), quindi imputarli aggiungerebbe un'informazione che il modello può sfruttare. Si tengono grezze solo per tracciabilità.
- Non eliminare i flussi a durata 0. Alternative: portare a 1 ms in BoT-IoT e UNSW-NB15 (allinea il caso dei flussi da un pacchetto, non tutto l'arrotondamento) oppure aggiungere `is_zero_duration`. Da confrontare con un'ablation, perché l'indicatore può diventare una scorciatoia (la quota va da 0% a 76% tra le classi).

#### Note per l'addestramento

- `BYTE_RATE_COLS` resta fuori dalle feature. Se servono tassi di trasferimento, si ricostruiscono in modo uniforme da `IN_BYTES`, `OUT_BYTES` e durata, con una regola esplicita per durata 0.
- Provare con un'ablation (anche leave-one-dataset-out) l'effetto di `is_zero_duration`.


#### Osservazioni

- Duplicati esatti (tutte le colonne tranne `row_id`, timestamp compresi): 2.459.426 righe, 3,67% del totale (`exact_duplicate_groups`). ToN-IoT 1.816.137 (6,6%), CSE-CIC-IDS2018 628.474 (3,1%), UNSW-NB15 14.815 (0,6%), BoT-IoT nessuno.
- Se si ignorano anche i timestamp, i duplicati salgono a 10.106.788 (15,1%, `exact_duplicates_without_time`): ToN-IoT 8.907.276 (32,4%), CSE-CIC-IDS2018 1.169.944 (5,8%), UNSW-NB15 24.417 (1,0%), BoT-IoT 5.151 (0,03%). La differenza sono flussi con feature identiche ma in istanti diversi. `[ipotesi]` traffico ripetitivo, non copie vere.
- Conflitti (feature uguali, timestamp esclusi, etichette diverse): 16.511 gruppi per 51.074 righe, lo 0,08% del totale. Quasi tutti cambiano solo il tipo di attacco, con `Label` uguale (16.303 gruppi su 16.511). In BoT-IoT sono 15.432 gruppi (31.526 righe), tutti `DoS` contro `DDoS`: circa lo 0,2% delle 15.185.072 righe `DoS` e `DDoS`. In ToN-IoT i più numerosi sono `injection` contro `ddos` (oltre 700 gruppi).
- I conflitti tra Benign e Attack sono solo 208 gruppi, 11.466 righe (circa 0,017%): CSE-CIC-IDS2018 152 gruppi con 10.997 righe (il gruppo più grande ha 1.078 righe) e ToN-IoT 56 gruppi con 469 righe (`conflict_group_summary`). Tra le coppie più frequenti di CSE-CIC-IDS2018 c'è `Benign` contro `Infilteration`.
- Con uno split casuale 75/25 ci si aspetta che circa 30.900 righe in conflitto abbiano una riga gemella nell'altro lato (`conflict_split_risk`). È lo 0,05% del dataset, ma circa il 60% delle righe in conflitto; in CSE-CIC-IDS2018 e ToN-IoT supera il 90% (10.948 su 11.093 e 7.722 su 8.282).
- Domini: nessuna violazione (porte 0–65535, `PROTOCOL`, flag e TTL in 0–255, valori non negativi, timestamp positivi).
- Regole di coerenza: 0 violazioni su TTL, lunghezze dei pacchetti, `DURATION_OUT`, pacchetti/byte, ritrasmissioni, `IAT_MIN <= IAT_MAX` e `IAT_STDDEV >= 0`. Violazioni: `DURATION_IN > FLOW_DURATION_MILLISECONDS` in 11.277 righe (0,017%) e `IAT_MIN <= IAT_AVG <= IAT_MAX` in 1.002.492 righe SRC→DST (1,50%) e 623.354 righe DST→SRC (0,93%). Il notebook non dice se il problema sia `AVG < MIN` o `AVG > MAX`, né in quali sorgenti.

#### Note per la pulizia

- Duplicati con timestamp (2,46 milioni): sono i candidati da eliminare prima di costruire sequenze o finestre. Quelli senza timestamp (10,1 milioni) non vanno eliminati: sono eventi in istanti diversi, soprattutto in ToN-IoT.
- Conflitti: non eliminarli in blocco, marcarli con `is_conflict` (51.074 righe). Per una versione tabellare pulita si possono togliere solo i 208 gruppi Benign contro Attack (11.466 righe). I conflitti `DoS`/`DDoS` di BoT-IoT riguardano pochi flussi (0,2%): non bastano per dire che le due classi siano indistinguibili (vedi capitolo 4).
- `DURATION_IN > FLOW_DURATION_MILLISECONDS` e incoerenze IAT: non correggere, aggiungere un flag (per esempio `iat_inconsistent`) e tenere le righe.

#### Note per l'addestramento

- Fare dedup prima dello split, oppure uno split a gruppi (stessa firma di feature dallo stesso lato): altrimenti le metriche sono troppo ottimistiche, soprattutto su ToN-IoT.
- Per le sequenze, togliere le righe prima di costruire le finestre, non dopo: si spezzerebbe la continuità temporale.
- Le incoerenze IAT (1,5% e 0,9%) non bloccano; con un'ablation si verifica se il flag aiuta o fa da scorciatoia.


## 4. Class distribution


#### Osservazioni

- In totale ci sono 36.596.560 flussi Benign (54,67%) e 30.338.461 Attack (45,33%), rapporto 1,21. È un dato fuorviante, perché il bilanciamento cambia molto da sorgente a sorgente (`dataset_label_pct`): BoT-IoT è attacco al 99,69% (solo 51.989 flussi Benign), CSE-CIC-IDS2018 è Benign all'87,07%, ToN-IoT al 61,02%, UNSW-NB15 al 94,60% (attacchi 5,40%).
- `Attack` ha 34 valori (Benign più 33 attacchi) e sono molto sbilanciati: da `DoS` 8.040.170, `DDoS` 7.150.882, `ddos` 4.141.256 e `xss` 2.834.435 fino a `Worms` 158, `SQL_Injection` 440, `Brute_Force_-XSS` 480, `Analysis` 1.226, `Theft` 1.615 e `Brute_Force_-Web` 1.618. Tra la classe di attacco più grande e la più piccola il rapporto supera 50.000 a 1.
- I nomi non sono uniformi: `DoS` (BoT-IoT) e `dos` (ToN-IoT), `DDoS` e `ddos`, e in CSE-CIC-IDS2018 `DDOS_attack-*` contro `DDoS_attacks-*`. `Infilteration` ha un refuso nel nome. Non è documentato se classi con nomi diversi (per esempio `Reconnaissance` e `scanning`) siano equivalenti.
- La maggior parte delle classi di attacco compare in una sola sorgente. Solo tre nomi sono condivisi: `DoS` e `Reconnaissance` (BoT-IoT e UNSW-NB15) e `Backdoor` (ToN-IoT e UNSW-NB15). Nei conteggi di `Attack` questi nomi sommano righe di sorgenti diverse (per esempio `DoS` 8.040.170 = 8.034.190 + 5.980), ma non è detto che indichino lo stesso comportamento.

#### Note per la pulizia

- Non unire i nomi alla cieca: serve una mappa esplicita (`Dataset`, `Attack`) → famiglia (colonna `attack_family`), tenendo anche `Attack` originale. Il minimo è uniformare maiuscole e minuscole, ma attenzione: `casefold` unisce anche `DoS` e `dos`, `DDoS` e `ddos` di sorgenti diverse, quindi è già una scelta di significato.
- Il conflitto `DoS`/`DDoS` in BoT-IoT riguarda solo lo 0,2% delle righe (capitolo 3): non basta per accorparle. Meglio guardare la matrice di confusione del primo modello e accorpare solo se le due classi si confondono molto.

#### Note per l'addestramento

- Riportare macro-F1 e metriche per classe e per `Dataset`: l'accuracy globale è dominata da `DoS`/`DDoS` di BoT-IoT e dal Benign di CSE-CIC-IDS2018 e ToN-IoT.
- Usare pesi di classe, non oversampling massiccio su 67 milioni di righe. Le classi sotto circa 2.000 righe (`Worms`, `SQL_Injection`, `Brute_Force_-XSS`, `Analysis`, `Theft`, `Brute_Force_-Web`) vanno raggruppate, escluse dal multiclasse o valutate solo nel binario.
- BoT-IoT è quasi solo attacco: se il modello vede `Dataset`, o feature che lo identificano, può imparare "BoT = attacco". Non usare `Dataset` come feature e controllare con leave-one-dataset-out.


## 5. Feature distributions


#### Zeri, costanti e valori sentinella

Non avere NULL non significa non avere valori mancanti: un mancante può essere scritto come 0. Le analisi seguenti guardano la quota di zeri per feature, fonte, classe e protocollo. Le soglie nel codice sono criteri esplorativi.


#### Zeri strutturali o sospetti

Uno zero può essere un valore valido, un campo che non si applica o una sentinella. `ICMP_TYPE=0`, ad esempio, non è per forza un mancante. Il controllo sui valori fuori protocollo assume TCP=6 e ICMP=1.


#### Osservazioni

- `FTP_COMMAND_RET_CODE` è sempre 0 in tutte le 20.115.529 righe di CSE-CIC-IDS2018 ed è quasi sempre 0 in BoT-IoT (100,0%) e ToN-IoT (99,7%); in UNSW-NB15 lo è l'81,4%. È l'unica colonna costante in una sorgente.
- Altre colonne dominate dagli zeri (quota di zeri per sorgente, `zero_pivot`): `DNS_*` (100% BoT-IoT, 84–96% ToN-IoT, 84–85% UNSW-NB15, 63–64% CSE-CIC-IDS2018), `RETRANSMITTED_*` (99,9% BoT-IoT, 92–99% CSE-CIC-IDS2018 e ToN-IoT, 26–29% UNSW-NB15), `ICMP_TYPE`/`ICMP_IPV4_TYPE` (99,9% BoT-IoT, 92,1% CSE-CIC-IDS2018, 97,7% ToN-IoT, 25,8% UNSW-NB15).
- `IAT_MIN` è spesso 0 e dipende dalla sorgente: `DST_TO_SRC_IAT_MIN` 92,3% BoT-IoT, 75,3% CSE-CIC-IDS2018, 95,9% ToN-IoT, 100% UNSW-NB15; `SRC_TO_DST_IAT_MIN` 12,3%, 74,6%, 90,9% e 99,9%. In UNSW-NB15 lo zero è la norma: `[ipotesi]` valore sentinella o limite di risoluzione, più che un tempo reale.
- La quota di zeri cambia molto tra Benign e Attack: `gap_cases` ha 60 combinazioni feature×Dataset con differenza di almeno 20 punti (per esempio in BoT-IoT `SRC_TO_DST_IAT_MIN` 77,7% nei Benign contro 12,0% negli attacchi; in ToN-IoT `MIN_TTL`/`MAX_TTL` 91,6% contro 29,0%).
- I campi TCP sono sempre 0 fuori da TCP, in tutte le sorgenti. `ICMP_TYPE` e `ICMP_IPV4_TYPE` invece sono diversi da zero anche su flussi non ICMP: 9.870 righe in BoT-IoT, 1.557.675 in CSE-CIC-IDS2018, 430.546 in ToN-IoT, 1.754.341 in UNSW-NB15 (dove solo il 2,8% dei flussi TCP ha `ICMP_TYPE` = 0). Quindi non indicano sempre un vero tipo ICMP.
- Dentro i flussi TCP, `TCP_FLAGS` = 0 è raro (BoT-IoT 5.061 righe, CSE-CIC-IDS2018 231, ToN-IoT 1, UNSW-NB15 7).

#### Note per la pulizia

- Togliere `FTP_COMMAND_RET_CODE` (costante in una sorgente e quasi costante in altre due) oppure tenerla solo come flag binario.
- `DNS_*` e `RETRANSMITTED_*`: tenerle, ma trattarle come sparse (`log1p` o flag `is_nonzero`), da validare con un'ablation.
- Non leggere `ICMP_TYPE`/`ICMP_IPV4_TYPE` come tipi ICMP: o si trattano come categoriche dipendenti dalla sorgente, o si escludono in ablation.
- Zeri di `IAT_MIN` e `MIN_TTL`/`MAX_TTL`: ambigui (valore vero o sentinella). Indicatori solo se l'ablation li giustifica.

#### Note per l'addestramento

- Le feature con grandi `gap_cases` possono diventare scorciatoie: provarle in ablation per `Dataset` e con leave-one-dataset-out.
- Scaling e statistiche si stimano solo sul train. Le scale cambiano da una sorgente all'altra (definizioni diverse), quindi conviene provare anche una normalizzazione per sorgente.


#### Durata

La durata può avere molti zeri e una coda a parte. L'analisi guarda la quota di righe oltre una soglia esplorativa (4.000.000 ms, impostata nel codice) per Dataset e Attack. Il massimo osservato e l'eventuale saturazione vanno verificati sui dati v3.


#### Osservazioni

- Nessuna riga supera 4.000.000 ms, in nessun gruppo `Dataset`×`Attack` (`rows_tail` = 0 ovunque). Nella v2 il massimo era 4.294.967 ms e molte classi superavano la soglia: in v3 questa coda non c'è, quindi non si vede un limite di esportazione. Il valore massimo vero della durata in v3 non è stato calcolato.
- La durata 0 (BoT-IoT 6,21%, UNSW-NB15 5,18%, CSE-CIC-IDS2018 e ToN-IoT 0%) è trattata nel capitolo 3.

#### Note per la pulizia

- Nessun intervento sulla coda della durata.

#### Note per l'addestramento

- Se usare `log1p` o un'altra trasformazione della durata si decide in preprocessing, guardando la distribuzione: qui si è controllata solo la coda.


## 6. Correlation


#### Osservazioni

- Le feature continue sono 37, analizzate su un campione di 100.000 righe (reservoir, seed 42). Il campione è proporzionale alle righe, quindi pesano soprattutto ToN-IoT, CSE-CIC-IDS2018 e BoT-IoT.
- Dieci coppie con |r| ≥ 0,90 (`high_correlation_table`): `LONGEST_FLOW_PKT`–`MAX_IP_PKT_LEN` 1,000; `FLOW_DURATION_MILLISECONDS`–`DURATION_IN` 0,999; `MIN_TTL`–`MAX_TTL` 0,999; `OUT_BYTES`–`NUM_PKTS_1024_TO_1514_BYTES` 0,997; `OUT_BYTES`–`OUT_PKTS` 0,996; `OUT_PKTS`–`NUM_PKTS_1024_TO_1514_BYTES` 0,994; `RETRANSMITTED_OUT_BYTES`–`RETRANSMITTED_OUT_PKTS` 0,991; `IN_BYTES`–`IN_PKTS` 0,962; `DST_TO_SRC_IAT_MIN`–`DST_TO_SRC_IAT_AVG` 0,945; `SRC_TO_DST_IAT_MAX`–`SRC_TO_DST_IAT_STDDEV` 0,901.
- La correlazione cambia molto tra Benign e Attack (`class_correlation_changes`): `IN_BYTES`–`NUM_PKTS_UP_TO_128_BYTES` 0,001 nei Benign contro 0,9998 negli attacchi; `IN_PKTS`–`NUM_PKTS_UP_TO_128_BYTES` 0,006 contro 0,99999; `IN_BYTES`–`NUM_PKTS_512_TO_1024_BYTES` 0,95 contro 0,008. La correlazione globale mescola due regimi diversi.
- Le colonne SECOND_BYTES non compaiono in nessuna coppia. `[ipotesi]` contengono +inf e la cella non li sostituisce con NaN prima del calcolo: le loro correlazioni non sono valide.
- Le correlazioni sono calcolate su tutti i dati insieme: non provano che due colonne siano uguali.

#### Note per la pulizia

- Non togliere colonne solo perché |r| ≥ 0,999: prima si controlla l'uguaglianza riga per riga. Candidate: `LONGEST_FLOW_PKT`/`MAX_IP_PKT_LEN` (r = 1,000), `MIN_TTL`/`MAX_TTL` e `FLOW_DURATION_MILLISECONDS`/`DURATION_IN` (0,999).
- `FLOW_DURATION_MILLISECONDS` e `DURATION_IN` non sono la stessa colonna: la quota di zeri è diversa (in BoT-IoT 6,2% contro 12,0%) e `DURATION_IN` supera la durata del flusso in 11.277 righe. Eventualmente sostituirle con una differenza o un rapporto.
- Le altre coppie (0,90–0,997) descrivono relazioni plausibili: non vanno eliminate in automatico.
- Se SECOND_BYTES restano fuori dalle feature, escluderle anche da `corr_columns` (oppure sostituire ±inf con NaN prima di `.corr()`).

#### Note per l'addestramento

- GNN, LSTM e Transformer tollerano la ridondanza meglio dei modelli lineari: la correlazione serve a ridurre costo e dimensione, non come criterio finale di selezione. Va calcolata solo sul train.
- Visto il cambio di regime tra le classi, ogni selezione basata sulla correlazione globale va confermata con un'ablation.


## 7. Network entities


#### Osservazioni

- Ci sono 197.190 IP sorgente distinti e 37.900 IP destinazione, senza NULL. Per `Dataset`, gli IP sorgente sono 20 (BoT-IoT), 181.876 (CSE-CIC-IDS2018), 15.270 (ToN-IoT) e 40 (UNSW-NB15). Il traffico è dominato da pochi host privati: `192.168.1.32` con 5,67 milioni di flussi, `192.168.1.31` con 5,29 milioni, `192.168.100.147`–`150` con circa 4,1–4,3 milioni ciascuno.
- IP sorgente e classe (`ip_shortcut`, conteggio per IP, non pesato per flussi): BoT-IoT 12 IP solo Benign, 8 con entrambe le classi e nessuno solo attacco; CSE-CIC-IDS2018 195 solo attacco, 963 entrambe, 180.718 solo Benign; ToN-IoT 2 solo attacco, 24 entrambe, 15.244 solo Benign; UNSW-NB15 4 solo attacco, 36 solo Benign.
- In CSE-CIC-IDS2018 alcune classi di attacco vengono da un solo IP sorgente, con una sola destinazione (`source_ip_summary`): `18.221.219.4` ha 386.720 flussi (come `FTP-BruteForce`), `13.58.98.64` 188.474 (come `SSH-Bruteforce`), `13.59.126.31` 105.550 (come `DoS_attacks-SlowHTTPTest`), `18.219.193.20` 100.076 (come `DoS_attacks-Hulk`). `[ipotesi]` per queste classi l'IP identifica la classe: il numero di flussi coincide con la dimensione della classe.
- Porta di destinazione e classe (`port_shortcut`, valori distinti non pesati): in ToN-IoT tutte le 65.536 porte compaiono con entrambe le classi; in BoT-IoT 57.695 porte compaiono solo negli attacchi, 7.841 in entrambe e nessuna solo nei Benign; in UNSW-NB15 101 porte solo attacco e 58.856 solo Benign; in CSE-CIC-IDS2018 2 solo attacco e 61.418 solo Benign.
- 15 IP sorgente compaiono in più `Dataset` (14 in due, 1 in tre). `[ipotesi]` sono indirizzi privati riutilizzati in reti diverse: gli IP non sono stati stampati.

#### Note per la pulizia

- Niente da correggere. IP e porte vanno trattati come identificatori, non come feature numeriche.

#### Note per l'addestramento

- Escludere `IPV4_SRC_ADDR` e `IPV4_DST_ADDR` dalle feature. Nella GNN gli IP possono definire i nodi (la struttura del grafo), ma l'IP grezzo non deve finire tra gli attributi dei nodi.
- `L4_DST_PORT` come numero può essere una scorciatoia: in BoT-IoT molte porte compaiono solo negli attacchi, ma è un conteggio di valori distinti e BoT-IoT è quasi solo attacco, quindi va verificato. Usare fasce (well-known, registered, ephemeral) o includerla solo in ablation per `Dataset`.
- Provare anche uno split per host (gruppi di IP), oltre allo split temporale. Attenzione: le classi di CSE-CIC-IDS2018 che vengono da un solo IP finirebbero tutte in train o tutte in test.
- Lo stesso IP in sorgenti diverse non è lo stesso host: non costruire grafi o sequenze che attraversino i `Dataset`.


## 8. Timestamp

I timestamp permettono di ricostruire l’ordine temporale utile per LSTM e Transformer e per creare sequenze e finestre. I timestamp v3 potrebbero però contenere errori: vanno validati prima della costruzione delle sequenze e dello split temporale.


#### Osservazioni

- Intervalli UTC (`time_summary`): BoT-IoT dal 2018-05-15 al 2018-06-19 (6 giorni con dati), CSE-CIC-IDS2018 dal 2018-02-14 al 2018-03-02 (11 giorni), ToN-IoT dal 2019-04-23 al 2019-04-29 (7 giorni), UNSW-NB15 dal 2015-01-22 al 2015-02-18 (3 giorni: 22 e 23 gennaio, 18 febbraio, cioè due sessioni a circa 26 giorni di distanza). I periodi sono diversi e non si sovrappongono: le sorgenti non condividono una linea temporale.
- Nessuna riga ha `FLOW_END` < `FLOW_START` e non ci sono NULL; tutti i timestamp sono positivi e a 13 cifre (`timestamp_range`: 0 non positivi, 0 implausibili).
- Lo scarto (`FLOW_END` − `FLOW_START`) − `FLOW_DURATION_MILLISECONDS` vale solo −1, 0 o +1 ms in tutte le sorgenti (`duration_diff`), compatibile con un arrotondamento al millisecondo. −1 è il valore più frequente in ToN-IoT (17,0 milioni di righe, 61,8%) ed è presente anche in CSE-CIC-IDS2018 (4,09 milioni, 20,3%); BoT-IoT e UNSW-NB15 non lo hanno. `[ipotesi]` in CSE-CIC-IDS2018 e ToN-IoT la durata minima è 1 ms anche per i flussi con inizio e fine uguali (capitolo 3), e questo spiega il −1.
- Ordine di `row_id` rispetto a `FLOW_START` (`row_time_order`): ToN-IoT 0 inversioni, CSE-CIC-IDS2018 1, BoT-IoT 40.736 (0,24% delle coppie consecutive), UNSW-NB15 335.443 (14,2%: solo l'85,8% delle coppie è in ordine). Quindi `row_id` è cronologico in ToN-IoT e CSE-CIC-IDS2018, quasi cronologico in BoT-IoT e non cronologico in UNSW-NB15.
- Copertura temporale (`daily`, `attack_windows`): in BoT-IoT `DoS` e `DDoS` compaiono solo il 2018-06-04 (15,19 milioni di righe d'attacco, circa il 90% degli attacchi della sorgente), `Reconnaissance` tra il 15 e il 22 maggio e `Theft` solo il 18–19 giugno. In CSE-CIC-IDS2018 ogni attacco sta in un solo giorno (`Infilteration` in due) mentre il Benign c'è in tutti gli 11 giorni. In ToN-IoT ogni attacco occupa 1–2 giorni e il Benign tutti e 7. In UNSW-NB15 tutte le classi compaiono nelle due sessioni, con 17.462 attacchi il 22 gennaio e 110.231 il 18 febbraio.

#### Note per la pulizia

- Non c'è nessuna riga da eliminare per i timestamp: nessun intervallo invertito, nessun valore fuori scala, nessun NULL. Lo scarto di ±1 ms non va corretto.
- I controlli verificano la coerenza interna (inizio/fine, durata), non la correttezza assoluta di fuso e offset.

#### Note per l'addestramento

- Per costruire sequenze o finestre, ordinare per `Dataset` e `FLOW_START_MILLISECONDS` (a parità, `row_id`). Non usare `row_id` come ordine: è affidabile solo in ToN-IoT e CSE-CIC-IDS2018 (UNSW-NB15 14,2% di inversioni, BoT-IoT 0,24%).
- Non costruire sequenze che attraversino sorgenti diverse. In UNSW-NB15 e BoT-IoT interrompere la sequenza quando il salto temporale supera una soglia (le sessioni sono separate da giorni o settimane); la soglia va scelta guardando i salti reali, che qui non sono stati misurati.
- Uno split per giorni interi non funziona: toglierebbe intere classi di attacco da train o test (in CSE-CIC-IDS2018 e ToN-IoT ogni attacco sta in 1–2 giorni; in BoT-IoT `DoS` e `DDoS` solo il 4 giugno). Opzioni: split temporale dentro ogni episodio (per `Dataset`×`Attack`, primi X% del tempo in train e ultimi in test) con un intervallo di separazione (purge) per non condividere finestre; blocchi contigui per classe. Lo split casuale va bene solo come baseline sui singoli flussi, non per le sequenze.
- Le finestre non devono attraversare i confini tra gli split.
