# Intrusion Detection su dataset NetFlow (NF-UQ-NIDS v2 e v3)

## 1. Struttura

```
intrusion_detection/
│
├── .venv/                          # Ambiente virtuale (non versionato)
│
├── config/
│   └── config.yaml                 # Configurazione del progetto
│
├── data/                           # NON versionata (vedi .gitignore)
│   ├── raw_csv/                    # Dataset originali scaricati manualmente
│   │   ├── v2/
│   │   │   ├── NF-BoT-IoT-v2.csv
│   │   │   ├── NF-CSE-CIC-IDS2018-v2.csv
│   │   │   ├── NF-ToN-IoT-v2.csv
│   │   │   └── NF-UNSW-NB15-v2.csv
│   │   └── v3/
│   │       ├── NF-BoT-IoT-v3.csv
│   │       ├── NF-CSE-CIC-IDS2018-v3.csv
│   │       ├── NF-ToN-IoT-v3.csv
│   │       └── NF-UNSW-NB15-v3.csv
│   │
│   └── parquet/                    # Generata dall'ingestion
│       ├── v2/
│       └── v3/
│
├── notebooks/
│   ├── eda_v2.ipynb                # EDA versione 2 (con output già eseguiti)
│   ├── eda_v2.md                   # Esportazione in Markdown
│   ├── eda_v3.ipynb                # EDA versione 3 (con output già eseguiti)
│   └── eda_v3.md                   # Esportazione in Markdown
│
├── src/
│   ├── ingestion_v2.py             # Conversione CSV → Parquet (v2)
│   └── ingestion_v3.py             # Conversione CSV → Parquet (v3)
│
├── .gitignore
├── README.md
└── requirements.txt                # Dipendenze del progetto
```

---

## 2. Replicabilità

Per riprodurre il progetto seguire i passaggi nell'ordine indicato.

### 2.1 Clonare il repository e installare le dipendenze

```bash
git clone <url-del-repository>
cd intrusion_detection

python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

Tutte le librerie necessarie sono elencate in `requirements.txt`.

### 2.2 Creare la cartella `data/`

La cartella `data/` è inclusa nel `.gitignore` per evitare di occupare spazio eccessivo su GitHub (i dataset pesano diversi GB). Non è quindi presente dopo il clone e va **creata manualmente**:

```bash
mkdir -p data/raw_csv/v2 data/raw_csv/v3
```

La sottocartella `data/parquet/` e le sue sottocartelle vengono popolate dall'ingestion (vedi 2.4).

### 2.3 Scaricare i dataset

I dataset vanno scaricati **manualmente** dalla pagina ufficiale:

<https://www.cyber.uq.edu.au/project/machine-learning-based-nids-datasets>

Scaricare, per **entrambe le versioni (v2 e v3)**, i quattro sotto-dataset (BoT-IoT, CSE-CIC-IDS2018, ToN-IoT, UNSW-NB15) e inserire i file CSV nelle rispettive cartelle:

- file v2 → `data/raw_csv/v2/`
- file v3 → `data/raw_csv/v3/`

I nomi dei file devono coincidere con quelli riportati nella struttura al punto 1.

### 2.4 Eseguire l'ingestion

L'ingestion legge i CSV grezzi e genera i file **Parquet** (formato colonnare più compatto e più veloce da leggere), salvati in `data/parquet/v2/` e `data/parquet/v3/`.

```bash
python src/ingestion_v2.py
python src/ingestion_v3.py
```

### 2.5 (Opzionale) Rieseguire i notebook di EDA

I notebook in `notebooks/` possono essere rieseguiti per riprodurre l'analisi esplorativa:

- `eda_v2.ipynb`
- `eda_v3.ipynb`

> **Non è consigliato rieseguirli:** l'elaborazione di dataset di queste dimensioni richiede molto tempo. I notebook sono già salvati **con i risultati dell'esecuzione** (e ne è disponibile anche la versione `.md`), quindi è possibile consultare l'analisi direttamente senza ripetere i calcoli.

---

## Note

- `.venv/` e `data/` non sono versionati: vanno ricreati localmente come descritto sopra.
- Questo repository copre la fase di ingestion ed EDA; l'addestramento dei modelli LSTM, GNN e Transformer verrà aggiunto nelle fasi successive.