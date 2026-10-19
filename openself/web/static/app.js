// OpenSelf web UI: browse, edit and version an OpenSelf profile.
//
//   const ui = OpenSelfUI(container, host);   ui.tick(); ui.search(text);
//
// `host` connects it to a server and a page:
//   get(name, params) -> json     name: profile | state | log | show | asof
//   post(name, body)  -> json     name: save | new | remove | flag | restore   (json.status = HTTP status)
//   status(text, kind)            optional: a status line ('' | 'busy' | 'err')
//   toast(text)                   optional
//   hits(text)                    optional: search result count
//   path(files, root)             optional: the files behind what is shown
//   request(id, text)             optional: ask an assistant about an entry (adds a button)
//   changed()                     optional: called after every write
//   nav                           optional: an element in the host's header to hold the view tabs and
//                                 buttons; without it they are a bar at the top of the container
// The rendered sections carry data-entry, data-section and data-file, so a host can anchor
// comments on selected text.

/* exported OpenSelfUI */
function OpenSelfUI(root, host) {
  'use strict';
  const PF = { data: null, sel: '', view: 'overview', dirty: false, edit: null, filters: { tech: [], removed: false },
               query: '', asof: null, hist: null, conflict: null, loading: false, open: new Set(), news: null, checked: false, check: null };
  const store = (() => { try { return window.localStorage; } catch (e) { return null; } })();
  const KEY = 'openself.sel.' + (host.key || 'profile');

  // ---- helpers ------------------------------------------------------------------------------
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const ICONS = {
    plus: 'M12 5v14M5 12h14', clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0', note: 'M5 4h14v16H5zM9 9h6M9 13h6M9 17h3',
    chat: 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13', save: 'M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM7 3v6h8V3M7 21v-7h10v7',
    tag: 'M3 12V4h8l10 10-8 8z', help: 'M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
    home: 'M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6', timeline: 'M3 6h10M7 12h14M3 18h8', code: 'M8 7l-5 5 5 5M16 7l5 5-5 5',
    briefcase: 'M3 8h18v12H3zM8 8V5h8v3M3 13h18', calendar: 'M4 6h16v15H4zM4 10h16M8 3v4M16 3v4',
    award: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM8.5 14L7 22l5-3 5 3-1.5-8', pin: 'M12 21s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12zM12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5',
    building: 'M4 21V5l8-3v19M12 9h8v12M8 8h.01M8 12h.01M8 16h.01M16 13h.01M16 17h.01M2 21h20', user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6',
    layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-5M12 8h.01', open: 'M7 17L17 7M9 7h8v8',
    chart: 'M4 20V10M10 20V4M16 20v-7M2 20h20', globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18',
    git: 'M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9', filter: 'M3 5h18l-7 8v6l-4 2v-8z',
    back: 'M19 12H5M12 19l-7-7 7-7', download: 'M12 4v12M7 11l5 5 5-5M5 20h14', book: 'M4 4h6a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h7z',
  };
  // A label with an icon in front, for rows of facts.
  const withIcon = (n, text, cls) => { const s = el('span', 'os-ic' + (cls ? ' ' + cls : '')); s.append(icon(n), text); return s; };
  const KIND_ICON = { client: 'briefcase', internal: 'building', portfolio: 'layers' };
  const icon = n => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'os-i'); s.setAttribute('viewBox', '0 0 24 24');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', ICONS[n] || ''); s.append(p); return s; };
  const toast = t => host.toast ? host.toast(t) : console.log(t);
  function sanitize(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('script,style,iframe,object,embed,link,meta,form,input,button,textarea,select,svg,math').forEach(n => n.remove());
    doc.querySelectorAll('img').forEach(n => n.replaceWith(doc.createTextNode(n.alt || '')));
    doc.querySelectorAll('*').forEach(n => {
      for (const a of [...n.attributes]) { const nm = a.name.toLowerCase(), v = a.value.trim().toLowerCase();
        if (nm.startsWith('on') || nm === 'style' || (nm === 'href' && /^(javascript|data|vbscript):/.test(v))) n.removeAttribute(a.name); }
      if (n.tagName === 'A') { n.target = '_blank'; n.rel = 'noopener noreferrer'; }
    });
    return doc.body.innerHTML;
  }
  const renderMd = text => { const b = el('div', 'os-md'); b.innerHTML = sanitize(marked.parse(text, { gfm: true })); return b; };
  function highlightDom(box, needle, jump) {
    for (const m of box.querySelectorAll('mark.os-hit')) m.replaceWith(document.createTextNode(m.textContent));
    box.normalize(); let first = null;
    if (needle) {
      const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT), nodes = [];
      while (w.nextNode()) if (!w.currentNode.parentElement.closest('textarea,input')) nodes.push(w.currentNode);
      for (const tn of nodes) {
        const t = tn.nodeValue, low = t.toLowerCase(); if (!low.includes(needle)) continue;
        const frag = document.createDocumentFragment(); let at = 0, i;
        while ((i = low.indexOf(needle, at)) >= 0) { frag.append(t.slice(at, i)); const m = el('mark', 'os-hit', t.slice(i, i + needle.length)); frag.append(m); first = first || m; at = i + needle.length; }
        frag.append(t.slice(at)); tn.replaceWith(frag);
      }
    }
    if (first && jump) first.scrollIntoView({ block: 'center' });
  }

  // ---- words ----------------------------------------------------------------------------------
  const UI = {
    en: { overview: 'Overview', timeline: 'Timeline', tech: 'Technology', questions: 'Questions and gaps', addTech: '+ technology', allKinds: 'all kinds',
      showRemoved: 'show removed', assignment: 'Assignment', employment: 'Employment', history: 'History', newAssignment: 'New assignment',
      newEmployment: 'New employment', asofBanner: 'Showing the profile as it was on {d} (version {r}). Read-only.', backNow: 'Back to now',
      readonly: 'This profile is read-only (readonly in openself.json). Change the original.', editHint: 'Edit, or select text', prevVersion: 'Earlier version',
      roStatus: 'Read-only', noMatch: 'Nothing matches the filter.', withoutEmployment: 'Without employment', removed: 'Removed', choose: 'Choose an entry.',
      period: 'Period', employer: 'Employment', customer: 'Customer', nameable: 'May be named', sector: 'Sector', allocation: 'Allocation', team: 'Team', kind: 'Kind',
      location: 'Location', empType: 'Employment type', breaks: 'Breaks', title: 'Title', languages: 'Languages', clearance: 'Clearance', confidence: 'Confidence',
      reviewed: 'Last reviewed', sources: 'Sources', edit: 'Edit', ask: 'Ask about this', remove: 'Remove', unreadable: 'The file cannot be read: {e}\nEdit it as a raw file to fix it.',
      editRaw: 'Edit raw file', inEmployment: 'Assignments in this employment', noText: 'No text yet. Press Edit.', answer: 'Answer', answerHint: 'Your answer, in your own words. It is stored in quotes after the question.',
      saveAnswer: 'Save answer', cancel: 'Cancel', askMe: 'Ask me about this', answerSaved: 'Answer saved', reloaded: 'The entry changed. Reloading.', couldNot: 'Could not save',
      editing: 'Editing', save: 'Save', form: 'Form', raw: 'Raw file', verified: 'I have checked that everything in this entry is right', verifiedTip: 'Sets confidence to verified',
      discard: 'Discard the changes?', switchView: 'Switching view discards the changes. Continue?', unsaved: 'You have unsaved changes. Discard them?', none: '(none)', notSet: '(not set)',
      number: 'number', ongoingHint: 'YYYY-MM or ongoing', table: 'Table (one row per line)', intro: 'Introduction', flagHint: 'One line per flag: - ⚑ question: …, conflict, emphasis, omit, correction',
      saved: 'Saved and versioned', savedButError: 'Saved, but the file still has an error: {e}', typeEnter: 'type and press Enter', unknownName: 'Not a known name in tech-names.txt',
      conflict: 'This entry was changed elsewhere while you were editing (an assistant, or another tab).', loadTheirs: 'Load their version', keepMine: 'Keep mine',
      keepMineTip: 'Saves your changes over theirs. Their version stays in the history.', whatChanged: 'See what changed', newLead: 'Write in your own words. Save what you have now and fill in the rest later.',
      nameNotPublic: 'How to describe the customer when it may not be named', role: 'Role', from: 'From * (YYYY-MM)', to: 'To (YYYY-MM)', unknownEnd: 'empty = not known',
      ongoing: 'ongoing', allocationPct: 'Allocation (%)', teamSize: 'Team size', technology: 'Technology', toAssistant: 'To the assistant (optional): what should it ask about?',
      saveAndAsk: 'Save and ask me about it', fromFormat: 'From must be YYYY-MM', needEmployer: 'Employer and title are required', needEmployment: 'Create the employment first',
      employerReq: 'Employer *', titleReq: 'Title (exact) *', employmentReq: 'Employment *', mayBeNamed: 'May the customer be named?',
      savedAsk: 'Saved. The assistant will ask you about it.', removeWhy: 'Why remove «{t}»? (stored with the entry; it can be restored from the history)',
      movedRemoved: 'Moved to removed', couldNotRemove: 'Could not remove', askWhat: 'What should the assistant ask about or know? (Empty is fine.)', requested: 'Requested',
      entryHistory: 'History of this entry', noVersions: 'No saved versions yet.', thisChange: 'The change in this version (red removed, green added):',
      restoreHere: 'Restore the entry as it was here', restoreConfirm: 'Restore this version? It becomes a new version; nothing is deleted.', restored: 'Restored',
      showAsOf: 'Show the profile as of this date', noVersion: 'No version found', noDates: 'No dates yet.', gap: 'Ask me about this',
      tlLead: 'The top bar in each row is the employment, the assignments are below. Hatched is a break. Click to open.',
      techLead: 'How long and where each technology was used, from the assignments\' dates. Click one to filter the list.',
      unknownTech: 'Names not in the list of known names (tech-names.txt): ', techHead: ['Technology', 'Months', 'Assignments that show it'],
      qLead: 'What is missing or needs clearing up. Answer here, edit the entry, or ask the assistant. Errors (red) must be fixed, warnings (yellow) are probably mistakes, the rest are gaps.',
      nothing: 'Nothing to clear up.', careerGap: 'Gaps in the career', open: 'Open', entries: '{n} entries', updated: 'Profile updated',
      you: 'you', assistant: 'assistant', tool: 'tool', unknownPeriod: 'unknown period', roleQ: 'role?', titleQ: 'title?', customerQ: 'customer?', portfolio: 'portfolio',
      years: 'y', months: 'mo', openQuestions: '{n} open questions', confidenceUnset: 'confidence not set', untilWord: ' until ', visitAll: 'Show everything with {t}',
      new: 'New', back: 'Overview', aboutJob: 'About the job', aboutMe: 'About me', yearsWorked: 'years working', assignmentsN: 'assignments',
      certsN: 'certifications', topTech: 'Most used technology', allN: 'All {n}', openQ: 'Open questions', answerAll: 'Answer them all',
      noOpenQ: 'No open questions.', showingOnly: 'Showing only', techTip: 'Show only where it was used', certsEdu: 'Certifications and education',
      showRemovedN: 'Show removed ({n})', hideRemoved: 'Hide removed', nowWord: 'now',
      newsFrom: 'New from {src}: {parts}.', newsAdded: '{n} new', newsUpdated: '{n} filled in', newsConflicts: '{n} disagree', newsSee: 'See and import', notNow: 'Not now',
      accounts: 'Linked accounts', linked: 'linked', notLinked: 'not linked', linkIt: 'Link', checkNow: 'Check now', checking: 'Checking …',
      checkedAt: 'Checked {t}', neverChecked: 'Not checked yet', lastImported: 'Last imported {d}', neverImported: 'Never imported',
      nothingNew: 'nothing new', newThings: '{n} new or changed', readFail: 'could not read: {e}', openPage: 'Open the page',
      importBtn: 'Import', importTitle: 'Import certifications', importLead: 'Paste the link to your Credly profile or your Microsoft Learn transcript, one per line. Nothing is saved until you have seen what changes.',
      importWhere: 'Credly: your profile page (credly.com/users/…). Microsoft Learn: Profile → Transcript → Share link.', preview: 'Preview',
      found: '{n} found', nothingToChange: 'Nothing to change: the table already has all of it.', imported: 'Imported and versioned', importNow: 'Import',
      importAdd: 'New rows', importUpdate: 'Filled in or made exact', importConflict: 'Disagrees with the table (becomes a conflict to resolve)', emptyCell: '(empty)' },
    nb: { overview: 'Oversikt', timeline: 'Tidslinje', tech: 'Teknologi', questions: 'Spørsmål og hull', addTech: '+ teknologi', allKinds: 'alle typer',
      showRemoved: 'vis fjernet', assignment: 'Oppdrag', employment: 'Ansettelse', history: 'Historikk', newAssignment: 'Nytt oppdrag',
      newEmployment: 'Ny ansettelse', asofBanner: 'Viser profilen slik den var {d} (versjon {r}). Skrivebeskyttet.', backNow: 'Tilbake til nå',
      readonly: 'Denne profilen er skrivebeskyttet (readonly i openself.json). Endringer gjøres i originalen.', editHint: 'Rediger, eller marker tekst', prevVersion: 'Tidligere versjon',
      roStatus: 'Skrivebeskyttet', noMatch: 'Ingen oppføringer passer filteret.', withoutEmployment: 'Uten ansettelse', removed: 'Fjernet', choose: 'Velg en oppføring.',
      period: 'Periode', employer: 'Ansettelse', customer: 'Kunde', nameable: 'Kan navngis', sector: 'Bransje', allocation: 'Stilling', team: 'Team', kind: 'Type',
      location: 'Sted', empType: 'Ansettelsesform', breaks: 'Pauser', title: 'Tittel', languages: 'Språk', clearance: 'Klarering', confidence: 'Sikkerhet',
      reviewed: 'Sist sjekket', sources: 'Kilder', edit: 'Rediger', ask: 'Be om intervju', remove: 'Fjern', unreadable: 'Filen kan ikke leses: {e}\nRediger den som rå fil for å rette feilen.',
      editRaw: 'Rediger rå fil', inEmployment: 'Oppdrag i denne ansettelsen', noText: 'Ingen tekst ennå. Trykk Rediger.', answer: 'Svar', answerHint: 'Svaret ditt, med dine ord. Det lagres i anførselstegn etter spørsmålet.',
      saveAnswer: 'Lagre svar', cancel: 'Avbryt', askMe: 'Spør meg om dette', answerSaved: 'Svar lagret', reloaded: 'Oppføringen ble endret. Laster på nytt.', couldNot: 'Kunne ikke lagre',
      editing: 'Redigerer', save: 'Lagre', form: 'Skjema', raw: 'Rå fil', verified: 'Jeg har sjekket at alt i denne oppføringen stemmer', verifiedTip: 'Setter sikkerhet til bekreftet',
      discard: 'Forkaste endringene?', switchView: 'Bytte visning forkaster endringene. Fortsette?', unsaved: 'Du har ulagrede endringer. Forkaste dem?', none: '(ingen)', notSet: '(ikke satt)',
      number: 'tall', ongoingHint: 'YYYY-MM eller ongoing', table: 'Tabell (én rad per linje)', intro: 'Innledning', flagHint: 'Én linje per flagg: - ⚑ spørsmål: …, konflikt, vekt, utelat, retting',
      saved: 'Lagret og versjonert', savedButError: 'Lagret, men filen har fortsatt en feil: {e}', typeEnter: 'skriv og trykk Enter', unknownName: 'Ikke et kjent navn i tech-names.txt',
      conflict: 'Denne oppføringen ble endret et annet sted mens du redigerte (en assistent, eller en annen fane).', loadTheirs: 'Last inn deres versjon', keepMine: 'Behold mine',
      keepMineTip: 'Lagrer dine endringer over deres. Deres versjon finnes fortsatt i historikken.', whatChanged: 'Se hva som ble endret', newLead: 'Skriv med dine egne ord. Lagre det du har nå og fyll ut resten senere.',
      nameNotPublic: 'Omtale når kunden ikke kan navngis', role: 'Rolle', from: 'Fra * (YYYY-MM)', to: 'Til (YYYY-MM)', unknownEnd: 'tom = vet ikke',
      ongoing: 'pågår', allocationPct: 'Stillingsandel (%)', teamSize: 'Teamstørrelse', technology: 'Teknologi', toAssistant: 'Til assistenten (valgfritt): hva vil du fortelle, hva bør den spørre om?',
      saveAndAsk: 'Lagre og be om intervju', fromFormat: 'Fra må være YYYY-MM', needEmployer: 'Arbeidsgiver og tittel må med', needEmployment: 'Lag ansettelsen først',
      employerReq: 'Arbeidsgiver *', titleReq: 'Tittel (nøyaktig) *', employmentReq: 'Ansettelse *', mayBeNamed: 'Kan kunden navngis?',
      savedAsk: 'Lagret. Du blir intervjuet om det.', removeWhy: 'Hvorfor skal «{t}» fjernes? (lagres sammen med oppføringen, den kan hentes tilbake fra historikken)',
      movedRemoved: 'Flyttet til fjernet', couldNotRemove: 'Kunne ikke fjerne', askWhat: 'Hva vil du bli spurt om, eller fortelle? (Tomt er greit.)', requested: 'Bestilt',
      entryHistory: 'Historikk for denne oppføringen', noVersions: 'Ingen lagrede versjoner ennå.', thisChange: 'Endringen i denne versjonen (rødt fjernet, grønt lagt til):',
      restoreHere: 'Gjenopprett oppføringen slik den var her', restoreConfirm: 'Gjenopprette denne versjonen? Det blir en ny versjon, ingenting slettes.', restored: 'Gjenopprettet',
      showAsOf: 'Vis profilen per dato', noVersion: 'Fant ingen versjon', noDates: 'Ingen datoer ennå.', gap: 'Spør meg om dette',
      tlLead: 'Øverste stolpe i hver rad er ansettelsen, under ligger oppdragene. Skravert felt er en pause. Klikk for å åpne.',
      techLead: 'Hvor lenge og hvor du har brukt hver teknologi, regnet fra oppdragenes datoer. Klikk en teknologi for å filtrere lista.',
      unknownTech: 'Navn som ikke står i listen over kjente navn (tech-names.txt): ', techHead: ['Teknologi', 'Måneder', 'Oppdrag som viser det'],
      qLead: 'Det som mangler eller må avklares. Svar her, rediger oppføringen, eller be om intervju. Feil (rødt) må rettes, advarsler (gult) er trolig feil, resten er hull å fylle.',
      nothing: 'Ingenting å avklare.', careerGap: 'Hull i karrieren', open: 'Åpne', entries: '{n} oppføringer', updated: 'Profilen er oppdatert',
      you: 'deg', assistant: 'assistent', tool: 'verktøy', unknownPeriod: 'ukjent periode', roleQ: 'rolle?', titleQ: 'tittel?', customerQ: 'kunde?', portfolio: 'portefølje',
      years: 'år', months: 'mnd', openQuestions: '{n} åpne spørsmål', confidenceUnset: 'sikkerhet ikke satt', untilWord: ' til ', visitAll: 'Vis alt med {t}',
      new: 'Ny', back: 'Oversikt', aboutJob: 'Om jobben', aboutMe: 'Om meg', yearsWorked: 'år i arbeid', assignmentsN: 'oppdrag',
      certsN: 'sertifiseringer', topTech: 'Mest brukt teknologi', allN: 'Alle {n}', openQ: 'Åpne spørsmål', answerAll: 'Svar på alle',
      noOpenQ: 'Ingen åpne spørsmål.', showingOnly: 'Viser bare', techTip: 'Vis bare der den ble brukt', certsEdu: 'Sertifiseringer og utdanning',
      showRemovedN: 'Vis fjernet ({n})', hideRemoved: 'Skjul fjernet', nowWord: 'nå',
      newsFrom: 'Nytt fra {src}: {parts}.', newsAdded: '{n} nye', newsUpdated: '{n} fylt ut', newsConflicts: '{n} uenige', newsSee: 'Se og importer', notNow: 'Ikke nå',
      accounts: 'Koblede kontoer', linked: 'koblet', notLinked: 'ikke koblet', linkIt: 'Koble til', checkNow: 'Sjekk nå', checking: 'Sjekker …',
      checkedAt: 'Sjekket {t}', neverChecked: 'Ikke sjekket ennå', lastImported: 'Sist importert {d}', neverImported: 'Aldri importert',
      nothingNew: 'ingenting nytt', newThings: '{n} nye eller endret', readFail: 'kunne ikke leses: {e}', openPage: 'Åpne siden',
      importBtn: 'Importer', importTitle: 'Importer sertifiseringer', importLead: 'Lim inn lenken til Credly-profilen din eller Microsoft Learn-transkripsjonen, én per linje. Ingenting lagres før du har sett hva som endres.',
      importWhere: 'Credly: profilsiden din (credly.com/users/…). Microsoft Learn: Profil → Transkripsjon → Del lenke.', preview: 'Forhåndsvis',
      found: '{n} funnet', nothingToChange: 'Ingenting å endre: tabellen har alt fra før.', imported: 'Importert og versjonert', importNow: 'Importer',
      importAdd: 'Nye rader', importUpdate: 'Fylt ut eller gjort nøyaktig', importConflict: 'Uenig med tabellen (blir en konflikt du avgjør)', emptyCell: '(tom)' },
  };
  const t = (k, vars) => { const s = (UI[PF.data && UI[PF.data.lang] ? PF.data.lang : 'en'][k]) ?? UI.en[k] ?? k;
    return typeof s === 'string' && vars ? s.replace(/\{(\w+)\}/g, (_, v) => vars[v]) : s; };
  const ISSUE = { nb: [[/^not given$/, 'ikke oppgitt'], [/^may the customer be named\?$/, 'kan kunden navngis?'],
    [/^how should the customer be described when not named\?$/, 'hvordan omtales kunden når den ikke kan navngis?'], [/^no own contribution written$/, 'eget bidrag er ikke skrevet'],
    [/^needs confirmation from the owner$/, 'må bekreftes av deg'], [/^end is empty; give a month or 'ongoing'$/, 'sluttdato mangler (måned eller pågår)'],
    [/^only the year is known; ask for the month$/, 'bare året er kjent, mangler måned'], [/^not reviewed in over (\d+) months$/, 'ikke sjekket på over $1 måneder'],
    [/^no employment (\S+) to (\S+) \((\d+) months\)$/, 'ingen ansettelse $1 til $2 ($3 måneder)']] };
  const issueText = m => { for (const [re, s] of ISSUE[PF.data.lang] || []) if (re.test(m)) return m.replace(re, s); return m; };

  // ---- data helpers ---------------------------------------------------------------------------
  const L = () => PF.data.labels;
  const fieldLabel = f => L().fields[f] || f;
  const enumLabel = (f, v) => (L().enums[f] || {})[v] || v;
  const sectionLabel = (type, sid) => ((L().sections[type] || {})[sid]) || sid;
  const typeLabel = x => (L().types || {})[x] || x;
  const entries = () => PF.asof ? PF.asof.entries : PF.data.entries;
  const byId = id => entries().find(e => e.id === id);
  const val = (e, k) => { const v = e.meta[k]; return Array.isArray(v) ? v : (v == null ? '' : v); };
  const list = (e, k) => { const v = e.meta[k]; return Array.isArray(v) ? v : (v ? [v] : []); };
  const ym = s => { const m = /^(\d{4})(?:-(\d{2}))?$/.exec(s || ''); return m ? +m[1] * 12 + (m[2] ? +m[2] - 1 : 0) : null; };
  const nowYm = () => { const d = new Date(); return d.getFullYear() * 12 + d.getMonth(); };
  const endYm = e => val(e, 'end') === 'ongoing' ? nowYm() : (ym(val(e, 'end')) ?? ym(val(e, 'start')));
  const period = e => { const s = val(e, 'start'), x = val(e, 'end'); if (!s) return t('unknownPeriod');
    return x === 'ongoing' ? s + ' – ' + fieldLabel('ongoing') : (x && x !== s ? s + ' – ' + x : s); };
  const dur = e => { const a = ym(val(e, 'start')), b = endYm(e); if (a == null || b == null || b < a) return '';
    const n = b - a + 1, y = Math.floor(n / 12), m = n % 12; return (y ? y + ' ' + t('years') : '') + (y && m ? ' ' : '') + (m ? m + ' ' + t('months') : ''); };
  const customerOf = e => {
    if (val(e, 'kind') === 'internal') return enumLabel('kind', 'internal');
    if (val(e, 'kind') === 'portfolio') return list(e, 'customers').length ? list(e, 'customers').join(', ') : (val(e, 'customer_alias') || t('portfolio'));
    return val(e, 'customer') || val(e, 'customer_alias') || val(e, 'sector') || t('customerQ'); };
  const titleOf = e => e.type === 'assignment' ? (val(e, 'role') || t('roleQ')) + ' · ' + customerOf(e)
    : e.type === 'employment' ? (val(e, 'title') || t('titleQ')) + ' · ' + (val(e, 'employer') || '?') : typeLabel(e.type);
  const openFlags = e => e.flags.filter(f => f.open).length;
  const issuesOf = id => (PF.data.issues || []).filter(i => i.id === id);
  const newestFirst = (a, b) => (ym(val(b, 'start')) || 0) - (ym(val(a, 'start')) || 0) || (a.id < b.id ? 1 : -1);
  const status = (s, k) => host.status && host.status(s, k || '');
  const post = async (name, body) => { const j = await host.post(name, body); if (j.ok && host.changed) host.changed(); return j; };

  // ---- loading and live reload ----------------------------------------------------------------
  async function load() {
    PF.loading = true;
    try {
      const d = await host.get('profile');
      if (!d.ok) { root.replaceChildren(el('pre', 'os-err', d.message || 'Could not read the profile')); return; }
      PF.data = d;
      if (!PF.sel || !d.entries.some(e => e.id === PF.sel)) PF.sel = (store && store.getItem(KEY)) || 'person';
      render();
      if (!PF.checked) { PF.checked = true; checkImports(); }
    } finally { PF.loading = false; }
  }
  async function tick() {
    if (!PF.data) { if (!PF.loading) await load(); return; }
    if (PF.loading) return;
    try {
      const s = await host.get('state');
      if (!s.ok || s.version === PF.data.version) return;
      if (!PF.dirty) { await load(); toast(t('updated')); return; }
      const d = await host.get('profile'); if (!d.ok) return;
      const mine = d.entries.find(e => e.id === PF.edit.id), base = PF.data.entries.find(e => e.id === PF.edit.id);
      PF.data = Object.assign(d, { entries: d.entries.map(e => e.id === PF.edit.id && base ? base : e) });
      if (mine && base && mine.sha !== base.sha && !PF.conflict) { PF.conflict = { current_text: mine.text, current_sha: mine.sha }; drawConflict(); }
    } catch (e) { status('', 'err'); }
  }

  // ---- layout ---------------------------------------------------------------------------------
  function render() {
    const old = root.querySelector('.os-main'), keep = old && old.classList.contains('osv-' + PF.view) ? old.firstChild.scrollTop : 0;
    const box = el('div', 'os'), bar = toolbar();
    if (host.nav) host.nav.replaceChildren(bar); else box.append(bar);
    if (PF.asof) {
      const b = el('div', 'os-banner'); b.append(icon('clock'), el('span', '', t('asofBanner', { d: PF.asof.date, r: PF.asof.rev })));
      const back = el('button', 'os-btn', t('backNow')); back.onclick = () => { PF.asof = null; render(); }; b.append(back); box.append(b);
    }
    if (PF.data.readonly) box.append(el('div', 'os-banner', t('readonly')));
    const main = el('div', 'os-main osv-' + PF.view), sc = el('div', 'os-scroll');
    main.append(sc); box.append(main);
    root.replaceChildren(box);
    status(PF.asof ? t('prevVersion') : PF.data.readonly ? t('roStatus') : t('editHint'));
    if (PF.view === 'overview') overview(sc);
    else if (PF.view === 'entry') {
      const page = el('div', 'os-page'), back = el('button', 'os-btn ghost os-back'); back.append(icon('back'), t('back'));
      back.onclick = () => { if (!leaveEdit()) return; const id = PF.sel; PF.view = 'overview'; render(); reveal(id, true); };
      page.append(back, el('section', 'os-detail')); sc.append(page); drawDetail();
    } else {
      const w = el('section', 'os-wide'); sc.append(w);
      if (PF.view === 'timeline') timeline(w); else if (PF.view === 'tech') techView(w); else questions(w);
    }
    sc.scrollTop = keep;
    if (PF.conflict) drawConflict();
  }
  function toolbar() {
    const bar = el('div', 'os-bar' + (host.nav ? ' os-bar-host' : '')), seg = el('span', 'os-seg');
    const nq = PF.data.issues.filter(i => i.level !== 'warning').length;
    for (const [v, label, ic] of [['overview', t('overview'), 'home'], ['timeline', t('timeline'), 'timeline'], ['tech', t('tech'), 'code'], ['questions', t('questions'), 'help']]) {
      const b = el('button', 'os-segb' + (PF.view === v || (v === 'overview' && PF.view === 'entry') ? ' on' : '')); b.append(icon(ic), label);
      if (v === 'questions' && nq) b.append(el('span', 'os-badge', String(nq)));
      b.onclick = () => { if (!leaveEdit()) return; PF.view = v; render(); }; seg.append(b);
    }
    bar.append(seg, el('span', 'os-sp'));
    if (PF.data.history) { const h = el('button', 'os-btn ghost'); h.append(icon('clock'), t('history')); h.onclick = e => { e.stopPropagation(); profileHistory(bar); }; bar.append(h); }
    if (!PF.data.readonly && !PF.asof) {
      const nb = el('button', 'os-btn'); nb.append(icon('plus'), t('new'));
      nb.onclick = e => { e.stopPropagation(); popup(bar, 'os-menu', pop => {
        for (const [type, label] of [['assignment', t('newAssignment')], ['employment', t('newEmployment')]]) {
          const b = el('button'); b.append(icon('plus'), label); b.onclick = () => { pop.remove(); newDialog(type); }; pop.append(b); } }); };
      bar.append(nb);
    }
    return bar;
  }
  // A small panel under the bar; a second click on the same button, or a click outside, closes it.
  function popup(bar, cls, fill) {
    const was = bar.querySelector('.os-pop'); if (was) { was.remove(); if (was.classList.contains(cls)) return null; }
    const pop = el('div', 'os-pop ' + cls); pop.addEventListener('click', ev => ev.stopPropagation()); bar.append(pop); fill(pop);
    setTimeout(() => document.addEventListener('click', function off() { pop.remove(); document.removeEventListener('click', off); }), 0);
    return pop;
  }

  // ---- overview: the career as a stream, newest first -----------------------------------------
  function matches(e) {
    if (e.removed && !PF.filters.removed) return false;
    if (PF.filters.tech.length && !PF.filters.tech.every(x => list(e, 'tech').includes(x))) return false;
    if (PF.query && !(JSON.stringify(e.meta) + ' ' + e.sections.map(s => s.text).join(' ')).toLowerCase().includes(PF.query)) return false;
    return true;
  }
  function overview(box) {
    const all = entries(), live = all.filter(e => !e.removed), shown = new Set(all.filter(matches).map(e => e.id));
    const filtering = !!(PF.query || PF.filters.tech.length), show = e => !filtering || shown.has(e.id);
    const jobs = live.filter(e => e.type === 'employment').sort(newestFirst), jobIds = new Set(jobs.map(j => j.id));
    const kidsOf = j => live.filter(e => e.type === 'assignment' && val(e, 'employment') === j.id).sort(newestFirst);
    const wrap = el('div', 'os-ov'), col = el('div'), side = el('aside', 'os-ov-side');
    wrap.append(col, side); box.append(wrap);
    const p = byId('person');
    if (p) {
      const hero = el('div', 'os-hero'), name = val(p, 'name') || typeLabel('person'), words = name.split(/\s+/).filter(Boolean);
      const av = el('div', 'os-av', words.length > 1 ? words[0][0] + words[words.length - 1][0] : name.slice(0, 2)), info = el('div'), h1 = el('h1'), nb = el('button', '', name);
      nb.onclick = () => select(p.id); h1.append(nb); info.append(h1);
      const line = el('div', 'os-mut os-icrow');
      if (val(p, 'title')) line.append(withIcon('briefcase', val(p, 'title')));
      if (val(p, 'location')) line.append(withIcon('pin', val(p, 'location')));
      for (const u of [val(p, 'github'), val(p, 'linkedin'), ...list(p, 'links')].filter(Boolean)) {
        const a = el('a', 'os-ic'); a.append(icon(/github\.com|gitlab\.com/.test(u) ? 'git' : 'globe'), u.replace(/^https?:\/\/(www\.)?/, '')); a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer'; line.append(a); }
      info.append(line);
      const about = el('button', 'os-btn'); about.append(icon('user'), t('aboutMe')); about.onclick = () => select(p.id);
      if (openFlags(p)) about.append(el('span', 'os-badge', String(openFlags(p))));
      hero.append(av, info, about); col.append(hero);
    }
    if (PF.news) col.append(newsBanner(PF.news));
    if (PF.filters.tech.length) {
      const f = el('div', 'os-filter'); f.append(icon('filter'), t('showingOnly'));
      for (const x of PF.filters.tech) { const c = el('button', 'os-chip on', x + ' ×'); c.onclick = () => { PF.filters.tech = PF.filters.tech.filter(y => y !== x); render(); }; f.append(c); }
      col.append(f);
    }
    col.append(miniTimeline(jobs, kidsOf, e => !filtering || shown.has(e.id) || kidsOf(e).some(k => shown.has(k.id))));
    const stream = el('div', 'os-stream');
    for (const j of jobs) {
      const kids = kidsOf(j).filter(show);
      if (filtering && !shown.has(j.id) && !kids.length) continue;
      stream.append(node(j, (val(j, 'start') || '?').slice(0, 4), dur(j), val(j, 'end') === 'ongoing' ? 'now' : '', [['building', val(j, 'employer')], ['calendar', period(j)], ['pin', val(j, 'location')]],
        [fold(j, t('aboutJob'), '', '', shown.has(j.id), '', 'info'), ...kids.map(k => fold(k, customerOf(k), val(k, 'role'), period(k), true, '', KIND_ICON[val(k, 'kind')] || 'briefcase'))]));
    }
    const orphans = live.filter(e => e.type === 'assignment' && !jobIds.has(val(e, 'employment'))).filter(show).sort(newestFirst);
    if (orphans.length) stream.append(node(null, '', '', 'plain', [['', t('withoutEmployment')]], orphans.map(k => fold(k, customerOf(k), val(k, 'role'), period(k), true, '', KIND_ICON[val(k, 'kind')] || 'briefcase'))));
    const other = ['certifications', 'education'].map(byId).filter(e => e && !e.removed && show(e));
    if (other.length) stream.append(node(null, '', '', 'plain', [['', t('certsEdu')]], other.map(e => fold(e, typeLabel(e.type), '', '', true, '', e.type === 'education' ? 'book' : 'award'))));
    const removed = all.filter(e => e.removed);
    if (PF.filters.removed && removed.length) stream.append(node(null, '', '', 'plain', [['', t('removed')]], removed.filter(show).map(e => fold(e, e.type === 'employment' ? val(e, 'employer') : customerOf(e), '', val(e, 'removed'), true, 'removed', 'trash'))));
    if (!stream.children.length) stream.append(el('div', 'os-empty', t('noMatch')));
    col.append(stream);
    if (removed.length) { const r = el('button', 'os-link os-ic'); r.append(icon('trash'), PF.filters.removed ? t('hideRemoved') : t('showRemovedN', { n: removed.length })); r.onclick = () => { PF.filters.removed = !PF.filters.removed; render(); }; col.append(r); }
    sideColumn(side, live, jobs);
    if (PF.query) highlightDom(col, PF.query, false);
  }
  // One point on the stream: a year on the left, a card on the right. A card with a job opens it on the title.
  function node(job, year, sub, cls, meta, folds) {
    const n = el('div', 'os-node ' + cls), y = el('div', 'os-yr', year), card = el('div', 'os-card'), top = el('div', 'os-card-top');
    if (sub) y.append(el('small', '', sub));
    if (job) {
      n.dataset.id = job.id; const h = el('button', 'os-card-title', val(job, 'title') || t('titleQ')); h.onclick = () => select(job.id); top.append(h);
      const acts = el('div', 'os-acts'); entryButtons(job, acts, false); top.append(acts);
      const m = el('div', 'os-card-meta os-icrow'); for (const [ic, x] of meta) if (x) m.append(withIcon(ic, x)); card.append(top, m);
    } else { top.append(el('span', 'os-card-title', meta[0][1])); card.append(top); }
    for (const f of folds) card.append(f);
    n.append(y, card); return n;
  }
  // An entry that opens in place. The text is built the first time it opens.
  function fold(e, title, sub, right, hit, cls, ic) {
    const d = el('details', 'os-fold' + (cls ? ' ' + cls : '')), s = el('summary'), tt = el('span', 'os-fold-t'), r = el('span', 'os-fold-r');
    d.dataset.id = e.id; if (ic) tt.append(icon(ic)); tt.append(el('b', '', title)); if (sub) tt.append(' ', el('span', 'os-mut', sub));
    const n = openFlags(e); if (n) { const b = el('span', 'os-badge', String(n)); b.title = t('openQuestions', { n }); r.append(b); }
    if (e.error) r.append(el('span', 'os-badge bad', '!'));
    if (right) r.append(right);
    s.append(tt, r); d.append(s);
    let filled = false;
    const fill = () => { if (filled) return; filled = true; const b = el('div', 'os-fold-in'); entryBody(e, b); if (PF.query) highlightDom(b, PF.query, false); d.append(b); };
    d.open = PF.open.has(e.id) || (!!PF.query && hit && matches(e));
    if (d.open) fill();
    d.addEventListener('toggle', () => { if (d.open) { PF.open.add(e.id); fill(); } else PF.open.delete(e.id); });
    return d;
  }
  function entryBody(e, box) {
    const tech = list(e, 'tech');
    if (tech.length) { const tl = el('div', 'os-tags'); for (const x of tech) { const b = el('button', 'os-chip', x); b.title = t('visitAll', { t: x }); b.onclick = () => { PF.filters.tech = [x]; render(); }; tl.append(b); } box.append(tl); }
    if (e.error) box.append(el('pre', 'os-err', t('unreadable', { e: e.error })));
    for (const s of sectionEls(e)) box.append(s);
    const acts = el('div', 'os-acts'), open = el('button', 'os-btn'); open.append(icon('open'), t('open')); open.onclick = () => select(e.id); acts.append(open);
    entryButtons(e, acts, true); box.append(acts);
  }
  // Edit, history and ask, for an entry shown in the overview. They open it on its own page.
  function entryButtons(e, acts, all) {
    const ro = PF.data.readonly || PF.asof || e.removed;
    const btn = (ic, label, fn) => { const b = el('button', 'os-btn'); b.append(icon(ic), label); b.onclick = ev => { ev.stopPropagation(); fn(); }; acts.append(b); };
    if (!ro) btn('note', t('edit'), () => { if (!select(e.id)) return; PF.edit = { id: e.id }; PF.dirty = false; drawDetail(); });
    if (all && PF.data.history && !PF.asof) btn('clock', t('history'), () => { if (select(e.id)) entryHistory(byId(e.id)); });
    if (all && !ro && host.request) btn('chat', t('ask'), () => request(e.id));
    if (all && !ro && e.type === 'certifications') btn('download', t('importBtn'), () => importDialog(e));
  }
  // Shared by both timelines: year bands, career gaps, the now marker and a hover card.
  function timeFrame(items, extra) {
    const more = extra || [], y0 = Math.floor(Math.min(...items.map(e => ym(val(e, 'start'))), ...more) / 12);
    const y1 = Math.floor(Math.max(nowYm(), ...items.map(endYm), ...more) / 12), span = (y1 - y0 + 1) * 12;
    return { y0, y1, span, at: mo => (mo - y0 * 12) / span * 100, w: (a, b) => (b - a + 1) / span * 100 };
  }
  function backdrop(f) {
    const bg = el('div', 'os-tlbg');
    for (let y = f.y0; y <= f.y1; y++) if ((y - f.y0) % 2) { const b = el('i', 'os-tlband'); b.style.left = f.at(y * 12) + '%'; b.style.width = f.w(y * 12, y * 12 + 11) + '%'; bg.append(b); }
    for (const g of PF.data.issues.filter(i => i.id === 'employments')) {
      const m = /(\d{4}-\d{2}) to (\d{4}-\d{2}) \((\d+)/.exec(g.message); if (!m) continue;
      const gp = el('i', 'os-tlgap'); gp.style.left = f.at(ym(m[1])) + '%'; gp.style.width = f.w(ym(m[1]), ym(m[2])) + '%'; gp.title = issueText(g.message);
      gp.append(el('span', '', m[3] + ' ' + t('months'))); bg.append(gp);
    }
    const now = el('i', 'os-tlnow'); now.style.left = f.at(nowYm() + 1) + '%'; now.append(el('span', '', t('nowWord'))); bg.append(now);
    return bg;
  }
  function hoverCard(box) {
    const tip = el('div', 'os-tltip'); box.append(tip);
    return (bar, e, info) => {
      bar.removeAttribute('title');
      bar.addEventListener('mouseenter', () => {
        if (info) tip.replaceChildren(el('b', '', info[0]), el('div', '', info[1]), el('small', '', info[2]));
        else tip.replaceChildren(el('b', '', e.type === 'assignment' ? customerOf(e) : val(e, 'employer')),
          el('div', '', e.type === 'assignment' ? val(e, 'role') : val(e, 'title')), el('small', '', period(e) + (dur(e) ? ' · ' + dur(e) : '')));
        if (!info && openFlags(e)) tip.append(el('span', 'os-badge', t('openQuestions', { n: openFlags(e) })));
        tip.classList.add('on'); });
      bar.addEventListener('mousemove', ev => { const r = box.getBoundingClientRect(), x = ev.clientX - r.left;
        tip.style.left = Math.min(x + 14, r.width - tip.offsetWidth - 4) + 'px'; const y = ev.clientY - r.top;
        tip.style.top = (y + 16 + tip.offsetHeight > r.height ? y - tip.offsetHeight - 10 : y + 16) + 'px'; });
      bar.addEventListener('mouseleave', () => tip.classList.remove('on'));
    };
  }
  // Certificates from the certifications table: name, issuer, the month taken and the month it expires.
  // Rows of the table at the top of certifications.md or education.md, header left out.
  function tableRows(id) {
    const c = byId(id); if (!c || c.removed) return [];
    return ((c.sections.find(x => x.id === '_intro') || {}).text || '').split('\n').filter(l => /^\s*\|/.test(l)).slice(1)
      .map(l => l.trim().replace(/^\||\|$/g, '').split('|').map(x => x.trim())).filter(r => !r.every(x => /^:?-*:?$/.test(x)));
  }
  const tmo = s => ym(String(s || '').slice(0, 7));
  // A lane's name goes left, or right when something starts at the left edge, or nowhere if both are taken.
  function laneLabel(lane, ic, text, f, from, to) {
    const lab = withIcon(ic, text, 'os-cert-lab');
    if (Math.min(...from.map(f.at)) < 14) { if (Math.max(...to.map(m => f.at(m + 1))) > 84) return; lab.classList.add('right'); }
    lane.append(lab);
  }
  function certRows() {
    return tableRows('certifications').map(r => ({ name: r[0], issuer: r[1] || '', date: r[2] || '', expires: r[3] || '', at: tmo(r[2]), to: tmo(r[3]) }))
      .filter(r => r.name && r.at != null);
  }
  // Education: degree, school, from, to. A year alone counts from January to December.
  function eduRows() {
    return tableRows('education').map(r => ({ name: r[0], school: r[1] || '', from: r[2] || '', to: r[3] || '', at: tmo(r[2]),
      end: /^\d{4}$/.test(r[3] || '') ? tmo(r[3]) + 11 : tmo(r[3]) })).filter(r => r.name && r.at != null);
  }
  // One lane of bars, one per education row; an unknown end fades out with a question mark.
  function eduLane(f, rows, card, cls) {
    const lane = el('div', cls), lanes = [];
    laneLabel(lane, 'book', typeLabel('education'), f, rows.map(r => r.at), rows.map(r => r.end ?? r.at + 5));
    for (const r of [...rows].sort((a, b) => a.at - b.at)) {
      const open = r.end == null, b = open ? r.at + 5 : r.end;
      let i = lanes.findIndex(e => e < r.at); if (i < 0) { i = lanes.length; lanes.push(0); } lanes[i] = b;
      const d = el('button', 'os-edu' + (open ? ' open' : '')); d.style.left = f.at(r.at) + '%'; d.style.width = f.w(r.at, b) + '%'; d.style.top = (3 + i * 16) + 'px';
      if (f.w(r.at, b) > r.name.length * 0.9 + 4) d.append(el('span', '', r.name));
      card(d, null, [r.name, r.school, r.from + ' – ' + (r.to || '?')]);
      d.onclick = () => (PF.view === 'overview' ? reveal('education', false) : select('education')); lane.append(d);
    }
    lane.style.height = (lanes.length * 16 + 8) + 'px';
    return lane;
  }
  // One lane of diamonds, one per certificate; an expired one is hollow.
  function certLane(f, certs, card, cls) {
    const lane = el('div', cls), rows = [], step = f.w(0, 0) * 3;
    laneLabel(lane, 'award', t('certsN').replace(/^./, x => x.toUpperCase()), f, certs.map(c => c.at), certs.map(c => c.at + 1));
    for (const c of [...certs].sort((a, b) => a.at - b.at)) {
      const x = f.at(c.at); let r = rows.findIndex(end => end < x - step); if (r < 0) { r = rows.length; rows.push(0); } rows[r] = x;
      const d = el('button', 'os-cert' + (c.to != null && c.to < nowYm() ? ' expired' : '')); d.style.left = x + '%'; d.style.top = (3 + r * 12) + 'px';
      card(d, null, [c.name, c.issuer, [c.date, c.expires && '→ ' + c.expires].filter(Boolean).join(' ')]);
      d.onclick = () => (PF.view === 'overview' ? reveal('certifications', false) : select('certifications')); lane.append(d);
    }
    lane.style.height = (rows.length * 12 + 10) + 'px';
    return lane;
  }
  function miniTimeline(jobs, kidsOf, lit) {
    const box = el('div', 'os-mtl' + (PF.grown ? '' : ' grow')), dated = jobs.filter(j => ym(val(j, 'start')) != null);
    if (!dated.length) return el('div');
    PF.grown = true;
    const certs = certRows(), edu = eduRows();
    const f = timeFrame(dated.flatMap(j => [j, ...kidsOf(j)]).filter(e => ym(val(e, 'start')) != null), [...certs.map(c => c.at), ...edu.flatMap(r => [r.at, r.end ?? r.at])]), card = hoverCard(box);
    const legend = el('div', 'os-mtl-legend');
    for (const [cls, label] of [['job', t('employment')], ['k-client', enumLabel('kind', 'client')], ['k-internal', enumLabel('kind', 'internal')], ['k-portfolio', enumLabel('kind', 'portfolio')]]) {
      const s = el('span'); s.append(el('i', cls), label); legend.append(s); }
    if (edu.length) { const s = el('span'); s.append(el('i', 'os-edu-key'), typeLabel('education').toLowerCase()); legend.append(s); }
    if (certs.length) { const s = el('span'); s.append(el('i', 'os-cert-key'), t('certsN')); legend.append(s); }
    const axis = el('div', 'os-mtl-axis'); for (let y = f.y0; y <= f.y1; y++) { const s = el('span', '', String(y)); s.style.left = f.at(y * 12) + '%'; s.style.width = f.w(0, 11) + '%'; axis.append(s); }
    const lanes = el('div', 'os-mtl-lanes'); lanes.append(backdrop(f));
    const bar = (e, cls, top, n) => { const a = ym(val(e, 'start')), b = endYm(e), d = el('button', 'os-mtl-bar ' + cls + (val(e, 'end') === 'ongoing' ? ' ongoing' : ''));
      d.style.left = f.at(a) + '%'; d.style.width = f.w(a, b) + '%'; if (top != null) d.style.top = top + 'px'; d.style.animationDelay = n * 40 + 'ms';
      card(d, e); d.onclick = () => reveal(e.id, false); return d; };
    let n = 0;
    for (const j of dated) {
      const lane = el('div', 'os-mtl-lane'), jb = bar(j, 'job' + (lit(j) ? '' : ' dim'), null, n++), name = val(j, 'employer'), a = ym(val(j, 'start')), b = endYm(j);
      // The name goes inside the bar when it fits, otherwise beside it, on the side with room.
      if (f.w(a, b) > name.length * 1.1 + 4) jb.append(el('span', '', name));
      else { const lab = el('span', 'os-mtl-lab', name); if (f.at(b + 1) > 70) lab.style.right = 'calc(' + (100 - f.at(a)) + '% + 6px)'; else lab.style.left = 'calc(' + f.at(b + 1) + '% + 6px)'; lane.append(lab); }
      lane.append(jb);
      const rows = [];
      for (const k of kidsOf(j).filter(k => ym(val(k, 'start')) != null).sort((p, q) => ym(val(p, 'start')) - ym(val(q, 'start')))) {
        let r = rows.findIndex(end => end < ym(val(k, 'start'))); if (r < 0) { r = rows.length; rows.push(0); } rows[r] = endYm(k);
        lane.append(bar(k, 'kid k-' + (val(k, 'kind') || 'client') + (lit(k) ? '' : ' dim'), 24 + r * 8, n++));
      }
      lane.style.height = (rows.length ? 28 + rows.length * 8 : 26) + 'px'; lanes.append(lane);
    }
    if (edu.length) lanes.append(eduLane(f, edu, card, 'os-mtl-lane os-cert-lane'));
    if (certs.length) lanes.append(certLane(f, certs, card, 'os-mtl-lane os-cert-lane'));
    box.append(legend, axis, lanes); return box;
  }
  function sideColumn(side, live, jobs) {
    const months = new Set(); for (const j of jobs) { const a = ym(val(j, 'start')), b = endYm(j); if (a != null && b != null) for (let m = a; m <= b; m++) months.add(m); }
    const certs = byId('certifications'), rows = certs ? ((certs.sections.find(s => s.id === '_intro') || {}).text || '').split('\n').filter(l => /^\s*\|/.test(l)).length - 2 : 0;
    const stats = el('div', 'os-stats');
    for (const [n, label, ic] of [[(months.size / 12).toFixed(1), t('yearsWorked'), 'calendar'], [live.filter(e => e.type === 'assignment').length, t('assignmentsN'), 'briefcase'], [Math.max(rows, 0), t('certsN'), 'award']]) {
      const d = el('div'); d.append(icon(ic), el('b', '', String(n)), el('span', '', label)); stats.append(d); }
    const sb = el('div', 'os-box'); sb.append(stats); side.append(sb);
    accountsBox(side);
    const top = [...PF.data.tech].sort((a, b) => b.months - a.months).slice(0, 12);
    if (top.length) {
      const tb = el('div', 'os-box'), h = el('h3'), all = el('button', 'os-link', t('allN', { n: PF.data.tech.length }));
      h.append(icon('chart'), t('topTech')); all.onclick = () => { PF.view = 'tech'; render(); }; h.append(all); tb.append(h);
      for (const x of top) {
        const r = el('button', 'os-tb' + (PF.filters.tech.includes(x.name) ? ' on' : '')), bar = el('i', x.ongoing ? 'ongoing' : '');
        bar.style.width = x.months / top[0].months * 100 + '%'; r.title = t('techTip');
        r.append(el('span', '', x.name), el('span', '', ''), el('span', '', (x.months / 12).toFixed(1) + ' ' + t('years'))); r.children[1].append(bar);
        r.onclick = () => { PF.filters.tech = PF.filters.tech.includes(x.name) ? [] : [x.name]; render(); }; tb.append(r);
      }
      side.append(tb);
    }
    const qs = live.flatMap(e => e.flags.filter(f => f.open).map(f => [e, f]));
    const qb = el('div', 'os-box'), h = el('h3'); h.append(icon('help'), t('openQ'));
    if (qs.length) h.append(el('span', 'os-badge', String(qs.length)));
    const go = el('button', 'os-link', t('answerAll')); go.onclick = () => { PF.view = 'questions'; render(); }; h.append(go); qb.append(h);
    for (const [e, f] of qs.slice(0, 6)) {
      const b = el('button', 'os-qi'), tx = el('span'); tx.innerHTML = sanitize(marked.parseInline(f.text));
      b.append(el('small', '', e.type === 'assignment' ? customerOf(e) : e.type === 'employment' ? val(e, 'employer') : typeLabel(e.type)), tx);
      b.onclick = () => reveal(e.id, false); qb.append(b);
    }
    if (!qs.length) qb.append(el('div', 'os-mut', t('noOpenQ')));
    side.append(qb);
  }
  // Scroll the overview to an entry and open it; what is not on the stream opens on its own page.
  function reveal(id, quiet) {
    const e = byId(id); if (!e) return;
    const q = x => root.querySelector(x + '[data-id="' + CSS.escape(x === '.os-node' && e.type === 'assignment' ? val(e, 'employment') : id) + '"]');
    const d = e.type === 'employment' ? null : q('.os-fold'), n = d ? d.closest('.os-node') : q('.os-node');
    if (!d && !n) { if (!quiet) select(id); return; }
    if (d) d.open = true;
    (d || n).scrollIntoView({ behavior: quiet ? 'auto' : 'smooth', block: d ? 'center' : 'start' });
    const c = n.querySelector('.os-card'); c.classList.add('flash'); setTimeout(() => c.classList.remove('flash'), 1200);
  }
  function select(id) {
    if (!leaveEdit()) return false;
    PF.sel = id; PF.hist = null; PF.view = 'entry'; if (store) store.setItem(KEY, id);
    render(); return true;
  }
  function leaveEdit() {
    if (!PF.dirty) { PF.edit = null; return true; }
    if (!confirm(t('unsaved'))) return false;
    PF.dirty = false; PF.edit = null; PF.conflict = null; return true;
  }
  window.addEventListener('beforeunload', e => { if (PF.dirty) { e.preventDefault(); e.returnValue = ''; } });

  // ---- detail ---------------------------------------------------------------------------------
  // Icons for the facts on an entry's page, by their label.
  const FACT_ICON = new Proxy({}, { get: (_, k) => ({ period: 'calendar', employer: 'building', customer: 'briefcase', nameable: 'user', sector: 'layers', allocation: 'chart',
    team: 'user', kind: 'tag', location: 'pin', empType: 'briefcase', breaks: 'clock', title: 'briefcase', languages: 'globe', clearance: 'info', confidence: 'info',
    reviewed: 'calendar', sources: 'book', LinkedIn: 'globe', GitHub: 'git' })[Object.keys(UI.en).find(x => t(x) === k) || k] });
  function drawDetail() {
    const box = root.querySelector('.os-detail'); if (!box) return;
    const e = byId(PF.sel); box.replaceChildren();
    if (host.path) host.path(['INDEX.md'].concat(e ? [e.rel] : []), PF.data.path);
    if (!e) { box.append(el('div', 'os-empty', t('choose'))); return; }
    if (PF.edit && PF.edit.id === e.id) { editor(box, e); return; }
    const head = el('div', 'os-head');
    head.append(el('div', 'os-type', typeLabel(e.type) + (e.removed ? ' · ' + t('removed').toLowerCase() + ' ' + val(e, 'removed') : '') + ' · ' + e.id),
      el('h2', '', e.type === 'person' ? (val(e, 'name') || typeLabel('person')) : titleOf(e)));
    const facts = el('div', 'os-facts'), fact = (k, v) => { if (v === '' || v == null) return; const s = el('span', 'os-fact'); s.append(withIcon(FACT_ICON[k] || 'info', k, 'os-fl'), el('span', '', v)); facts.append(s); };
    if (e.type === 'assignment') {
      fact(t('period'), period(e) + (dur(e) ? ' (' + dur(e) + ')' : ''));
      const emp = byId(val(e, 'employment'));
      if (emp) { const s = el('span', 'os-fact'); const a = el('a', '', val(emp, 'employer') + ', ' + val(emp, 'title')); a.href = '#'; a.onclick = ev => { ev.preventDefault(); select(emp.id); }; s.append(withIcon('building', t('employer'), 'os-fl'), a); facts.append(s); }
      fact(t('customer'), val(e, 'kind') === 'portfolio' ? list(e, 'customers').join(', ') : val(e, 'customer'));
      fact(t('nameable'), enumLabel('customer_public', val(e, 'customer_public')) + (val(e, 'customer_public') !== 'public' && val(e, 'customer_alias') ? ': «' + val(e, 'customer_alias') + '»' : ''));
      fact(t('sector'), val(e, 'sector')); fact(t('allocation'), val(e, 'allocation') ? val(e, 'allocation') + ' %' : ''); fact(t('team'), val(e, 'team_size'));
      fact(t('kind'), enumLabel('kind', val(e, 'kind')));
    } else if (e.type === 'employment') {
      fact(t('period'), period(e) + (dur(e) ? ' (' + dur(e) + ')' : '')); fact(t('location'), val(e, 'location'));
      fact(t('empType'), enumLabel('employment_type', val(e, 'employment_type'))); if (list(e, 'breaks').length) fact(t('breaks'), list(e, 'breaks').join(', '));
    } else if (e.type === 'person') {
      fact(t('title'), val(e, 'title')); fact(t('location'), val(e, 'location')); fact(t('languages'), list(e, 'languages').join(', '));
      fact(t('clearance'), val(e, 'clearance') + (val(e, 'clearance_valid_until') ? t('untilWord') + val(e, 'clearance_valid_until') : ''));
      fact('LinkedIn', val(e, 'linkedin')); fact('GitHub', val(e, 'github'));
    }
    fact(t('confidence'), enumLabel('confidence', val(e, 'confidence'))); fact(t('reviewed'), val(e, 'last_reviewed')); fact(t('sources'), list(e, 'sources').join(', '));
    head.append(facts);
    const tech = list(e, 'tech');
    if (tech.length) { const tl = el('div', 'os-tags'); for (const x of tech) { const b = el('button', 'os-chip', x); b.title = t('visitAll', { t: x }); b.onclick = () => { PF.filters.tech = [x]; PF.view = 'overview'; render(); }; tl.append(b); } head.append(tl); }
    const acts = el('div', 'os-acts'), ro = PF.data.readonly || PF.asof || e.removed;
    const btn = (ic, label, fn) => { const b = el('button', 'os-btn'); b.append(icon(ic), label); b.onclick = fn; acts.append(b); };
    if (!ro) btn('note', t('edit'), () => { PF.edit = { id: e.id }; PF.dirty = false; drawDetail(); });
    if (PF.data.history && !PF.asof) btn('clock', t('history'), () => entryHistory(e));
    if (!ro && host.request) btn('chat', t('ask'), () => request(e.id));
    if (!ro && (e.type === 'assignment' || e.type === 'employment')) btn('trash', t('remove'), () => removeEntry(e));
    if (!ro && e.type === 'certifications') btn('download', t('importBtn'), () => importDialog(e));
    head.append(acts); box.append(head);
    if (e.error) { box.append(el('pre', 'os-err', t('unreadable', { e: e.error })));
      if (!ro) { const b = el('button', 'os-btn', t('editRaw')); b.onclick = () => { PF.edit = { id: e.id, raw: true }; drawDetail(); }; box.append(b); } }
    const iss = issuesOf(e.id).filter(i => !/^(question|conflict):/.test(i.message));
    if (iss.length) { const ul = el('ul', 'os-issues'); for (const i of iss) ul.append(el('li', 'lv-' + i.level, (i.field ? fieldLabel(i.field) + ': ' : '') + issueText(i.message))); box.append(ul); }
    if (PF.hist && PF.hist.id === e.id) box.append(PF.hist.el);
    for (const s of sectionEls(e)) box.append(s);
    if (e.type === 'employment') {
      const kids = entries().filter(x => x.type === 'assignment' && !x.removed && val(x, 'employment') === e.id).sort(newestFirst);
      if (kids.length) { const sec = el('div', 'os-sec'); sec.append(el('h3', '', t('inEmployment')));
        for (const k of kids) { const a = el('button', 'os-link', customerOf(k) + ' · ' + (val(k, 'role') || '') + ' · ' + period(k)); a.onclick = () => select(k.id); sec.append(a); }
        box.append(sec); }
    }
    if (!e.sections.some(s => s.text.trim()) && !e.error) box.append(el('div', 'os-empty', t('noText')));
    highlightDom(box, PF.query, false);
  }
  function sectionEls(e) {
    const sch = PF.data.schema[e.type] || { sections: [] };
    const rank = s => s.id === '_intro' ? -1 : (sch.sections.indexOf(s.id) < 0 ? 99 : sch.sections.indexOf(s.id));
    return [...e.sections].sort((a, b) => rank(a) - rank(b)).filter(s => s.text.trim()).map(s => {
      const sec = el('div', 'os-sec'); sec.dataset.entry = e.id; sec.dataset.section = s.id; sec.dataset.file = e.file;
      if (s.id !== '_intro') sec.append(el('h3', '', s.known ? sectionLabel(e.type, s.id) : s.heading));
      sec.append(s.id === 'flags' ? flagsView(e, s.text) : renderMd(s.text));
      if (s.id === '_intro' && sch.table) { sourceChips(sec, e, sch.table.indexOf('source')); issuerBadges(sec, sch.table.indexOf('issuer')); }
      return sec;
    });
  }
  // The source cell of a table row as chips: 'raw.md 2026-10, Credly 2026-10-19' becomes two, each with
  // its date muted; Credly and Microsoft Learn link to the linked page.
  function sourceChips(sec, e, col) {
    if (col < 0) return;
    const links = list(byId('certifications') || { meta: {} }, 'imports');
    for (const td of sec.querySelectorAll('tbody tr td:nth-child(' + (col + 1) + ')')) {
      const parts = td.textContent.split(/,\s*(?![^()]*\))/).map(x => x.trim()).filter(Boolean); if (!parts.length) continue;
      const box = el('span', 'os-srcs');
      for (const p of parts) {
        const m = /^(.*?)\s+(\d{4}(?:-\d{2}){0,2})$/.exec(p), name = m ? m[1] : p, date = m ? m[2] : '';
        const kind = /credly/i.test(name) ? 'credly' : /microsoft learn/i.test(name) ? 'mslearn' : /egne notater|own notes|self-edit/i.test(name) ? 'own'
          : /\.(md|pdf|docx?)\b|^intake:/i.test(name) ? 'doc'
          : /chat|intervju|interview|samtale/i.test(name) ? 'talk' : 'other';
        const url = kind === 'credly' ? links.find(u => /credly\.com/.test(u)) : kind === 'mslearn' ? links.find(u => /learn\.microsoft\.com/.test(u)) : '';
        const chip = el(url ? 'a' : 'span', 'os-src k-' + kind); if (url) { chip.href = url; chip.target = '_blank'; chip.rel = 'noopener noreferrer'; }
        chip.append(kind === 'credly' || kind === 'mslearn' ? logoMark(kind === 'credly' ? 'Credly' : 'Microsoft Learn')
          : icon({ own: 'user', doc: 'note', talk: 'chat', other: 'tag' }[kind]), el('span', '', name));
        if (date) chip.append(el('small', '', date));
        chip.title = p; box.append(chip);
      }
      td.replaceChildren(box);
    }
  }
  // Issuer logos. Bundled marks are from Simple Icons (https://simpleicons.org, CC0), drawn white on
  // the brand colour. Brands whose marks are not freely licensed (Microsoft, AWS, Oracle, Forsvaret)
  // show the icon from their own website instead, loaded when the page shows it; if that fails, initials.
  const LOGOS = {
    anthropic: ['#191919', 'M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z'],
    github: ['#181717', 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12'],
    linuxfoundation: ['#003778', 'M4.8 19.2h9.6V24H0V9.6h4.8v9.6zM0 0v7.2h4.8V4.822h14.4V19.2h-2.4V24H24V0H0z'],
    credly: ['#FF6B00', 'M23.8 13.154a.299.299 0 0 0-.101-.024.407.407 0 0 0-.202.048c-.06.028-.092.08-.127.136-.087.128-.15.268-.226.4-.107.187-.246.351-.38.515-.135.156-.286.291-.424.44-.028.027-.072.043-.107.027-.028-.016-.036-.056-.032-.088.04-.38.075-.763.123-1.138.02-.172.043-.336.063-.512.028-.247.056-.487.087-.735l.234-1.824c.02-.128.032-.372-.135-.52a.446.446 0 0 0-.233-.116.46.46 0 0 0-.254.06c-.226.16-.297.504-.365.76-.142.603-.178 1.241-.471 1.804a1.772 1.772 0 0 1-.202.316.668.668 0 0 1-.186.18.332.332 0 0 1-.246.051.365.365 0 0 1-.238-.207.871.87 0 0 1-.063-.324 4.499 4.499 0 0 1 .24-1.585c.045-.132.089-.252.104-.383.028-.156.028-.38-.114-.516-.131-.128-.337-.18-.504-.128-.194.056-.31.244-.372.392-.198.463-.25.95-.317 1.446-.044.327-.127.64-.293.926a2.717 2.717 0 0 1-.603.72c-.118.087-.222.123-.328.107a.376.376 0 0 1-.278-.208.875.875 0 0 1-.095-.315 3.361 3.36 0 0 1-.036-.616c.004-.223 0-.44.044-.658.075-.39.678-1.937.808-2.345.135-.407.262-.823.353-1.246.08-.38.123-.767.11-1.15-.007-.277-.07-.576-.288-.736a.611.61 0 0 0-.603-.048.968.968 0 0 0-.455.428 2.53 2.53 0 0 0-.226.59 12.01 12.01 0 0 0-.266 1.29c-.071.429-.138.848-.206 1.268-.06.355-.206 1.614-.261 1.88-.06.272-.175.54-.301.787-.131.268-.258.536-.408.791a.694.694 0 0 1-.175.224c-.08.06-.182.088-.27.048-.102-.048-.146-.176-.166-.292-.075-.435-.012-.875.072-1.302.083-.431.44-2.4.519-2.851.099-.532.24-1.05.285-1.59.028-.388.09-.88-.202-1.187-.115-.136-.31-.16-.44-.136-.174.036-.31.176-.388.296-.1.128-.186.28-.258.467-.115.284-.186.615-.261.91l-.032.129c-.083.383-.143.77-.186 1.162a16.95 16.948 0 0 0-.06.632c-.008.1-.016.203-.027.307 0 .08.007.168-.028.244a.304.304 0 0 1-.052.068c-.08.072-.202.06-.31.056-.557-.016-1.045.3-1.35.755-.18.252-.281.542-.39.834-.01.048-.034.1-.054.152-.051.143-.13.327-.222.511a3.037 3.037 0 0 1-.317.46 3.285 3.285 0 0 1-.384.41 1.123 1.123 0 0 1-.515.26c-.174.04-.384-.043-.543-.203a.916.916 0 0 1-.206-.54c-.004-.055-.004-.115.028-.163.05-.068.146-.072.23-.076a1.623 1.623 0 0 0 1.375-1.015c.138-.34.178-.698.122-1.046a1.193 1.193 0 0 0-.19-.48.9.9 0 0 0-.396-.323c-.293-.14-.658-.127-1.01.004-.575.232-.951.74-1.134 1.562l-.02.088c-.114.487-.23 1-.582 1.354-.127.12-.261.163-.368.143-.044-.004-.08-.04-.103-.075-.096-.16.003-.532.15-1a4.1 4.1 0 0 0 .1-.366.925.925 0 0 0-.108-.495.783.783 0 0 0-.372-.324c-.143-.064-.31-.06-.468-.06h-.047c-.044 0-.103 0-.151-.012a.215.215 0 0 1-.147-.127.485.485 0 0 1 .016-.232c.004-.02.012-.048.016-.072a.368.368 0 0 0-.162-.412.509.509 0 0 0-.468-.036.768.768 0 0 0-.364.348.769.769 0 0 0-.103.48c.04.13.07.32.043.475-.055.28-.222.51-.384.74-.04.05-.072.106-.107.16a4.96 4.96 0 0 1-.706.825c-.372.335-.804.575-1.232.67-.745.165-1.506-.06-1.91-.734-.222-.38-.32-.827-.348-1.266a5.425 5.425 0 0 1 .424-2.516c.328-.76.816-1.52 1.715-1.614.353-.04.753.083.912.4.115.23.075.506 0 .75-.072.244-.175.49-.18.75-.003.26.124.54.37.616.238.072.495-.08.634-.29.138-.21.186-.46.245-.704a6.282 6.281 0 0 1 .662-1.634c.139-.236.297-.488.254-.76a.543.543 0 0 0-.373-.415.543.543 0 0 0-.535.144c-.134.148-.206.371-.387.43-.17.06-.35-.055-.507-.134-.6-.32-1.336-.312-1.963-.048-.634.25-1.146.735-1.526 1.294C.462 8.53.098 9.508.022 10.48c-.027.34-.031.695 0 1.038.036.46.1.854.214 1.206.139.423.317.79.547 1.094.266.34.587.6.94.747.372.148.784.22 1.192.208a3.172 3.172 0 0 0 1.177-.283 4.29 4.29 0 0 0 1.026-.68c.309-.26.594-.559.84-.89.162-.224.309-.46.44-.708a4.83 4.83 0 0 0 .178-.383c.044-.104.087-.215.202-.26.056-.043.15-.02.202.013.064.04.115.075.135.135.048.116.02.232-.004.332v.012c-.028.1-.055.203-.091.303-.14.424-.238.811-.16 1.195.045.207.128.387.25.527a.84.84 0 0 0 .504.264c.246.04.51-.028.725-.132.143-.068.278-.156.397-.26.06-.06.122-.12.174-.184.044-.06.087-.147.178-.143a.15.15 0 0 1 .107.064c.028.031.04.071.06.115.23.52.776.84 1.335.84h.07c.27 0 .556-.093.79-.22.27-.14.48-.348.7-.552.02-.016.045-.04.073-.044.035-.008.07.012.099.044a.26.26 0 0 1 .047.1c.135.34.46.6.824.66a1.1 1.1 0 0 0 .99-.356c.056-.06.104-.128.167-.176.064-.044.15-.076.222-.044.107.04.135.164.182.268.107.235.357.371.615.375.289 0 .554-.148.764-.34.195-.183.353-.399.516-.61a.328.328 0 0 1 .106-.096c.04-.024.096-.028.13 0 .033.024.045.06.06.091.163.4.587.652 1.01.648.417-.004.809-.224 1.103-.516.095-.092.194-.2.32-.21.14-.017.207.114.254.22.072.142.115.238.25.338.158.116.36.152.547.1.17-.04.34-.156.47-.316.072-.088.112-.204.19-.284.092-.087.132.028.136.1.016.116.016.236.008.352-.016.236-.052.471-.08.703-.011.068-.02.136-.063.188-.06.068-.166.08-.253.064a2.898 2.898 0 0 0-.321-.028l-.14-.016c-.201-.012-.4-.036-.61-.044h-.185c-.404 0-.733.048-1.03.16-.48.187-.852.57-1.003 1.018a1.305 1.305 0 0 0-.052.64c.04.203.13.403.282.587.265.315.68.515 1.149.543.408.02.852-.064 1.292-.26.848-.367 1.482-1.094 1.696-1.95 0-.02.01-.039.023-.043.298-.104.57-.248.813-.428.245-.187.467-.399.65-.643.09-.12.174-.243.253-.37.07-.125.13-.257.202-.38a.906.906 0 0 0 .13-.316.411.411 0 0 0-.05-.328.257.257 0 0 0-.135-.124m-13.68-1.63c.017-.071.045-.14.06-.206a1.9 1.9 0 0 1 .262-.504c.04-.048.08-.1.135-.136a.246.246 0 0 1 .186-.048c.107.02.183.128.202.236.032.18-.04.396-.114.555a1.097 1.097 0 0 1-.31.415c-.06.044-.114.088-.178.116-.028.008-.063.028-.115.028h-.016c-.055 0-.114-.028-.126-.088a.827.827 0 0 1 .015-.367m4.308-.184c-.004.072-.024.148-.028.223a4.91 4.91 0 0 0 0 .779c.012.152.047.3-.016.444a1.069 1.069 0 0 1-.567.643.555.555 0 0 1-.245.056c-.02 0-.04-.004-.06-.004-.12 0-.214-.092-.265-.18a.871.87 0 0 1-.1-.272 2.129 2.129 0 0 1 .072-1.122c.08-.22.202-.435.38-.594a.874.874 0 0 1 .563-.24.31.31 0 0 1 .206.064c.04.044.06.104.056.164a.05.05 0 0 1 .004.04m6.43 4.653c-.015.044-.06.104-.08.14-.042.08-.102.163-.161.235a2.562 2.562 0 0 1-.317.304c-.238.18-.503.311-.777.387a2.025 2.025 0 0 1-.487.072h-.04a.795.795 0 0 1-.515-.18.433.433 0 0 1-.158-.25.537.537 0 0 1 .047-.305.776.776 0 0 1 .38-.383c.326-.16.682-.176 1.019-.16.139.004.265.012.4.02.107.004.218.012.325.024.056 0 .115.004.17.012.044.004.092-.004.135.008.06.004.068.036.06.076'],
    google: ['#4285F4', 'M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z'],
    hashicorp: ['#000000', 'M10.114 4.094 4.215 7.5v13.09L.666 18.542V5.45L10.114 0v4.094zm3.772 13.37 3.549-2.049V2.05L13.885 0v10.426h-3.77v-3.89L6.562 8.585v13.357l3.551 2.054V13.599h3.772v3.865zM19.783 3.41V16.5l-5.897 3.405V24l9.448-5.45V5.458l-3.551-2.05z'],
    cncf: ['#231F20', 'M0 0v24h24V0H8.004Zm3.431 3.431h4.544l.029.023 4.544 4.544h3.03l-4.572-4.567h9.569v9.563l-.789-.782-3.784-3.79v3.03l2.271 2.272 2.272 2.272.029.03v4.543h-4.55l-.023-.023-2.272-2.278-2.272-2.272H8.427l3.785 3.79.782.783H3.43v-9.563l4.573 4.567v-3.031l-4.55-4.544-.023-.023Z'],
    redhat: ['#EE0000', 'M16.009 13.386c1.577 0 3.86-.326 3.86-2.202a1.765 1.765 0 0 0-.04-.431l-.94-4.08c-.216-.898-.406-1.305-1.982-2.093-1.223-.625-3.888-1.658-4.676-1.658-.733 0-.947.946-1.822.946-.842 0-1.467-.706-2.255-.706-.757 0-1.25.515-1.63 1.576 0 0-1.06 2.99-1.197 3.424a.81.81 0 0 0-.028.245c0 1.162 4.577 4.974 10.71 4.974m4.101-1.435c.218 1.032.218 1.14.218 1.277 0 1.765-1.984 2.745-4.593 2.745-5.895.004-11.06-3.451-11.06-5.734a2.326 2.326 0 0 1 .19-.925C2.746 9.415 0 9.794 0 12.217c0 3.969 9.405 8.861 16.851 8.861 5.71 0 7.149-2.582 7.149-4.62 0-1.605-1.387-3.425-3.887-4.512'],
    cisco: ['#1BA0D7', 'M16.331 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.186 1.186 0 01-.806-.237 1.038 1.038 0 01-.352-.498 1.21 1.21 0 01-.023-.667c.052-.225.178-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.34 2.34 0 00-.903.206c-.287.132-.54.327-.739.571a2.221 2.221 0 00-.04 2.705c.295.378.709.645 1.175.756.491.12 1.006.102 1.487-.052l.082-.023M5.336 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.183 1.183 0 01-.806-.237 1.03 1.03 0 01-.351-.498 1.202 1.202 0 01-.024-.667c.052-.225.177-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.344 2.344 0 00-.903.206 2.08 2.08 0 00-.74.571 2.224 2.224 0 00-.041 2.705 2.11 2.11 0 001.176.756c.491.12 1.005.102 1.487-.052l.083-.023M9.26 17.249l-.004.957.07.012c.22.041.441.069.664.085.195.019.391.022.587.012.187-.014.372-.049.551-.104.21-.06.405-.163.571-.305a1.16 1.16 0 00.333-.478 1.31 1.31 0 00-.007-.96 1.068 1.068 0 00-.298-.414 1.261 1.261 0 00-.438-.255l-.722-.268a.388.388 0 01-.197-.188.245.245 0 01.008-.219.382.382 0 01.154-.142.798.798 0 01.257-.074c.153-.022.308-.021.46.005.18.02.358.051.533.096l.038.008v-.883l-.069-.015a4.749 4.749 0 00-.543-.097 2.844 2.844 0 00-.714-.003c-.3.027-.585.143-.821.33-.16.126-.281.293-.351.484-.104.29-.105.608 0 .899.054.145.14.274.252.381.097.093.207.173.327.236.157.084.324.149.497.195.057.017.114.035.17.054l.085.031.024.01c.084.03.162.078.226.14.045.042.08.094.101.151a.325.325 0 01.001.161.339.339 0 01-.166.198.856.856 0 01-.275.086 2.032 2.032 0 01-.427.021 5.208 5.208 0 01-.557-.074 9.195 9.195 0 01-.287-.067l-.033-.006zm-2.475.995h1.05v-4.167h-1.05v4.167zm12.162-2.936a1.095 1.095 0 011.541.158 1.094 1.094 0 01-.157 1.541l-.017.014a1.096 1.096 0 01-1.367-1.713m-1.525.854a2.193 2.193 0 002.666 2.107 2.139 2.139 0 00.701-3.937 2.207 2.207 0 00-3.367 1.83M22.961 10.728a.52.52 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M20.117 10.728a.522.522 0 001.041 0V8.139a.521.521 0 00-1.04 0v2.589M17.231 11.771a.521.521 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M14.393 10.728a.521.521 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M11.494 10.728a.522.522 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M8.624 10.728a.52.52 0 001.039 0V8.139a.52.52 0 00-1.039 0v2.589M5.737 11.771a.52.52 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M2.876 10.728a.522.522 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M0 10.728a.521.521 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155'],
    kubernetes: ['#326CE5', 'M10.204 14.35l.007.01-.999 2.413a5.171 5.171 0 0 1-2.075-2.597l2.578-.437.004.005a.44.44 0 0 1 .484.606zm-.833-2.129a.44.44 0 0 0 .173-.756l.002-.011L7.585 9.7a5.143 5.143 0 0 0-.73 3.255l2.514-.725.002-.009zm1.145-1.98a.44.44 0 0 0 .699-.337l.01-.005.15-2.62a5.144 5.144 0 0 0-3.01 1.442l2.147 1.523.004-.002zm.76 2.75l.723.349.722-.347.18-.78-.5-.623h-.804l-.5.623.179.779zm1.5-3.095a.44.44 0 0 0 .7.336l.008.003 2.134-1.513a5.188 5.188 0 0 0-2.992-1.442l.148 2.615.002.001zm10.876 5.97l-5.773 7.181a1.6 1.6 0 0 1-1.248.594l-9.261.003a1.6 1.6 0 0 1-1.247-.596l-5.776-7.18a1.583 1.583 0 0 1-.307-1.34L2.1 5.573c.108-.47.425-.864.863-1.073L11.305.513a1.606 1.606 0 0 1 1.385 0l8.345 3.985c.438.209.755.604.863 1.073l2.062 8.955c.108.47-.005.963-.308 1.34zm-3.289-2.057c-.042-.01-.103-.026-.145-.034-.174-.033-.315-.025-.479-.038-.35-.037-.638-.067-.895-.148-.105-.04-.18-.165-.216-.216l-.201-.059a6.45 6.45 0 0 0-.105-2.332 6.465 6.465 0 0 0-.936-2.163c.052-.047.15-.133.177-.159.008-.09.001-.183.094-.282.197-.185.444-.338.743-.522.142-.084.273-.137.415-.242.032-.024.076-.062.11-.089.24-.191.295-.52.123-.736-.172-.216-.506-.236-.745-.045-.034.027-.08.062-.111.088-.134.116-.217.23-.33.35-.246.25-.45.458-.673.609-.097.056-.239.037-.303.033l-.19.135a6.545 6.545 0 0 0-4.146-2.003l-.012-.223c-.065-.062-.143-.115-.163-.25-.022-.268.015-.557.057-.905.023-.163.061-.298.068-.475.001-.04-.001-.099-.001-.142 0-.306-.224-.555-.5-.555-.275 0-.499.249-.499.555l.001.014c0 .041-.002.092 0 .128.006.177.044.312.067.475.042.348.078.637.056.906a.545.545 0 0 1-.162.258l-.012.211a6.424 6.424 0 0 0-4.166 2.003 8.373 8.373 0 0 1-.18-.128c-.09.012-.18.04-.297-.029-.223-.15-.427-.358-.673-.608-.113-.12-.195-.234-.329-.349-.03-.026-.077-.062-.111-.088a.594.594 0 0 0-.348-.132.481.481 0 0 0-.398.176c-.172.216-.117.546.123.737l.007.005.104.083c.142.105.272.159.414.242.299.185.546.338.743.522.076.082.09.226.1.288l.16.143a6.462 6.462 0 0 0-1.02 4.506l-.208.06c-.055.072-.133.184-.215.217-.257.081-.546.11-.895.147-.164.014-.305.006-.48.039-.037.007-.09.02-.133.03l-.004.002-.007.002c-.295.071-.484.342-.423.608.061.267.349.429.645.365l.007-.001.01-.003.129-.029c.17-.046.294-.113.448-.172.33-.118.604-.217.87-.256.112-.009.23.069.288.101l.217-.037a6.5 6.5 0 0 0 2.88 3.596l-.09.218c.033.084.069.199.044.282-.097.252-.263.517-.452.813-.091.136-.185.242-.268.399-.02.037-.045.095-.064.134-.128.275-.034.591.213.71.248.12.556-.007.69-.282v-.002c.02-.039.046-.09.062-.127.07-.162.094-.301.144-.458.132-.332.205-.68.387-.897.05-.06.13-.082.215-.105l.113-.205a6.453 6.453 0 0 0 4.609.012l.106.192c.086.028.18.042.256.155.136.232.229.507.342.84.05.156.074.295.145.457.016.037.043.09.062.129.133.276.442.402.69.282.247-.118.341-.435.213-.71-.02-.039-.045-.096-.065-.134-.083-.156-.177-.261-.268-.398-.19-.296-.346-.541-.443-.793-.04-.13.007-.21.038-.294-.018-.022-.059-.144-.083-.202a6.499 6.499 0 0 0 2.88-3.622c.064.01.176.03.213.038.075-.05.144-.114.28-.104.266.039.54.138.87.256.154.06.277.128.448.173.036.01.088.019.13.028l.009.003.007.001c.297.064.584-.098.645-.365.06-.266-.128-.537-.423-.608zM16.4 9.701l-1.95 1.746v.005a.44.44 0 0 0 .173.757l.003.01 2.526.728a5.199 5.199 0 0 0-.108-1.674A5.208 5.208 0 0 0 16.4 9.7zm-4.013 5.325a.437.437 0 0 0-.404-.232.44.44 0 0 0-.372.233h-.002l-1.268 2.292a5.164 5.164 0 0 0 3.326.003l-1.27-2.296h-.01zm1.888-1.293a.44.44 0 0 0-.27.036.44.44 0 0 0-.214.572l-.003.004 1.01 2.438a5.15 5.15 0 0 0 2.081-2.615l-2.6-.44-.004.005z'],
  };
  const ISSUERS = [[/anthropic/i, 'anthropic'], [/github/i, 'github'], [/linux foundation/i, 'linuxfoundation'], [/google/i, 'google'],
    [/hashicorp/i, 'hashicorp'], [/cncf|cloud native/i, 'cncf'], [/red hat/i, 'redhat'], [/cisco/i, 'cisco'], [/kubernetes/i, 'kubernetes'],
    [/credly/i, 'credly'], [/microsoft learn/i, 'https://learn.microsoft.com/favicon.ico'], [/microsoft|azure/i, 'https://www.microsoft.com/favicon.ico'],
    [/amazon|aws/i, 'https://aws.amazon.com/favicon.ico'], [/oracle/i, 'https://www.oracle.com/favicon.ico'],
    [/forsvaret|sjøforsvaret|hæren|luftforsvaret/i, 'https://www.forsvaret.no/_/image/d409e1bc-d800-4858-8e46-89c41daf72e4:326128bc7956e86a6d913180dbad83b65ac4e994/square-64/Forsvaret-favicon.png']];
  function initials(name) {
    const words = name.replace(/\(.*?\)/g, '').split(/[\s/&-]+/).filter(w => w && !/^(the|and|of|for|og|av)$/i.test(w));
    let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
    const t = el('span', 'os-iss', (words.length > 1 ? words.slice(0, 2).map(w => w[0]).join('') : (words[0] || '?').slice(0, 2)).toUpperCase());
    t.style.background = `hsl(${h} 45% 45%)`; return t;
  }
  // The mark for an issuer or source: a bundled logo, the site's own icon, or initials.
  function logoMark(name) {
    const hit = ISSUERS.find(([re]) => re.test(name)), v = hit && hit[1];
    if (v && LOGOS[v]) {
      const t = el('span', 'os-iss logo'), s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      s.setAttribute('viewBox', '0 0 24 24'); path.setAttribute('d', LOGOS[v][1]); s.append(path); t.style.background = LOGOS[v][0]; t.append(s); t.title = name; return t;
    }
    if (v) {
      const t = el('span', 'os-iss site'), img = el('img'); img.alt = ''; img.referrerPolicy = 'no-referrer'; img.loading = 'lazy'; img.src = v;
      img.onerror = () => t.replaceWith(initials(name)); t.append(img); t.title = name; return t;
    }
    const t = initials(name); t.title = name; return t;
  }
  function issuerBadges(sec, col) {
    if (col < 0) return;
    for (const td of sec.querySelectorAll('tbody tr td:nth-child(' + (col + 1) + ')')) {
      const name = td.textContent.trim(); if (!name) continue;
      const w = el('span', 'os-issw'); w.append(logoMark(name), el('span', '', name)); td.replaceChildren(w);
    }
  }
  function flagsView(e, text) {
    const wrap = el('div', 'os-flags');
    for (const f of e.flags) {
      const row = el('div', 'os-flag' + (f.open ? ' open' : '') + (f.resolved ? ' done' : ''));
      row.append(el('span', 'os-ftype t-' + f.type, (L().flags[f.type] || f.type) + (f.resolved ? ' · ' + (L().flags.resolved || 'resolved') + ' ' + f.resolved : '')));
      const tx = el('div', 'os-ftext'); tx.innerHTML = sanitize(marked.parseInline(f.text)); row.append(tx);
      if (f.open && !PF.data.readonly && !PF.asof) {
        const acts = el('div', 'os-acts small'), b = el('button', 'os-btn', t('answer'));
        b.onclick = () => {
          if (row.querySelector('textarea')) return;
          const ta = el('textarea'); ta.placeholder = t('answerHint');
          const go = el('button', 'os-btn on', t('saveAnswer')), cancel = el('button', 'os-btn', t('cancel')), r = el('div', 'os-answer');
          go.onclick = async () => { if (!ta.value.trim()) return; const j = await post('flag', { id: e.id, raw: f.raw, answer: ta.value, base_sha: e.sha });
            if (j.ok) { toast(t('answerSaved')); await load(); } else if (j.status === 409) { toast(t('reloaded')); await load(); } else toast(j.message || t('couldNot')); };
          cancel.onclick = () => r.remove(); r.append(ta, go, cancel); row.append(r); ta.focus();
        };
        acts.append(b);
        if (host.request) { const ask = el('button', 'os-btn ghost', t('askMe')); ask.onclick = () => request(e.id, f.text); acts.append(ask); }
        row.append(acts);
      }
      wrap.append(row);
    }
    const rest = text.split('\n').filter(l => !l.includes('⚑')).join('\n').trim();
    if (rest) wrap.append(renderMd(rest));
    for (const b of e.bad_flags || []) wrap.append(el('div', 'os-flag bad', '⚑? ' + b));
    return wrap;
  }

  // ---- editor ---------------------------------------------------------------------------------
  function grow(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(600, Math.max(70, ta.scrollHeight + 4)) + 'px'; }
  function editor(box, e) {
    const form = el('div', 'os-edit'), sch = PF.data.schema[e.type];
    const save = el('button', 'os-btn on'), dirty = () => { PF.dirty = true; save.disabled = false; };
    form.append(el('div', 'os-type', t('editing') + ' · ' + e.id), el('h2', '', titleOf(e)));
    const bar = el('div', 'os-acts'), cancel = el('button', 'os-btn', t('cancel')), raw = el('button', 'os-btn ghost', PF.edit.raw ? t('form') : t('raw'));
    save.append(icon('save'), t('save')); save.disabled = true; save.title = '⌘S / Ctrl+S';
    const verified = el('label', 'os-check'), vcb = el('input'); vcb.type = 'checkbox'; vcb.onchange = dirty;
    verified.append(vcb, ' ' + t('verified')); verified.title = t('verifiedTip');
    cancel.onclick = () => { if (PF.dirty && !confirm(t('discard'))) return; PF.dirty = false; PF.edit = null; PF.conflict = null; drawDetail(); };
    raw.onclick = () => { if (PF.dirty && !confirm(t('switchView'))) return; PF.dirty = false; PF.edit = { id: e.id, raw: !PF.edit.raw }; drawDetail(); };
    bar.append(save, cancel, raw, verified); form.append(bar, el('div', 'os-conflict-slot'));
    let collect;
    const skip = new Set(['schema', 'id', 'type', 'status', 'removed', 'removed_reason', 'last_reviewed']);
    if (PF.edit.raw) {
      const ta = el('textarea', 'os-raw'); ta.value = e.text; ta.oninput = dirty; form.append(ta);
      collect = () => ({ text: ta.value });
    } else {
      const grid = el('div', 'os-grid'), inputs = {};
      for (const f of sch.fields) {
        if (skip.has(f.name) || (!f.scaffold && !(f.name in e.meta))) continue;
        if (e.type === 'assignment' && f.name === 'customers' && val(e, 'kind') !== 'portfolio' && !list(e, 'customers').length) continue;
        const lab = el('label', 'os-field' + (f.type === 'array' ? ' wide' : '')); lab.append(el('span', '', fieldLabel(f.name) + (sch.required.includes(f.name) ? ' *' : ''))); lab.title = f.description;
        let inp;
        if (f.name === 'employment') {
          inp = el('select', 'os-select'); const o0 = el('option', '', t('none')); o0.value = ''; inp.append(o0);
          for (const j of PF.data.entries.filter(x => x.type === 'employment' && !x.removed).sort(newestFirst)) { const o = el('option', '', val(j, 'employer') + ', ' + val(j, 'title') + ' (' + period(j) + ')'); o.value = j.id; inp.append(o); }
          inp.value = val(e, f.name);
        } else if (f.enum && f.type !== 'array') {
          inp = el('select', 'os-select'); for (const v of f.enum) { const o = el('option', '', v ? enumLabel(f.name, v) : t('notSet')); o.value = v; inp.append(o); } inp.value = val(e, f.name);
        } else if (f.type === 'array') {
          inp = tagInput(list(e, f.name), f.name === 'tech' ? PF.data.tech_names : null, dirty);
        } else {
          inp = el('input'); inp.value = val(e, f.name);
          if (f.integer) { inp.inputMode = 'numeric'; inp.placeholder = t('number'); }
          if (f.name === 'start') inp.placeholder = 'YYYY-MM'; if (f.name === 'end') inp.placeholder = t('ongoingHint');
          if (/_until$/.test(f.name)) inp.placeholder = 'YYYY-MM-DD';
        }
        if (inp.tagName !== 'DIV') inp.oninput = inp.onchange = dirty;
        lab.append(inp); grid.append(lab); inputs[f.name] = inp;
        if (f.name === 'end') { const og = el('label', 'os-check'), cb = el('input'); cb.type = 'checkbox'; cb.checked = inp.value === 'ongoing';
          cb.onchange = () => { inp.value = cb.checked ? 'ongoing' : ''; dirty(); }; og.append(cb, ' ' + fieldLabel('ongoing')); lab.append(og); }
      }
      form.append(grid);
      const secs = {}, present = new Map(e.sections.map(s => [s.id, s]));
      const ids = [...(sch.table ? ['_intro'] : []), ...sch.sections, ...e.sections.filter(s => !s.known && s.id !== '_intro').map(s => s.id)];
      if (present.has('_intro') && !ids.includes('_intro')) ids.unshift('_intro');
      for (const sid of ids) {
        const s = present.get(sid), lab = el('label', 'os-field wide os-secedit');
        lab.append(el('span', '', sid === '_intro' ? (sch.table ? t('table') : t('intro')) : s && !s.known ? s.heading : sectionLabel(e.type, sid)));
        if (sid === 'flags') lab.append(el('small', '', t('flagHint')));
        const ta = el('textarea'); ta.value = s ? s.text : ''; ta.oninput = () => { dirty(); grow(ta); };
        lab.append(ta); form.append(lab); secs[sid] = { ta, heading: s ? s.heading : '' }; requestAnimationFrame(() => grow(ta));
      }
      collect = () => {
        const meta = {};
        for (const [k, inp] of Object.entries(inputs)) meta[k] = inp.getValues ? inp.getValues() : inp.value.trim();
        for (const k of Object.keys(e.meta)) if (!(k in meta) && !skip.has(k)) meta[k] = e.meta[k];
        for (const k of ['status', 'removed', 'removed_reason']) if (k in e.meta) meta[k] = e.meta[k];
        return { meta, sections: Object.entries(secs).map(([id, s]) => ({ id, heading: s.heading, text: s.ta.value })) };
      };
    }
    const doSave = async base => {
      if (!PF.dirty && !base) return;
      save.disabled = true;
      const j = await post('save', Object.assign({ id: e.id, base_sha: base || e.sha, verified: vcb.checked }, collect()));
      if (j.ok) { PF.dirty = false; PF.edit = null; PF.conflict = null; toast(j.error ? t('savedButError', { e: j.error }) : t('saved')); await load(); return; }
      save.disabled = false;
      if (j.status === 409) { PF.conflict = { current_text: j.current_text, current_sha: j.current_sha }; drawConflict(); } else toast(j.message || t('couldNot'));
    };
    save.onclick = () => doSave(); PF.edit.save = doSave;
    box.append(form);
    if (PF.conflict) drawConflict();
  }
  function tagInput(values, suggestions, onChange) {
    const box = el('div', 'os-tagin'), inp = el('input'); let vals = [...values];
    const known = suggestions ? new Set(suggestions.map(s => s.toLowerCase())) : null;
    if (suggestions) { const dl = el('datalist'); dl.id = 'osdl' + Math.random().toString(36).slice(2); for (const s of suggestions) { const o = el('option'); o.value = s; dl.append(o); } box.append(dl); inp.setAttribute('list', dl.id); }
    const draw = () => { box.querySelectorAll('.os-chip').forEach(c => c.remove());
      for (const v of vals) { const bad = known && !known.has(v.toLowerCase()), c = el('button', 'os-chip' + (bad ? ' warn' : ''), v + ' ×'); c.type = 'button';
        if (bad) c.title = t('unknownName'); c.onclick = () => { vals = vals.filter(x => x !== v); draw(); onChange(); }; box.insertBefore(c, inp); } };
    const add = () => { for (const v of inp.value.split(',').map(s => s.trim()).filter(Boolean)) if (!vals.includes(v)) vals.push(v); inp.value = ''; draw(); onChange(); };
    inp.placeholder = t('typeEnter');
    inp.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ',') { ev.preventDefault(); add(); } else if (ev.key === 'Backspace' && !inp.value && vals.length) { vals.pop(); draw(); onChange(); } };
    inp.onchange = () => { if (suggestions && suggestions.includes(inp.value)) add(); }; inp.onblur = () => { if (inp.value.trim()) add(); };
    box.append(inp); draw(); box.getValues = () => { if (inp.value.trim()) add(); return vals; };
    return box;
  }
  function drawConflict() {
    const slot = root.querySelector('.os-conflict-slot') || root.querySelector('.os-detail'); if (!slot || !PF.conflict) return;
    slot.querySelector('.os-conflict')?.remove();
    const e = byId(PF.edit ? PF.edit.id : PF.sel), box = el('div', 'os-conflict'), row = el('div', 'os-acts');
    box.append(el('b', '', t('conflict')));
    const theirs = el('button', 'os-btn', t('loadTheirs')); theirs.onclick = async () => { PF.dirty = false; PF.edit = null; PF.conflict = null; await load(); };
    const mine = el('button', 'os-btn', t('keepMine')); mine.title = t('keepMineTip');
    mine.onclick = () => { const c = PF.conflict; PF.conflict = null; box.remove(); PF.dirty = true; if (PF.edit && PF.edit.save) PF.edit.save(c.current_sha); };
    const diff = el('button', 'os-btn ghost', t('whatChanged')); diff.onclick = () => { if (!box.querySelector('.os-diff')) box.append(diffView(e ? e.text : '', PF.conflict.current_text || '')); };
    row.append(theirs, mine, diff); box.append(row); slot.prepend(box);
  }

  // ---- new, remove, request -------------------------------------------------------------------
  function newDialog(type) {
    let d = document.getElementById('osnew'); if (d) d.remove();
    d = el('dialog', 'os-dialog'); d.id = 'osnew'; document.body.append(d);
    d.append(el('h2', '', type === 'assignment' ? t('newAssignment') : t('newEmployment')), el('p', 'os-lead', t('newLead')));
    const grid = el('div', 'os-grid'), inputs = {};
    const field = (name, label, make) => { const lab = el('label', 'os-field'); lab.append(el('span', '', label)); const inp = make ? make() : el('input'); lab.append(inp); grid.append(lab); inputs[name] = inp; return inp; };
    const sel = opts => () => { const s = el('select', 'os-select'); for (const [v, l] of opts) { const o = el('option', '', l); o.value = v; s.append(o); } return s; };
    if (type === 'assignment') {
      field('kind', fieldLabel('kind'), sel([['client', enumLabel('kind', 'client')], ['portfolio', enumLabel('kind', 'portfolio')], ['internal', enumLabel('kind', 'internal')]]));
      field('employment', t('employmentReq'), sel(PF.data.entries.filter(x => x.type === 'employment' && !x.removed).sort(newestFirst).map(j => [j.id, val(j, 'employer') + ', ' + val(j, 'title')])));
      field('customer', t('customer'));
      field('customer_public', t('mayBeNamed'), sel(['unknown', 'public', 'anonymised', 'nda'].map(v => [v, enumLabel('customer_public', v)])));
      field('customer_alias', t('nameNotPublic')); field('role', t('role'));
    } else {
      field('employer', t('employerReq')); field('title', t('titleReq')); field('location', t('location'));
      field('employment_type', t('empType'), sel(PF.data.schema.employment.fields.find(f => f.name === 'employment_type').enum.map(v => [v, v ? enumLabel('employment_type', v) : t('notSet')])));
    }
    field('start', t('from')).placeholder = '2026-01'; const end = field('end', t('to')); end.placeholder = t('unknownEnd');
    const og = el('label', 'os-check'), ocb = el('input'); ocb.type = 'checkbox'; ocb.onchange = () => { end.value = ocb.checked ? 'ongoing' : ''; end.disabled = ocb.checked; };
    og.append(ocb, ' ' + t('ongoing')); end.parentElement.append(og);
    if (type === 'assignment') { field('allocation', t('allocationPct')).inputMode = 'numeric'; field('team_size', t('teamSize')).inputMode = 'numeric'; }
    const tl = el('label', 'os-field wide'); tl.append(el('span', '', t('technology'))); const tech = tagInput([], PF.data.tech_names, () => {}); tl.append(tech); grid.append(tl);
    d.append(grid);
    const texts = {};
    for (const sid of type === 'assignment' ? ['summary', 'contribution', 'outcome'] : ['summary']) {
      const lab = el('label', 'os-field wide'); lab.append(el('span', '', sectionLabel(type, sid))); const ta = el('textarea'); ta.rows = 3; lab.append(ta); d.append(lab); texts[sid] = ta;
    }
    let askTa = null;
    if (host.request) { const ask = el('label', 'os-field wide'); ask.append(el('span', '', t('toAssistant'))); askTa = el('textarea'); askTa.rows = 2; ask.append(askTa); d.append(ask); }
    const row = el('div', 'os-acts end'), msg = el('span', 'os-msg'), cancel = el('button', 'os-btn', t('cancel')), saveB = el('button', 'os-btn on', t('save'));
    row.append(msg, cancel); let interview = null;
    if (host.request) { interview = el('button', 'os-btn', t('saveAndAsk')); row.append(interview); }
    row.append(saveB); d.append(row);
    cancel.onclick = () => d.close();
    const submit = async alsoAsk => {
      const fields = {}; for (const [k, inp] of Object.entries(inputs)) fields[k] = inp.value.trim(); fields.tech = tech.getValues();
      if (!/^\d{4}(-\d{2})?$/.test(fields.start)) { msg.textContent = t('fromFormat'); return; }
      if (type === 'employment' && (!fields.employer || !fields.title)) { msg.textContent = t('needEmployer'); return; }
      if (type === 'assignment' && !fields.employment) { msg.textContent = t('needEmployment'); return; }
      if (alsoAsk) fields.confidence = 'needs-confirmation';
      const secs = {}; for (const [k, ta] of Object.entries(texts)) if (ta.value.trim()) secs[k] = ta.value;
      saveB.disabled = true;
      const j = await post('new', { type, fields, sections: secs }); saveB.disabled = false;
      if (!j.ok) { msg.textContent = j.message || t('couldNot'); return; }
      if (alsoAsk) await host.request(j.id, askTa.value.trim());
      d.close(); PF.sel = j.id; PF.view = 'entry'; await load(); toast(alsoAsk ? t('savedAsk') : t('saved'));
    };
    saveB.onclick = () => submit(false); if (interview) interview.onclick = () => submit(true);
    d.showModal(); (inputs.customer || inputs.employer).focus();
  }
  // Certifications from Credly or Microsoft Learn: a preview first, then the import as one commit.
  // At start-up: are there certificates on the stored pages that the table does not have yet?
  async function checkImports(manual) {
    const c = byId('certifications');
    if (!c || !list(c, 'imports').length || PF.data.readonly || PF.asof) return;
    PF.check = Object.assign(PF.check || {}, { busy: true }); if (manual) render();
    let j; try { j = await host.post('import', { dry_run: true }); } catch (err) { j = { ok: false, message: String(err) }; }
    if (!j || j.status === 404) { PF.check = null; return; }  // a host without the import endpoint
    PF.check = { at: new Date(), results: j.results || [], error: j.ok ? '' : j.message || t('couldNot') };
    PF.news = j.ok && j.changed ? j : null;
    if (PF.view === 'overview' && !PF.dirty) render();
  }
  const SOURCES = [['credly', 'Credly', /^https:\/\/(www\.)?credly\.com\//], ['mslearn', 'Microsoft Learn', /^https:\/\/learn\.microsoft\.com\//]];
  // Which accounts are linked, when they were last checked and imported, and buttons to check or import now.
  function accountsBox(side) {
    const c = byId('certifications'); if (!c || c.removed) return;
    const links = list(c, 'imports'), ro = PF.data.readonly || PF.asof, box = el('div', 'os-box os-accts'), h = el('h3');
    h.append(icon('globe'), t('accounts')); box.append(h);
    for (const [key, name, re] of SOURCES) {
      const url = links.find(u => re.test(u)), row = el('div', 'os-acct'), top = el('div', 'os-acct-top');
      const dot = el('span', 'os-acct-dot' + (url ? ' on' : '')); top.append(dot, el('b', '', name));
      if (url) { const a = el('a', '', t('linked')); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.title = t('openPage'); top.append(a); }
      else top.append(el('span', 'os-mut', t('notLinked')));
      row.append(top);
      if (url) {
        const r = PF.check && PF.check.results && PF.check.results.find(x => x.url === url), st = el('div', 'os-acct-st');
        const when = PF.check && PF.check.at ? PF.check.at.toLocaleTimeString(PF.data.lang === 'nb' ? 'nb-NO' : undefined, { hour: '2-digit', minute: '2-digit' }) : '';
        if (PF.check && PF.check.busy) st.append(t('checking'));
        else if (r && r.error) { st.classList.add('bad'); dot.classList.add('bad'); st.append(t('checkedAt', { t: when }) + ' · ' + t('readFail', { e: r.error })); }
        else if (r) { const n = r.added.length + r.updated.length + r.conflicts.length; st.append(t('checkedAt', { t: when }) + ' · '); st.append(el('span', n ? 'os-acct-new' : '', n ? t('newThings', { n }) : t('nothingNew'))); }
        else if (PF.check && PF.check.error) { st.classList.add('bad'); st.append(t('readFail', { e: PF.check.error })); }
        else st.append(t('neverChecked'));
        const stamp = list(c, 'sources').filter(x => x.startsWith(name + ' ')).pop();
        row.append(st, el('div', 'os-acct-st', stamp ? t('lastImported', { d: stamp.slice(name.length + 1) }) : t('neverImported')));
      }
      box.append(row);
    }
    if (!ro) {
      const acts = el('div', 'os-acts');
      if (links.length) { const ck = el('button', 'os-btn'); ck.append(icon('clock'), t('checkNow')); ck.disabled = !!(PF.check && PF.check.busy); ck.onclick = () => checkImports(true); acts.append(ck); }
      const im = el('button', 'os-btn'); im.append(icon('download'), links.length ? t('importBtn') + ' …' : t('linkIt'));
      im.onclick = () => importDialog(c, PF.news); acts.append(im); box.append(acts);
    }
    side.append(box);
  }
  function newsBanner(j) {
    const b = el('div', 'os-news'), n = k => j.results.reduce((a, r) => a + r[k].length, 0);
    const parts = [[n('added'), 'newsAdded'], [n('updated'), 'newsUpdated'], [n('conflicts'), 'newsConflicts']].filter(x => x[0]).map(([k, w]) => t(w, { n: k })).join(', ');
    const src = [...new Set(j.results.filter(r => r.added.length + r.updated.length + r.conflicts.length).map(r => r.source === 'credly' ? 'Credly' : 'Microsoft Learn'))].join(', ');
    const see = el('button', 'os-btn on'), later = el('button', 'os-btn ghost', t('notNow'));
    see.append(icon('download'), t('newsSee')); see.onclick = () => importDialog(byId('certifications'), j);
    later.onclick = () => { PF.news = null; render(); };
    b.append(icon('download'), el('span', '', t('newsFrom', { src, parts })), see, later); return b;
  }
  function importDialog(e, ready) {
    let d = document.getElementById('osimport'); if (d) d.remove();
    d = el('dialog', 'os-dialog'); d.id = 'osimport'; document.body.append(d);
    const ta = el('textarea'); ta.rows = 3; ta.value = list(e, 'imports').join('\n'); ta.placeholder = 'https://www.credly.com/users/…\nhttps://learn.microsoft.com/…/transcript/…';
    const out = el('div', 'os-imp'), row = el('div', 'os-acts end'), msg = el('span', 'os-msg');
    const cancel = el('button', 'os-btn', t('cancel')), pre = el('button', 'os-btn'), go = el('button', 'os-btn on');
    pre.append(icon('help'), t('preview')); go.append(icon('download'), t('importNow')); go.disabled = true;
    d.append(el('h2', '', t('importTitle')), el('p', 'os-lead', t('importLead')), ta, el('p', 'os-lead', t('importWhere')), out);
    row.append(msg, cancel, pre, go); d.append(row);
    const urls = () => ta.value.split(/\s+/).filter(Boolean);
    const show = j => {
      out.replaceChildren();
      for (const r of j.results) {
        const box = el('div', 'os-imp-src'); box.append(el('b', '', r.url.includes('credly') ? 'Credly' : 'Microsoft Learn'), el('span', 'os-mut', ' · ' + (r.error ? t('readFail', { e: r.error }) : t('found', { n: r.found }))));
        const part = (label, items, cls, fmt) => { if (!items.length) return; box.append(el('div', 'os-imp-h ' + cls, label)); const ul = el('ul'); for (const x of items) ul.append(el('li', '', fmt(x))); box.append(ul); };
        part(t('importAdd'), r.added, 'add', x => x.name + ' · ' + [x.issuer, x.date, x.expires && '→ ' + x.expires].filter(Boolean).join(' · '));
        part(t('importUpdate'), r.updated, 'upd', x => x.name + ': ' + Object.entries(x.changes).map(([k, v]) => (v[0] || t('emptyCell')) + ' → ' + v[1]).join(', '));
        part(t('importConflict'), r.conflicts, 'bad', x => x);
        out.append(box);
      }
      if (!j.changed) out.append(el('p', 'os-mut', t('nothingToChange')));
      go.disabled = !j.changed;
    };
    const run = async dry => {
      msg.textContent = ''; pre.disabled = go.disabled = true; status(t('preview') + ' …', 'busy');
      const j = await (dry ? host.post('import', { urls: urls(), dry_run: true }) : post('import', { urls: urls() }));
      status(''); pre.disabled = false;
      if (!j.ok) { msg.textContent = j.message || t('couldNot'); return; }
      if (!dry) { d.close(); PF.news = null; toast(j.changed ? t('imported') : t('nothingToChange')); await load(); checkImports(); return; }
      show(j);
    };
    pre.onclick = () => run(true); go.onclick = () => run(false); cancel.onclick = () => d.close();
    ta.oninput = () => { go.disabled = true; };
    d.showModal(); ta.focus();
    if (ready) show(ready);
  }
  async function removeEntry(e) {
    const reason = prompt(t('removeWhy', { t: titleOf(e) }), ''); if (!reason || !reason.trim()) return;
    const j = await post('remove', { id: e.id, reason, base_sha: e.sha });
    toast(j.ok ? t('movedRemoved') : j.message || t('couldNotRemove')); if (j.ok) await load();
  }
  async function request(id, quote) {
    const c = prompt(t('askWhat'), ''); if (c === null) return;
    const j = await host.request(id, c, quote || ''); toast((j && j.message) || t('requested'));
  }

  // ---- history, diff and as-of ----------------------------------------------------------------
  const when = s => new Date(s).toLocaleString(PF.data.lang === 'nb' ? 'nb-NO' : undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const actorName = a => ({ owner: t('you'), claude: t('assistant'), tool: t('tool') }[a] || a || '');
  function revRow(it, cls) {
    const r = el(cls === 'button' ? 'button' : 'div', 'os-rev'), top = el('div', 'os-revtop');
    top.append(el('code', '', it.short), el('span', '', actorName(it.actor)));
    for (const x of it.tags || []) { const g = el('span', 'os-tag'); g.append(icon('tag'), x); top.append(g); }
    top.append(el('span', 'os-when', when(it.date))); r.append(top, el('div', 'os-sub', it.subject.replace(/ \[\w+\]$/, '')));
    return r;
  }
  async function entryHistory(e) {
    if (PF.hist && PF.hist.id === e.id) { PF.hist = null; drawDetail(); return; }
    const box = el('div', 'os-hist'); box.append(el('h3', '', t('entryHistory')));
    PF.hist = { id: e.id, el: box }; drawDetail();
    const j = await host.get('log', { id: e.id });
    if (!j.ok || !j.items.length) { box.append(el('div', 'os-empty', t('noVersions'))); return; }
    const out = el('div');
    j.items.forEach((it, n) => {
      const b = revRow(it, 'button');
      b.onclick = async () => {
        box.querySelectorAll('.os-rev').forEach(x => x.classList.toggle('on', x === b));
        const cur = await host.get('show', { id: e.id, rev: it.rev });
        const prev = j.items[n + 1] ? await host.get('show', { id: e.id, rev: j.items[n + 1].rev }) : { text: '' };
        out.replaceChildren(el('div', 'os-lead', t('thisChange')), diffView(prev.text || '', cur.text || ''));
        if (n > 0 && !PF.data.readonly) { const r = el('button', 'os-btn', t('restoreHere')); r.onclick = async () => {
          if (!confirm(t('restoreConfirm'))) return;
          const res = await post('restore', { id: e.id, rev: it.rev }); toast(res.ok ? t('restored') : res.message || t('couldNot')); if (res.ok) { PF.hist = null; await load(); } };
          out.append(r); }
      };
      box.append(b);
    });
    box.append(out);
  }
  async function profileHistory(bar) {
    const pop = popup(bar, 'os-hpop', () => {}); if (!pop) return;
    const dRow = el('div', 'os-asof'), di = el('input'); di.type = 'date'; di.value = new Date().toISOString().slice(0, 10);
    const go = el('button', 'os-btn', t('showAsOf'));
    go.onclick = async () => { const j = await host.get('asof', { date: di.value }); if (!j.ok) { toast(j.message || t('noVersion')); return; }
      if (!leaveEdit()) return; PF.asof = { date: di.value, rev: j.rev, entries: j.entries }; pop.remove(); PF.view = 'overview'; render(); };
    dRow.append(di, go); pop.append(dRow);
    const j = await host.get('log');
    for (const it of (j.items || []).slice(0, 80)) pop.append(revRow(it));
  }
  function diffView(a, b) { const box = el('div', 'os-diff'); for (const [op, x] of wordDiff(a, b)) box.append(op === '=' ? document.createTextNode(x) : el(op === '+' ? 'ins' : 'del', '', x)); return box; }
  function wordDiff(a, b) {
    const tok = s => s.match(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu) || [];
    const x = tok(a), y = tok(b), n = x.length, m = y.length;
    if (n * m > 6e6) return [['-', a], ['+', b]];
    const w = m + 1, dp = new Uint32Array((n + 1) * w);
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i * w + j] = x[i] === y[j] ? dp[(i + 1) * w + j + 1] + 1 : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
    const out = [], push = (op, s) => { if (out.length && out[out.length - 1][0] === op) out[out.length - 1][1] += s; else out.push([op, s]); };
    let i = 0, j = 0;
    while (i < n && j < m) { if (x[i] === y[j]) { push('=', x[i]); i++; j++; } else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) push('-', x[i++]); else push('+', y[j++]); }
    while (i < n) push('-', x[i++]); while (j < m) push('+', y[j++]);
    return out;
  }

  // ---- timeline, technology, questions --------------------------------------------------------
  function timeline(box) {
    const all = entries().filter(e => !e.removed && (e.type === 'employment' || e.type === 'assignment') && ym(val(e, 'start')) != null);
    if (!all.length) { box.append(el('div', 'os-empty', t('noDates'))); return; }
    const certs = certRows(), edu = eduRows(), f = timeFrame(all, [...certs.map(c => c.at), ...edu.flatMap(r => [r.at, r.end ?? r.at])]), pct = mo => f.at(mo) + '%', wid = (a, b) => f.w(a, b) + '%';
    const tl = el('div', 'os-tl'), axis = el('div', 'os-tl-axis'), rows = el('div', 'os-tl-rows'), card = hoverCard(tl);
    for (let y = f.y0; y <= f.y1; y++) { const s = el('span', '', String(y)); s.style.left = pct(y * 12); s.style.width = wid(0, 11); axis.append(s); }
    tl.append(axis); rows.append(backdrop(f));
    for (const g of PF.data.issues.filter(i => i.id === 'employments')) {
      const r = el('div', 'os-gapnote'); r.append(icon('help'), el('span', '', issueText(g.message).replace(/^./, c => c.toUpperCase())));
      if (host.request) { const b = el('button', 'os-btn ghost', t('gap')); b.onclick = () => request('', g.message); r.append(b); }
      tl.append(r);
    }
    const bar = (e, cls) => {
      const a = ym(val(e, 'start')), b = endYm(e), d = el('button', 'os-tl-bar ' + cls + (val(e, 'end') === 'ongoing' ? ' ongoing' : ''));
      d.style.left = pct(a); d.style.width = wid(a, b);
      d.append(el('span', '', e.type === 'assignment' ? customerOf(e) : val(e, 'employer') + ', ' + val(e, 'title')));
      for (const br of list(e, 'breaks')) { const [p, q] = br.split('/'), bx = ym(p), by = ym(q); if (bx == null || by == null) continue;
        const h = el('i', 'os-tl-break'); h.style.left = ((bx - a) / (b - a + 1) * 100) + '%'; h.style.width = ((by - bx + 1) / (b - a + 1) * 100) + '%'; h.title = br; d.append(h); }
      card(d, e); d.onclick = () => select(e.id); return d;
    };
    for (const j of all.filter(e => e.type === 'employment').sort(newestFirst)) {
      const row = el('div', 'os-tl-row'); row.append(bar(j, 'job'));
      const lanes = [];
      for (const k of all.filter(e => e.type === 'assignment' && val(e, 'employment') === j.id).sort((p, q) => ym(val(p, 'start')) - ym(val(q, 'start')))) {
        let li = lanes.findIndex(end => end < ym(val(k, 'start'))); if (li < 0) { lanes.push(0); li = lanes.length - 1; } lanes[li] = endYm(k);
        const b = bar(k, 'kid k-' + (val(k, 'kind') || 'client')); b.style.top = (26 + li * 22) + 'px'; row.append(b);
      }
      row.style.height = (30 + lanes.length * 22) + 'px'; rows.append(row);
    }
    if (edu.length) rows.append(eduLane(f, edu, card, 'os-tl-row os-cert-lane'));
    if (certs.length) rows.append(certLane(f, certs, card, 'os-tl-row os-cert-lane'));
    tl.append(rows); box.append(tl, el('div', 'os-lead', t('tlLead')));
  }
  function techView(box) {
    const tb = el('table', 'os-table'), hr = el('tr'); for (const h of t('techHead')) hr.append(el('th', '', h)); tb.append(hr);
    for (const r of PF.data.tech) {
      const tr = el('tr'), name = el('td'), b = el('button', 'os-chip', r.name); b.onclick = () => { PF.filters.tech = [r.name]; PF.view = 'overview'; render(); }; name.append(b);
      const ids = el('td'); for (const id of r.ids) { const e = byId(id), a = el('button', 'os-link inline', e ? customerOf(e) + ' (' + (val(e, 'start') || '?').slice(0, 4) + ')' : id); a.onclick = () => select(id); ids.append(a); }
      tr.append(name, el('td', '', r.months + (r.ongoing ? '+' : '')), ids); tb.append(tr);
    }
    const unknown = new Set(); for (const e of entries()) for (const x of list(e, 'tech')) if (!PF.data.tech_names.includes(x)) unknown.add(x);
    box.append(el('p', 'os-lead', t('techLead')), tb);
    if (unknown.size) box.append(el('p', 'os-lead', t('unknownTech') + [...unknown].join(', ')));
  }
  function questions(box) {
    const groups = new Map();
    for (const i of PF.data.issues) { if (!groups.has(i.id)) groups.set(i.id, []); groups.get(i.id).push(i); }
    box.append(el('p', 'os-lead', t('qLead')));
    if (!groups.size) { box.append(el('div', 'os-empty', t('nothing'))); return; }
    const order = id => { const e = byId(id); return e ? ['person', 'certifications', 'education'].indexOf(e.type) + 10 * (e.type === 'assignment') : -1; };
    for (const [id, items] of [...groups.entries()].sort((a, b) => order(a[0]) - order(b[0]))) {
      const e = byId(id), card = el('div', 'os-qcard'), head = el('div', 'os-qhead');
      head.append(el('b', '', e ? titleOf(e) : id === 'employments' ? t('careerGap') : id));
      if (e) { const o = el('button', 'os-btn ghost'); o.append(icon('open'), t('open')); o.onclick = () => select(e.id); head.append(o);
        if (!PF.data.readonly && host.request) { const a = el('button', 'os-btn ghost', t('ask')); a.onclick = () => request(e.id, items.map(i => i.message).join('; ')); head.append(a); } }
      card.append(head);
      for (const i of items) {
        const flag = e && e.flags.find(f => f.open && i.message === f.type + ': ' + f.text);
        if (flag) card.append(flagsView(Object.assign({}, e, { flags: [flag], bad_flags: [] }), ''));
        else card.append(el('div', 'os-q lv-' + i.level, (i.field ? fieldLabel(i.field) + ': ' : '') + issueText(i.message)));
      }
      box.append(card);
    }
  }

  // ---- search and keys --------------------------------------------------------------------------
  function search(needle, jump) {
    if (!PF.data) return;
    PF.query = (needle || '').trim().toLowerCase();
    if (PF.view === 'entry') { const d = root.querySelector('.os-detail'); if (d && !PF.edit) highlightDom(d, PF.query, jump); }
    else { PF.view = 'overview'; render(); if (jump) root.querySelector('mark.os-hit')?.scrollIntoView({ block: 'center' }); }
    if (host.hits) host.hits(PF.query ? t('entries', { n: entries().filter(matches).length }) : '');
  }
  const onKey = e => { if ((e.metaKey || e.ctrlKey) && e.key === 's' && PF.edit && PF.edit.save && root.isConnected) { e.preventDefault(); PF.edit.save(); } };
  document.addEventListener('keydown', onKey);

  return { tick, search, reload: load, dirty: () => PF.dirty, destroy: () => { document.removeEventListener('keydown', onKey); if (host.nav) host.nav.replaceChildren(); } };
}
