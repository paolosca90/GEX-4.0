# Formule Tecniche e Logica di Calcolo - GEX 4.0

Questa documentazione descrive le formule matematiche e la logica algoritmica utilizzate per i calcoli del GEX, della gestione 0DTE e del Power Meter nel sistema.

---

## 1. Gamma Exposure (GEX)

Il GEX misura l'esposizione al Gamma dei market maker. Nel nostro sistema, viene calcolato per ogni strike price delle opzioni SPX e QQQ.

### Formula di Calcolo
Per ogni singolo contratto (opzione):
$$GEX_{strike} = \text{Gamma} \times \text{Open Interest} \times 100 \times \text{Spot Price}$$

*   **Gamma**: La variazione del Delta dell'opzione rispetto al prezzo del sottostante.
*   **Open Interest (OI)**: Numero totale di contratti aperti per quello strike.
*   **100**: Moltiplicatore standard per i contratti di opzione (1 contratto = 100 azioni/unità).
*   **Spot Price**: Il prezzo corrente dell'indice sottostante (SPX o QQQ).

### Segnatura
*   **Call GEX**: Valore positivo (+).
*   **Put GEX**: Valore negativo (-).
*   **Total GEX per Strike**: La somma algebrica del GEX di tutte le Call e Put su quello specifico livello di strike.

---

## 2. Gestione 0DTE (Zero Days To Expiration)

Il sistema isola specificamente le opzioni che scadono nella giornata corrente (o la successiva se il mercato è chiuso).

### Logica di Selezione
*   Vengono filtrate solo le opzioni con data di scadenza uguale alla data target del calcolo.
*   **Puntamento Orario**: Alle 16:30 EST (chiusura mercato), il sistema sposta automaticamente il calcolo sulla data di scadenza del giorno di trading successivo.

---

## 3. Power Meter (Analisi del Flusso Opzioni)

Il Power Meter elabora il "Tape" in tempo reale applicando una pesatura algoritmica per distinguere tra成交 (eseguiti) istituzionali, retail e rumore di fondo.

### A. Determinazione del Sentiment (Algoritmo Bid/Ask Proximity)
Ogni trade viene classificato come **BUY** (aggressività in acquisto) o **SELL** (aggressività in vendita) basandosi sulla vicinanza ai prezzi Bid/Ask.

1.  **Spread Normale**:
    *   Price $\ge$ Ask $\rightarrow$ **BUY**
    *   Price $\le$ Bid $\rightarrow$ **SELL**
    *   Price $>$ Mid $\rightarrow$ **Leans BUY**
    *   Price $<$ Mid $\rightarrow$ **Leans SELL**

2.  **Wide Spread Neutrality** (Spread $> \$0.50$):
    *   Viene definita una "zona morta" centrale. Il trade deve essere entro il **25%** del bordo della fascia Bid-Ask per essere considerato direzionale. Se cade nel centro, viene ignorato (**NONE/Noise**).

### B. Pesatura del Volume (Combined Multiplier)
Il valore del premio grezzo ($Price \times Size \times 100$) viene moltiplicato per un `final_multiplier` composto da tre fattori:

#### 1. Block Trade Discounting (Dampening Logaritmico)
Se la dimensione (`size`) è superiore a 200 contratti, il peso viene ridotto logaritmicamente per evitare che singoli "Block Trades" distorcano eccessivamente l'indicatore.
$$W_{block} = \frac{\ln(200 + 1)}{\ln(\text{size} + 1)}$$

#### 2. Urgency Weight (Aggressività)
*   Esecuzione **al mercato** (at Bid/Ask): **1.5x** (indica alta urgenza).
*   Esecuzione **interna** (leaning Mid): **0.8x** (indica bassa urgenza).

#### 3. Distance-to-Spot Weight (Proxy Delta)
Le opzioni ATM (At-The-Money) hanno un peso maggiore rispetto alle OTM lontane.
$$W_{dist} = \max(0.1, 1.0 - (\text{distanza\%} \times 10))$$
*   Sconto lineare: 0% distanza = 1.0, 10% distanza = 0.1 (minimo).

### C. Filtro OTM (Out-of-the-Money)
Per ridurre il rumore generato dalle opzioni ITM (In-The-Money) che si muovono quasi linearmente con l'indice (Delta $\approx 1$), il sistema le esclude:
*   **Ignora CALL** se Strike $\le$ Spot Price.
*   **Ignora PUT** se Strike $\ge$ Spot Price.

