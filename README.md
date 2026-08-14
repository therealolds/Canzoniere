# Canzoniere Scout

Sito statico con testi e accordi, raggruppati per categoria, con ricerca,
attivazione/disattivazione accordi, trasposizione (per chi suona) e uso offline.

## Come vedere il sito in locale

I browser bloccano i moduli JS e `fetch` sui file aperti con `file://`,
quindi serve un piccolo server locale:

```sh
py -m http.server 8123
```

Poi apri <http://localhost:8123> nel browser.

> Nota: su questo PC usa `py` (non `python`, che è un collegamento al Microsoft Store).

## Aggiungere o modificare una canzone

1. Crea un file in `songs/`, es. `songs/nome-canzone.cho` (nome file = slug URL).
2. Scrivi la canzone in formato **ChordPro** (vedi sotto).
3. Rigenera l'indice:
   ```sh
   py scripts/build_index.py
   ```
4. Ricarica il sito. Fatto. (Per pubblicare: commit + push.)

## Formato ChordPro (Italiano)

Gli accordi vanno **fra parentesi quadre**, subito prima della sillaba su cui cadono.
Accordi in notazione italiana: `DO RE MI FA SOL LA SI`, con `#`/`b` e suffissi
(`m`, `7`, `sus4`, `/SOL`…).

```
{title: Titolo della canzone}
{subtitle: Autore (facoltativo)}
{categories: preghiera}          # preghiera | italiane | internazionali | scout (una o più, separate da virgola)
{key: LA}                        # tono di riferimento (facoltativo)

[MI]Testo con l'accordo [LA]sopra la sillaba giusta

{start_of_chorus}
Righe del ritornello (evidenziate)
{end_of_chorus}

{comment: Rit.}                  # etichetta/annotazione
```

Una riga vuota separa le strofe.

## Struttura del progetto

```
index.html            pagina principale
src/
  app.js              routing, ricerca, vista canzone, toggle/trasposizione
  chordpro.js         parser + trasposizione italiana + rendering (nessuna dipendenza)
  style.css           stile
songs/                una canzone per file .cho  ← QUI si aggiungono i canti
songs.json            indice generato (NON modificare a mano)
scripts/
  build_index.py      genera songs.json dai file in songs/
  make_icons.py       (ri)genera le icone dell'app
manifest.webmanifest  configurazione PWA (installabile / offline)
sw.js                 service worker (cache offline)
icons/                icone dell'app (segnaposto, sostituibili)
```

## Pubblicazione (GitHub Pages)

1. Crea un repository e fai push di questi file.
2. Impostazioni del repo → Pages → Deploy from a branch → `main` / root.
3. Il sito è statico: Pages lo serve così com'è, nessuna build lato server.

Ad ogni nuovo canto: aggiungi il `.cho`, esegui `py scripts/build_index.py`,
poi commit + push.
