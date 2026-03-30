<div align="center">
  <img src="./logo.png" alt="QuantumGEX Logo" width="200" />
  <h1>Guida Utente: QuantumGEX v4.0</h1>
  <p><i>Il sistema avanzato per il monitoraggio in tempo reale del Gamma Exposure (GEX) e dei flussi Smart Money</i></p>
</div>

---

## 1. Panoramica del Sistema

**QuantumGEX** ti offre una lente d'ingrandimento istituzionale sulla reale struttura del mercato. Attraverso l'analisi in tempo reale del posizionamento dei Market Maker (Dealers), la piattaforma rivela dove si trovano i veri livelli di supporto e resistenza per i mercati principali:
* **S&P 500** (Futures ES / Sottostante SPX)
* **NASDAQ 100** (Futures NQ / Sottostante QQQ)

Tutti i dati vengono processati in **stream continuo**, incrociando i prezzi in millisecondi di cTrader con l'esauriente e complessa mole di dati delle catene di opzioni 0DTE via Tradier API.

---

## 2. Interfaccia Principale e "Spade Laser" (GEX)

L'interfaccia principale fonde l'azione del prezzo (Price Action) direttamente con l'esposizione al Gamma dei Market Maker, disegnando le iconiche "*Spade Laser*" (livelli orizzontali) esattamente dove i Dealers hanno le loro barriere protettive.

<div align="center">
  <img src="./dashboard_main.png" alt="QuantumGEX Main View" width="800" />
  <p><i>Figura 1: Schermata principale di QuantumGEX che mostra il Gamma Flip (Linea Gialla) e le barriere GEX (Rosso/Verde).</i></p>
</div>

### 2.1 La Linea Gialla: Il "Gamma Flip" (Zero GEX)
Il livello più critico visibile a schermo è la **spessa e brillante linea Gialla** (marcata con l'etichetta testuale `0GEX: [Prezzo]` nell'header).
Questo è lo **spartiacque strutturale** del mercato: il punto matematico in cui l'esposizione netta dei Dealer passa dall'essere positiva (Mean Reverting) all'essere negativa (Alta Volatilità).

* **Prezzo > Linea Gialla (Gamma Positivo)**: Il mercato è "denso" e stabile. I Dealer vendono sui rialzi e comprano sui ribassi per coprirsi. **I livelli tendono a reggere**.
* **Prezzo < Linea Gialla (Gamma Negativo)**: Il mercato è in "panico" strutturale. I Dealer sono costretti a vendere quando il mercato scende e comprare quando sale. **I livelli diventano fragili o magneti direzionali**.

### 2.2 Livelli di Supporto e Resistenza (I Colori)
L'intensità luminosa (opacità) di proporziona all'importanza del livello (GEX Size). Il colore e lo stile della linea hanno un preciso significato operativo:

* 🔴 **Linee Rosse (Call GEX - Resistenze)**: Qui si ammassano i contratti Call. 
* 🟢 **Linee Verdi (Put GEX - Supporti)**: Qui si ammassano i contratti Put. 

### 2.3 Stile delle Linee (Il Contesto)
Per permetterti di valutare la *robustezza* di questi livelli istantaneamente, QuantumGEX adatta lo stile della riga in base a dove si trova il prezzo rispetto al Gamma Flip:

* ➖ **Linee Continue (Solid)**: Compaiono quando il prezzo è nella zona di Gamma Positivo. Indicano un **Muro di Cemento**. Questi livelli offrono ottime probabilità di respingere il prezzo e causare rimbalzi (mean-reversion strutturale).
* 🧻 **Linee Tratteggiate (Dashed)**: Compaiono quando il prezzo è nella zona di Gamma Negativo. Indicano un **Muro di Cartongesso** o un "Magnete". La volatilità elevata può far cedere questi livelli facilmente, accelerando il trend piuttosto che fermarlo.

---

## 3. Lo Smart Money Box (Power Meter)

Il pannello *Smart Money Box* traduce il devastante e caotico flusso degli ordini in opzioni (Order Flow) in un indicatore chiaro della convinzione istituzionale in quel preciso momento. 

<div align="center">
  <img src="./smart_money_new.png" alt="Smart Money Power Meter" width="400" />
  <p><i>Figura 2: Lo Smart Money Box con visualizzazione della divergenza Call/Put.</i></p>
</div>

### 3.1 Net Drift EMA 5m (Il "Capo Assoluto")
Il cuore pulsante del Power Meter è l'indicatore verde/rosso centrale: la **Smart Money Conviction**.
* Calcolato tramite un **EMA (Exponential Moving Average) a 5 minuti**, premia le "Sweep" urgenti a mercato e le trade massicce vicine al prezzo Spot, scontando contemporaneamente i Block Trade giganteschi ma neutrali.
* **Segnale Cromatico**: Se la lancetta è sul lato verde e il valore è positivo (+XX K), i capitali istituzionali stanno attivamente spingendo (Drifting) il mercato al rialzo.

### 3.2 Dual Bars (Volume vs Premium) e Segnali "Trap"
Sotto la Conviction EMA trovi due barre a percentuale:
- **Premium Bar**: (Il vero Smart Money) Indica chi sta spendendo più Dollari reali (Calls o Puts).
- **Volume Bar**: (Lo Swarm/Retail) Indica su che fronte si scambiano più fogli di carta (contratti puri).

Il display testuale in alto fonde l'EMA con queste barre per fornirti non solo la direzione del trend (`STRONG CALL/PUT TREND`), ma anche allarmi su comportamenti anomali (Divergenze e Trappole):

* 🚨 **BEAR TRAP (SQZ UP)**: SPX sale (EMA Bullish), le Put hanno alti volumi (Retail è spaventato o copre corti), ma il mercato reale viene comprato. Ottimo momento per long squishy.
* 🚨 **BULL TRAP (DUMP)**: SPX scende (EMA Bearish), il Retail sta disperatamente comprando Call sperando in un the bottom, ma i grossi attori scaricano. Crollo imminente.
* ⚠️ **VOL / DRIFT DIV**: Disaccordo netto tra la spesa dei grossi calibri (Drift piatto o opposto) e il mero traffico dei volumi. Momento per stare a bordo campo.
* ⚪ **NEUTRAL DRIFT**: Volumi irrisori netti (< 10.000$). Assenza di spinta algoritmica, rumore di fondo.

---

## 4. Troubleshooting (Domande Frequenti)

* **Il Pannello Smart Money scompare o si blocca su "Offline"?**
  Se non passano tick per 60 secondi (e siamo in orario di borsa), l'app va in protezione per evitare di mostrare segnali vecchi. Aggiorna semplicemente la pagina (F5).
* **Posso spostare i pannelli?**
  Sì! Clicca e trascina la scatola dello Smart Money dove ti è più comoda sul grafico.
* **Come leggo lo zero GEX sul Nasdaq?**
  A differenza del SPX, il QQQ è spesso sbilanciato in modo mostruoso verso le Put. Il motore logico di QuantumGEX usa l'algoritmo alla base della *"Gamma Valley"*, e trova il punto matematico minuzioso del Flip, senza falsi allarmi, regalandoti un righello inossidabile.