### Calcolo Finale del Premio Pesato
$$\text{Weighted Premium} = (\text{Price} \times \text{Size} \times 100) \times (W_{block} \times W_{urgency} \times W_{dist})$$

---

## 4. Net Flow e Net Drift (EMA 5)

Questi indicatori misurano l'andamento dei premi opzioni su base temporale.

### A. Net Flow (Flusso Netto a 1 Minuto)
È il "bilancio" immediato del mercato negli ultimi 60 secondi.

#### Come si calcola (Passo dopo passo):
1.  **Raccolta**: Il sistema guarda tutti i trade avvenuti negli ultimi 60 secondi.
2.  **Pesatura**: Per ogni singolo trade, viene calcolato il valore monetario (Premio) e applicati i filtri (es. se è un grosso blocco viene ridimensionato, se è aggressivo viene potenziato).
3.  **Somma algebrica**: 
    *   I premi dei trade in **ACQUISTO** vengono **aggiunti** al totale.
    *   I premi dei trade in **VENDITA** vengono **sottratti** dal totale.
4.  **Risultato**: Quello che resta è il **Net Flow**. Se il numero è positivo, c'è più pressione in acquisto; se è negativo, in vendita.

---

### B. Net Drift EMA 5 (Flusso Esponenziale a 5 Minuti)
Il Net Drift utilizza una media mobile esponenziale (**EMA**) per gestire la finestra temporale di 5 minuti.

#### Spiegazione Semplice (Il concetto di "Memoria")
Immagina che il mercato abbia una "memoria" che sfuma col tempo:
*   Un trade enorme appena avvenuto è **freschissimo** e sposta l'indicatore in modo deciso.
*   Passati 2 minuti, quel trade inizia a essere "dimenticato" (perde il 63% del suo peso).
*   Dopo 5 minuti, viene quasi completamente rimosso dal calcolo.

**In breve:** Il Net Drift è come una scia termica: la parte più vicina all'oggetto è la più calda (più pesante), mentre la scia lasciata indietro si raffredda rapidamente.

#### Come si calcola (Passo dopo passo):
1.  **Finestra**: Si prendono tutti i trade degli ultimi 5 minuti.
2.  **Freschezza**: Ad ogni trade viene assegnato un "moltiplicatore di freschezza" in base a quanto tempo fa è avvenuto.
    *   Appena eseguito $\rightarrow$ Moltiplicatore 1.0 (100% del peso).
    *   Dopo 2 minuti $\rightarrow$ Moltiplicatore 0.37 (37% del peso).
    *   Quasi 5 minuti $\rightarrow$ Moltiplicatore vicino a 0.
3.  **Accumulo**: Si moltiplica il valore del trade per la sua freschezza e si sommano tutti insieme (sempre aggiungendo gli acquisti e sottraendo le vendite).
4.  **Risultato**: Otteniamo un indicatore che "scivola" nel tempo, dando sempre priorità a ciò che sta accadendo **adesso**.

#### Perché è Importante?
Il Net Drift è il "cuore pulsante" del Power Meter per tre ragioni fondamentali:

1.  **Reattività Immediata (Trend Detection)**: A differenza di una media semplice che aspetta minuti per muoversi, l'EMA reagisce istantaneamente se arriva un "Golden Sweep" (una raffica di acquisti aggressivi). Ti permette di vedere il cambio di direzione *mentre accade*.
2.  **Filtraggio del Rumore**: Se arriva un singolo grosso ordine isolato (magari una copertura tecnica) e poi non succede più nulla, il Net Drift lo assorbe e lo fa decadere velocemente. Se invece il flusso continua, l'indicatore continua a salire, confermando un **trend reale**.
3.  **Individuazione delle Inversioni**: Quando il Net Drift incrocia lo zero o cambia bruscamente pendenza, è spesso il primo segnale che la pressione dei Market Maker sta cambiando, anticipando spesso il movimento del prezzo (Spot Price).

**La formula tecnica (Time Decay):**
Il sistema applica un decadimento esponenziale con una costante di tempo ($\tau$) di 120 secondi.
$$\text{Net Drift} = \Sigma \left( \text{Net Premium} \times e^{-\frac{\Delta t}{\tau}} \right)$$
*   **$\Delta t$**: Tempo trascorso dall'esecuzione del trade.
*   **$\tau = 120$s**: I trade più vecchi di 2 minuti perdono gradualmente peso per mantenere l'indicatore sempre "fresco".
