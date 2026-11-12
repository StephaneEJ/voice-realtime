// Page téléphone de voice-realtime : micro du navigateur (traitement WebRTC :
// annulation d'écho, réduction de bruit, gain automatique) ↔ serveur du Mac par
// WebSocket. Le serveur annonce les fréquences ; la page rééchantillonne.
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const el = {
    appel: $("appel"), libelle: $("appel-libelle"), anneau: $("anneau"), etat: $("etat"),
    fournisseur: $("fournisseur"), muet: $("muet"), duree: $("duree"), journal: $("journal"),
    saisie: $("saisie"), texte: $("saisie-texte"), envoi: $("saisie-envoi"),
    avert: $("avertissement"), niveauMicro: $("niveau-micro"), niveauVoix: $("niveau-voix"),
  };

  const MOTIFS = {
    raccroche: "Appel terminé", mot_arret: "Mot d'arrêt entendu", duree_max: "Durée maximale atteinte",
    cout_max: "Plafond de coût atteint", deconnexion: "Connexion perdue", erreur_fournisseur: "Erreur du fournisseur",
    fournisseur_ferme: "Le fournisseur a fermé la session", arret_serveur: "Serveur arrêté",
  };

  // État lisible par l'essai automatisé (scripts/essai_telephone_chrome.py).
  const suivi = {
    etat: "repos", evenements: [], octetsEnvoyes: 0, echantillonsRecus: 0, echantillonsJoues: 0,
    interruptions: 0, fin: null, frequenceContexte: 0, erreurs: [],
  };
  window.__telephone = suivi;

  let ctx = null, flux = null, ws = null, capture = null, lecture = null, source = null, puits = null;
  let verrouEcran = null, minuteur = null, debut = 0, muet = false, outilsEnCours = 0, voixActive = false;
  let freqSortie = 24000, resteLecture = null, positionLecture = 0;
  let partielCourant = { utilisateur: null, modele: null };

  function noter(ev) {
    suivi.evenements.push(ev);
    if (suivi.evenements.length > 200) suivi.evenements.shift();
  }

  function afficherEtat(etat, texte) {
    suivi.etat = etat;
    el.anneau.dataset.etat = etat;
    el.etat.textContent = texte;
  }

  function rafraichirEtat() {
    if (!ws) return;
    if (outilsEnCours > 0) afficherEtat("outil", "Jarvis consulte tes sessions…");
    else if (voixActive) afficherEtat("parle", "Jarvis parle");
    else if (muet) afficherEtat("ecoute", "Micro coupé");
    else afficherEtat("ecoute", "Je t'écoute");
  }

  function avertir(message) {
    el.avert.textContent = message;
    el.avert.hidden = !message;
  }

  function ligne(role, texte, final) {
    let li = partielCourant[role];
    if (!li || li.dataset.final === "1") {
      li = document.createElement("li");
      li.className = role;
      el.journal.appendChild(li);
      while (el.journal.children.length > 60) el.journal.removeChild(el.journal.firstChild);
    }
    // Textes du modèle et des sessions : données, jamais du HTML.
    if (final) {
      li.textContent = texte;
      li.dataset.final = "1";
      li.classList.remove("partiel");
      partielCourant[role] = null;
    } else {
      const avant = li.dataset.final === "0" ? li.textContent : "";
      // Le mode chaîne envoie une phrase par partiel, sans espace de liaison.
      const liaison = /[.!?…]$/.test(avant) && !/^\s/.test(texte) ? " " : "";
      li.textContent = avant + liaison + texte;
      li.dataset.final = "0";
      li.classList.add("partiel");
      partielCourant[role] = li;
    }
    li.scrollIntoView({ block: "end", behavior: "smooth" });
  }

  function systeme(texte) {
    const li = document.createElement("li");
    li.className = "systeme";
    li.textContent = texte;
    el.journal.appendChild(li);
    li.scrollIntoView({ block: "end" });
  }

  function niveau(barre, v) {
    barre.style.width = `${Math.min(100, Math.round(Math.sqrt(v) * 160))}%`;
  }

  function horloge() {
    const s = Math.floor((performance.now() - debut) / 1000);
    el.duree.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  // PCM16 (freqSortie) → Float32 (fréquence du contexte), interpolation linéaire
  // continue d'un bloc à l'autre.
  function versLecture(buffer) {
    const pcm = new Int16Array(buffer);
    suivi.echantillonsRecus += pcm.length;
    const n = pcm.length;
    if (!n || !lecture) return;
    const pas = freqSortie / ctx.sampleRate;
    const precedent = resteLecture === null ? pcm[0] / 32768 : resteLecture;
    const lire = (i) => (i < 0 ? precedent : pcm[i] / 32768);
    const sortie = [];
    let t = positionLecture;
    while (t <= n - 1) {
      const i0 = Math.floor(t);
      const f = t - i0;
      const a = lire(i0);
      const b = i0 + 1 <= n - 1 ? lire(i0 + 1) : a;
      sortie.push(a + (b - a) * f);
      t += pas;
    }
    positionLecture = t - n;
    resteLecture = pcm[n - 1] / 32768;
    const bloc = Float32Array.from(sortie);
    lecture.port.postMessage(bloc, [bloc.buffer]);
  }

  function viderLecture() {
    if (lecture) lecture.port.postMessage("vider");
    resteLecture = null;
    positionLecture = 0;
  }

  function surMessage(message) {
    if (message.data instanceof ArrayBuffer) {
      versLecture(message.data);
      return;
    }
    let ev;
    try { ev = JSON.parse(message.data); } catch { return; }
    noter(ev);
    switch (ev.ev) {
      case "pret":
        freqSortie = ev.sortie;
        el.fournisseur.textContent = ev.fournisseur;
        brancherCapture(ev.entree);
        const n = ev.outils ? ev.outils.length : 0;
        systeme(n ? `Connecté · ${n} outil${n > 1 ? "s" : ""}` : "Connecté");
        rafraichirEtat();
        break;
      case "transcription":
        ligne(ev.role === "utilisateur" ? "utilisateur" : "modele", ev.texte, ev.final);
        break;
      case "interrompu":
        suivi.interruptions += 1;
        viderLecture();
        partielCourant.modele = null;
        break;
      case "outil":
        outilsEnCours = Math.max(0, outilsEnCours + (ev.etape === "appel" ? 1 : -1));
        if (ev.etape === "resultat") systeme(`${ev.nom} : ${ev.ok ? "fait" : "échec"}`);
        rafraichirEtat();
        break;
      case "muet":
        muet = !!ev.actif;
        el.muet.setAttribute("aria-pressed", String(muet));
        el.muet.textContent = muet ? "Micro coupé" : "Muet";
        rafraichirEtat();
        break;
      case "erreur":
        suivi.erreurs.push(ev.code);
        if (ev.code === "occupe") avertir("Un appel est déjà en cours sur le Mac.");
        else systeme(`Erreur : ${ev.code}`);
        break;
      case "fin":
        suivi.fin = ev.motif;
        systeme(MOTIFS[ev.motif] || `Fin : ${ev.motif}`);
        break;
      default:
        break;
    }
  }

  function brancherCapture(frequence) {
    source = ctx.createMediaStreamSource(flux);
    capture = new AudioWorkletNode(ctx, "capture", { processorOptions: { cible: frequence } });
    capture.port.onmessage = (e) => {
      niveau(el.niveauMicro, muet ? 0 : e.data.niveau);
      if (!muet && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data.pcm);
        suivi.octetsEnvoyes += e.data.pcm.byteLength;
      }
    };
    // Un nœud non relié à la sortie n'est pas cadencé partout : gain nul.
    puits = ctx.createGain();
    puits.gain.value = 0;
    source.connect(capture).connect(puits).connect(ctx.destination);
  }

  async function demarrer() {
    avertir("");
    if (!window.isSecureContext || !navigator.mediaDevices || !window.AudioWorkletNode) {
      avertir("Le micro exige une page sécurisée (HTTPS, ou localhost sur le Mac) et un navigateur récent.");
      return;
    }
    el.appel.disabled = true;
    afficherEtat("connexion", "Connexion…");
    try {
      ctx = new AudioContext({ latencyHint: "interactive" });
      await ctx.resume();
      suivi.frequenceContexte = ctx.sampleRate;
      flux = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      // Adresses relatives : la page fonctionne aussi sous un préfixe public (relais du Worker).
      await ctx.audioWorklet.addModule(new URL("worklets.js", location.href).href);
      lecture = new AudioWorkletNode(ctx, "lecture", { outputChannelCount: [1] });
      lecture.port.onmessage = (e) => {
        suivi.echantillonsJoues = e.data.joues;
        niveau(el.niveauVoix, e.data.niveau);
        if (e.data.actif !== voixActive) {
          voixActive = e.data.actif;
          rafraichirEtat();
        }
      };
      lecture.connect(ctx.destination);
    } catch (err) {
      suivi.erreurs.push(String(err && err.name));
      avertir(err && err.name === "NotAllowedError" ? "Accès au micro refusé." : `Micro indisponible (${err && err.name}).`);
      await raccrocher(false);
      return;
    }

    const adresse = new URL("ws", location.href);
    adresse.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(adresse.href);
    ws = socket;
    ws.binaryType = "arraybuffer";
    ws.onmessage = surMessage;
    ws.onopen = () => {
      debut = performance.now();
      minuteur = setInterval(horloge, 1000);
      el.appel.disabled = false;
      el.appel.classList.add("en-cours");
      el.appel.setAttribute("aria-label", "Raccrocher");
      el.libelle.textContent = "Raccrocher";
      el.muet.disabled = el.texte.disabled = el.envoi.disabled = false;
    };
    // Un ancien appel qui se ferme en retard ne coupe pas le suivant.
    ws.onclose = () => { if (ws === socket) raccrocher(false); };
    ws.onerror = () => { suivi.erreurs.push("websocket"); };
    try { verrouEcran = await navigator.wakeLock?.request("screen"); } catch { verrouEcran = null; }
  }

  async function raccrocher(envoyer = true) {
    if (envoyer && ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ op: "raccrocher" }));
    const w = ws;
    ws = null;
    if (w && w.readyState <= WebSocket.OPEN) { try { w.close(1000); } catch { /* déjà fermé */ } }
    clearInterval(minuteur);
    if (flux) flux.getTracks().forEach((p) => p.stop());
    if (ctx) { try { await ctx.close(); } catch { /* déjà fermé */ } }
    if (verrouEcran) { try { await verrouEcran.release(); } catch { /* relâché */ } }
    ctx = flux = capture = lecture = source = puits = verrouEcran = null;
    muet = false; outilsEnCours = 0; voixActive = false; resteLecture = null; positionLecture = 0;
    niveau(el.niveauMicro, 0); niveau(el.niveauVoix, 0);
    el.appel.disabled = false;
    el.appel.classList.remove("en-cours");
    el.appel.setAttribute("aria-label", "Appeler");
    el.libelle.textContent = "Appeler";
    el.muet.disabled = el.texte.disabled = el.envoi.disabled = true;
    el.muet.setAttribute("aria-pressed", "false");
    el.muet.textContent = "Muet";
    afficherEtat("repos", "Prêt");
  }

  el.appel.addEventListener("click", () => (ws ? raccrocher(true) : demarrer()));
  el.muet.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ op: "muet", actif: !muet }));
  });
  el.saisie.addEventListener("submit", (e) => {
    e.preventDefault();
    const texte = el.texte.value.trim();
    if (texte && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ op: "texte", texte }));
      el.texte.value = "";
    }
  });
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && ws && !verrouEcran) {
      try { verrouEcran = await navigator.wakeLock?.request("screen"); } catch { verrouEcran = null; }
    }
  });
  if (!window.isSecureContext) {
    avertir("Page non sécurisée : le micro ne sera pas disponible. Ouvre-la en HTTPS (adresse protégée par Access) ou sur localhost.");
  }
})();
