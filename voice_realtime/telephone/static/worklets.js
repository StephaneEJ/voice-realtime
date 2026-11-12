// Worklets audio de la page téléphone.
//
// « capture » : micro (fréquence du contexte, souvent 48 kHz) → filtre moyenneur
// anti-repliement → rééchantillonnage linéaire vers la fréquence demandée par le
// serveur → trames PCM16 de 20 ms envoyées au fil principal.
// « lecture » : file de blocs Float32 déjà à la fréquence du contexte, vidée
// d'un coup sur coupure de parole.

class Capture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const cible = options.processorOptions.cible;
    this.pas = sampleRate / cible;
    this.largeur = Math.max(1, Math.round(this.pas));
    this.historique = new Float32Array(this.largeur);
    this.indexHisto = 0;
    this.somme = 0;
    this.precedent = 0;
    this.t = 0;
    this.longueurTrame = Math.round(cible * 0.02);
    this.trame = new Int16Array(this.longueurTrame);
    this.n = 0;
    this.carres = 0;
  }

  lisser(x) {
    // Moyenne glissante sur `largeur` échantillons (coupe au-dessus de ~cible/2).
    this.somme += x - this.historique[this.indexHisto];
    this.historique[this.indexHisto] = x;
    this.indexHisto = (this.indexHisto + 1) % this.largeur;
    return this.somme / this.largeur;
  }

  pousser(v) {
    const s = Math.max(-1, Math.min(1, v));
    this.carres += s * s;
    this.trame[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    if (this.n === this.longueurTrame) {
      const niveau = Math.sqrt(this.carres / this.n);
      const pcm = this.trame;
      // Le tampon est transféré (détaché ensuite) : ne plus lire `pcm.length`.
      this.port.postMessage({ pcm: pcm.buffer, niveau }, [pcm.buffer]);
      this.trame = new Int16Array(this.longueurTrame);
      this.n = 0;
      this.carres = 0;
    }
  }

  process(entrees) {
    const canal = entrees[0] && entrees[0][0];
    if (!canal) return true;
    const lisse = new Float32Array(canal.length);
    for (let i = 0; i < canal.length; i++) lisse[i] = this.lisser(canal[i]);
    // Positions t dans [-1, n-1] : -1 désigne le dernier échantillon du bloc précédent.
    let t = this.t;
    const dernier = lisse.length - 1;
    while (t <= dernier) {
      const i0 = Math.floor(t);
      const f = t - i0;
      const a = i0 < 0 ? this.precedent : lisse[i0];
      const b = i0 + 1 <= dernier ? lisse[i0 + 1] : a;
      this.pousser(a + (b - a) * f);
      t += this.pas;
    }
    this.t = t - lisse.length;
    this.precedent = lisse[dernier];
    return true;
  }
}

class Lecture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.file = [];
    this.tete = 0;
    this.joues = 0;
    this.attente = 0;
    this.actif = false;
    this.compteur = 0;
    this.port.onmessage = (e) => {
      if (e.data === "vider") {
        this.attente = 0;
        this.file = [];
        this.tete = 0;
      } else {
        this.file.push(e.data);
        this.attente += e.data.length;
      }
    };
  }

  process(entrees, sorties) {
    const sortie = sorties[0][0];
    let i = 0;
    let carres = 0;
    while (i < sortie.length && this.file.length) {
      const bloc = this.file[0];
      const n = Math.min(sortie.length - i, bloc.length - this.tete);
      for (let k = 0; k < n; k++) {
        const v = bloc[this.tete + k];
        sortie[i + k] = v;
        carres += v * v;
      }
      i += n;
      this.tete += n;
      if (this.tete >= bloc.length) {
        this.file.shift();
        this.tete = 0;
      }
    }
    this.joues += i;
    this.attente = Math.max(0, this.attente - i);
    if (i < sortie.length) sortie.fill(0, i);
    for (let c = 1; c < sorties[0].length; c++) sorties[0][c].set(sortie);
    const actif = i > 0;
    this.compteur += sortie.length;
    if (actif !== this.actif || this.compteur >= sampleRate / 20) {
      this.port.postMessage({ joues: this.joues, attente: this.attente, actif, niveau: Math.sqrt(carres / sortie.length) });
      this.actif = actif;
      this.compteur = 0;
    }
    return true;
  }
}

registerProcessor("capture", Capture);
registerProcessor("lecture", Lecture);
